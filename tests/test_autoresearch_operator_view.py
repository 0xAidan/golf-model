"""Tests for the autoresearch operator view: status, ledger, promote-to-lab, eras."""

from __future__ import annotations

import json

import pytest

from src import autoresearch_operator as op


@pytest.fixture()
def track_db(tmp_db):
    """tmp_db with a minimal track_configs + graded picks spine."""
    conn = tmp_db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS track_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track TEXT NOT NULL,
            strategy_bundle_json TEXT,
            model_variant TEXT,
            config_hash TEXT,
            label TEXT,
            status TEXT DEFAULT 'active',
            parent_id INTEGER,
            evidence_json TEXT,
            activated_by TEXT,
            activation_reason TEXT,
            activated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        "INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, '34')"
    )
    conn.execute(
        "INSERT INTO picks (id, tournament_id, bet_type, player_key, opponent_key) VALUES (1, 1, '72-hole Match', 'a', 'b')"
    )
    conn.execute(
        "INSERT INTO pick_outcomes (id, pick_id, hit, stake, profit) VALUES (1, 1, 1, 1.0, 0.9)"
    )
    conn.commit()
    yield conn


def test_cycle_status_shape(monkeypatch, tmp_path):
    hb = tmp_path / "autoresearch_heartbeat.json"
    hb.write_text(json.dumps({"ts": "2026-08-23T02:31:00+00:00", "stage": "cycle_end", "status": "ok"}))
    monkeypatch.setattr(op, "HEARTBEAT_PATH", hb)
    status = op.get_cycle_status()
    assert status["heartbeat"]["status"] == "ok"
    assert status["hours_until_next_cycle"] >= 0
    assert status["effort"] in ("light", "standard", "max")


def test_browse_ledger_filters(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    rows = [
        {"ts": "2026-08-23T01:00:00+00:00", "kind": "trial", "decision": "keep"},
        {"ts": "2026-08-23T02:00:00+00:00", "kind": "trial", "decision": "discard"},
        {"ts": "2026-08-23T03:00:00+00:00", "kind": "confirmation"},
    ]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkey = pytest.MonkeyPatch()
    monkey.setattr(op, "LEDGER_PATH", ledger)
    try:
        all_rows = op.browse_ledger(limit=10)
        assert all_rows["total"] == 3 and len(all_rows["rows"]) == 3
        keeps = op.browse_ledger(kinds=["trial"], decision="keep")
        assert len(keeps["rows"]) == 1
        newest_first = op.browse_ledger(limit=2)
        assert newest_first["rows"][0]["kind"] == "confirmation"
    finally:
        monkey.undo()


def test_promote_to_lab_requires_dossier(track_db):
    result = op.promote_candidate_to_lab("deadbeef", reason="test")
    assert result["ok"] is False


def test_promote_and_rollback_lab_roundtrip(track_db, tmp_path):
    from backtester.strategy_config_artifact import SCHEMA_VERSION

    dossier_dir = tmp_path / "promotion_ready"
    dossier_dir.mkdir(parents=True)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "name": "tier1_staged",
        "overrides": {"min_ev": 0.07},
        "ranges": {},
        "segments": {},
    }
    payload = {
        "status": "PROMOTION_READY",
        "schema_version": SCHEMA_VERSION,
        "name": "tier1_staged",
        "overrides": {"min_ev": 0.07},
        "ranges": {},
        "segments": {},
        "config_hash": "cafe1234",
        "search_window": {"events": 13},
        "confirmation_window": {"events": 3},
        "multiplicity_context": {"trials_run_this_lineage": 3},
    }
    (dossier_dir / "promotion_ready_cafe1234.json").write_text(json.dumps(payload))

    original_base = op.ROOT
    # Point the dossier lookup at tmp by patching module ROOT-derived path usage.
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        "src.autoresearch_operator.ROOT", tmp_path
    )
    # ROOT also controls LEDGER_PATH etc.; copy structure:
    (tmp_path / "output" / "research" / "promotion_ready").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "research" / "promotion_ready" / "promotion_ready_cafe1234.json").write_text(
        json.dumps(payload)
    )
    (tmp_path / "data").mkdir(exist_ok=True)
    # Seed a pre-existing active lab row (as production has) so promotion gets a rollback parent.
    track_db.execute(
        """
        INSERT INTO track_configs (track, strategy_bundle_json, model_variant, config_hash,
                                   label, status, activated_by, activation_reason)
        VALUES ('lab', '{}', 'baseline', 'seed0', 'lab_seed', 'active', 'seed', 'initial')
        """
    )
    track_db.commit()
    try:
        result = op.promote_candidate_to_lab("cafe1234", reason="grill-approved")
        assert result["ok"] is True
        active = track_db.execute(
            "SELECT config_hash, label FROM track_configs WHERE track='lab' AND status='active'"
        ).fetchone()
        assert active["label"].startswith("tier1")  # the new candidate row is active

        rollback = op.rollback_lab()
        assert rollback["ok"] is True
    finally:
        monkey.undo()


def test_eras_measures_from_activation(track_db):
    track_db.execute(
        """
        INSERT INTO track_configs (track, strategy_bundle_json, model_variant, config_hash,
                                   label, status, activated_by, activation_reason)
        VALUES ('lab', '{}', 'baseline', 'abc123', 'tier1-abc123', 'active', 'operator', 'test')
        """
    )
    track_db.commit()

    class _ConnProxy:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            return self._real.execute(sql, params)

        def close(self):
            return None

    import src.db as db_mod

    original = db_mod.get_conn
    db_mod.get_conn = lambda: _ConnProxy(track_db)
    try:
        eras = op.get_algorithm_eras()
    finally:
        db_mod.get_conn = original

    lab_eras = [e for e in eras["eras"] if e["config_hash"] == "abc123"]
    assert len(lab_eras) == 1
    assert lab_eras[0]["picks"] >= 1
    assert eras["all_time"]["picks"] >= 1
