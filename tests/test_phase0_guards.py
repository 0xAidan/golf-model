"""Phase 0 guards: honest tie EV, no metrics journal churn, learning loops off by default."""

import json

import pytest

from src import config
from src.adaptation import get_adaptation_state
from src.matchup_value import _v5_matchup_ev_void_tie


# ── Tie-void EV ──────────────────────────────────────────────────────

def test_fair_coin_at_minus_110_is_negative_with_any_tie_probability():
    decimal = 1 + 100 / 110
    assert _v5_matchup_ev_void_tie(0.5, decimal, 0.11) == pytest.approx(-0.04045, abs=1e-4)
    for tie in (0.0, 0.05, 0.11, 0.14):
        assert _v5_matchup_ev_void_tie(0.5, decimal, tie) < 0


def test_tie_probability_shrinks_ev_toward_zero_and_never_flips_its_sign():
    winning = [_v5_matchup_ev_void_tie(0.58, 2.0, tie) for tie in (0.0, 0.05, 0.11)]
    losing = [_v5_matchup_ev_void_tie(0.45, 2.0, tie) for tie in (0.0, 0.05, 0.11)]
    assert winning == sorted(winning, reverse=True) and all(value > 0 for value in winning)
    assert losing == sorted(losing) and all(value < 0 for value in losing)
    assert _v5_matchup_ev_void_tie(0.58, 2.0, 0.11) == pytest.approx(0.89 * 0.16)


def test_break_even_price_has_zero_ev_whatever_the_tie_probability():
    for tie in (0.0, 0.08, 0.14):
        assert _v5_matchup_ev_void_tie(0.5, 2.0, tie) == pytest.approx(0.0, abs=1e-12)


# ── Metrics journal ──────────────────────────────────────────────────

def _metric(tournament_id, **updates):
    return {
        "tournament_id": tournament_id,
        "csv_import_id": None,
        "player_key": "source_player",
        "player_display": "Source Player",
        "metric_category": "strokes_gained",
        "data_mode": "recent_form",
        "round_window": "50",
        "metric_name": "SG:TOT",
        "metric_value": 1.25,
        "metric_text": None,
        **updates,
    }


def _metric_versions(conn):
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='prediction_history_versions'"
    ).fetchone():
        return []
    return [json.loads(row[0]) for row in conn.execute(
        "SELECT payload_json FROM prediction_history_versions WHERE source_table='metrics' ORDER BY id"
    )]


def test_resync_with_only_a_new_import_id_is_not_journaled(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Resync", year=2026)
    imports = [
        tmp_db.log_csv_import(tournament, f"sync{n}.json", "sg", "recent_form", "50", 1)
        for n in range(4)
    ]

    for import_id in imports:
        tmp_db.store_metrics([_metric(tournament, csv_import_id=import_id)])

    conn = tmp_db.get_conn()
    try:
        assert _metric_versions(conn) == []
        rows = tmp_db.get_player_metrics(tournament, "source_player")
        assert len(rows) == 1
        assert rows[0]["csv_import_id"] == imports[-1]
    finally:
        conn.close()


def test_changed_value_is_still_journaled_once(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Value change", year=2026)
    first = tmp_db.log_csv_import(tournament, "a.json", "sg", "recent_form", "50", 1)
    second = tmp_db.log_csv_import(tournament, "b.json", "sg", "recent_form", "50", 1)
    tmp_db.store_metrics([_metric(tournament, csv_import_id=first)])
    original = tmp_db.get_player_metrics(tournament, "source_player")[0]

    tmp_db.store_metrics([_metric(tournament, csv_import_id=second, metric_value=2.0)])

    conn = tmp_db.get_conn()
    try:
        assert _metric_versions(conn) == [original]
        assert tmp_db.get_player_metrics(tournament, "source_player")[0]["metric_value"] == 2.0
    finally:
        conn.close()


# ── Adaptation freeze ────────────────────────────────────────────────

def _seed_market(tmp_db, *, wagered, returned, losing_streak):
    conn = tmp_db.get_conn()
    tournament = tmp_db.get_or_create_tournament("Cold market", year=2026)
    conn.execute("UPDATE tournaments SET date='2026-10-01' WHERE id=?", (tournament,))
    conn.execute(
        """INSERT INTO market_performance
           (tournament_id, market_type, bets_placed, wins, losses, units_wagered, units_returned)
           VALUES (?, 'top20', 30, 3, 27, ?, ?)""",
        (tournament, wagered, returned),
    )
    conn.commit()
    conn.close()
    return losing_streak


def test_freeze_is_off_by_default_and_worst_state_is_cold(tmp_db, monkeypatch):
    monkeypatch.delenv("ADAPTATION_FREEZE_ENABLED", raising=False)
    _seed_market(tmp_db, wagered=30.0, returned=6.0, losing_streak=0)  # ROI -80%
    monkeypatch.setattr("src.adaptation._count_consecutive_losses", lambda conn, market: 25)

    state = get_adaptation_state("top20")

    assert state["state"] == "cold"
    assert state["suppress"] is False
    assert state["stake_multiplier"] == config.ADAPTATION_STAKE_MULTIPLIER_COLD
    assert state["ev_threshold"] == config.ADAPTATION_EV_THRESHOLD_COLD


def test_freeze_still_available_when_explicitly_enabled(tmp_db, monkeypatch):
    monkeypatch.setenv("ADAPTATION_FREEZE_ENABLED", "1")
    _seed_market(tmp_db, wagered=30.0, returned=6.0, losing_streak=0)
    monkeypatch.setattr("src.adaptation._count_consecutive_losses", lambda conn, market: 0)

    assert get_adaptation_state("top20")["state"] == "frozen"

    monkeypatch.setattr("src.adaptation._count_consecutive_losses", lambda conn, market: 10)
    assert get_adaptation_state("top20")["suppress"] is True


# ── Automatic retune ─────────────────────────────────────────────────

def test_switches_default_off_and_follow_the_environment(monkeypatch):
    from src import safety_flags

    monkeypatch.delenv("AUTO_RETUNE_ENABLED", raising=False)
    monkeypatch.delenv("ADAPTATION_FREEZE_ENABLED", raising=False)
    assert safety_flags.auto_retune_enabled() is False
    assert safety_flags.adaptation_freeze_enabled() is False
    monkeypatch.setenv("AUTO_RETUNE_ENABLED", "true")
    assert safety_flags.auto_retune_enabled() is True
    assert safety_flags.adaptation_freeze_enabled() is False


def test_post_tournament_learning_skips_weight_changes_by_default(tmp_db, monkeypatch):
    from src import learning
    from src.models import weights

    monkeypatch.delenv("AUTO_RETUNE_ENABLED", raising=False)
    calls = []
    monkeypatch.setattr(weights, "retune", lambda **kwargs: calls.append(kwargs) or {"saved": True})
    monkeypatch.setattr(learning, "update_course_weights", lambda *a, **k: calls.append("course") or {})
    tournament = tmp_db.get_or_create_tournament("No retune", year=2026)

    summary = learning.post_tournament_learn(tournament, course_num=1, course_name="Test Course")

    assert calls == []
    assert summary["steps"]["global_retune"]["skipped"] is True
    assert summary["steps"]["course_weights"]["skipped"] is True


def test_pinned_comparator_sources_are_untouched():
    """The frozen original-model comparator hashes these files; Phase 0 must not edit them."""
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    pinned = json.loads((root / "config/model-baselines/original-453f49ec24f0e48a.json").read_text())
    for name, digest in pinned["source_hashes"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
