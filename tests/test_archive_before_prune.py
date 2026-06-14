"""Tests for archive-before-prune enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import src.db as db
from src.cold_archive import export_tick_tables_before_cutoff


def _seed_old_and_new_rows(tmp_db) -> str:
    conn = db.get_conn()
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    new = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    payload = '{"x": 1}'
    conn.execute("DELETE FROM live_snapshot_history")
    conn.execute("DELETE FROM market_prediction_rows")
    conn.execute("DELETE FROM picks")
    conn.execute(
        """
        INSERT INTO live_snapshot_history
        (snapshot_id, generated_at, tour, cadence_mode, section, event_id, event_name,
         source_event_id, source_event_name, active, payload_json)
        VALUES (?, ?, 'pga', 'off_window', 'live', 'e1', 'Old Event', 'e1', 'Old Event', 0, ?)
        """,
        ("snap_old", old, payload),
    )
    conn.execute(
        """
        INSERT INTO live_snapshot_history
        (snapshot_id, generated_at, tour, cadence_mode, section, event_id, event_name,
         source_event_id, source_event_name, active, payload_json)
        VALUES (?, ?, 'pga', 'off_window', 'live', 'e2', 'New Event', 'e2', 'New Event', 0, ?)
        """,
        ("snap_new", new, payload),
    )
    conn.execute(
        """
        INSERT INTO market_prediction_rows
        (snapshot_id, generated_at, tour, section, event_id, event_name, market_family,
         market_type, player_key, player_display, opponent_key, opponent_display,
         book, odds, model_prob, implied_prob, ev, is_value, payload_json)
        VALUES (?, ?, 'pga', 'live', 'e1', 'Old Event', 'matchup', 'tournament_matchups',
                'a', 'A', 'b', 'B', 'fd', '+100', 0.5, 0.5, 0.0, 0, ?)
        """,
        ("snap_old", old, payload),
    )
    conn.commit()
    conn.close()

    tid = tmp_db.get_or_create_tournament("Keep Forever Event", year=2026)
    tmp_db.store_picks([
        {
            "tournament_id": tid,
            "model_variant": "baseline",
            "source": "cockpit",
            "bet_type": "top10",
            "player_key": "player_a",
            "player_display": "Player A",
            "opponent_key": "",
            "opponent_display": "",
            "composite_score": 1.0,
            "course_fit_score": 0.5,
            "form_score": 0.5,
            "momentum_score": 0.0,
            "model_prob": 0.12,
            "market_odds": "+1200",
            "market_book": "draftkings",
            "market_implied_prob": 0.08,
            "ev": 0.04,
            "confidence": "low",
            "reasoning": "archive test",
        }
    ])
    return old


def test_prune_fails_without_archive(tmp_path, tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("SNAPSHOT_PRUNE_REQUIRE_ARCHIVE", "1")
    _seed_old_and_new_rows(tmp_db)

    out = db.prune_snapshot_history_tables(retain_days=365, require_archive=True)
    assert out["skipped"] is True
    assert "archive" in out["reason"].lower()

    conn = db.get_conn()
    n_old = conn.execute(
        "SELECT COUNT(*) FROM live_snapshot_history WHERE snapshot_id = ?",
        ("snap_old",),
    ).fetchone()[0]
    picks = conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    conn.close()
    assert int(n_old) >= 1
    assert int(picks) >= 1


def test_prune_succeeds_with_verified_archive(tmp_path, tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("SNAPSHOT_PRUNE_REQUIRE_ARCHIVE", "1")
    _seed_old_and_new_rows(tmp_db)

    retain_days = 365
    from src.cold_archive import export_tick_tables_before_cutoff, snapshot_history_cutoff_utc

    cutoff = snapshot_history_cutoff_utc(retain_days)
    exports_dir = tmp_path / "exports"
    monkeypatch.setenv("SNAPSHOT_ARCHIVE_EXPORTS_DIR", str(exports_dir))
    export_tick_tables_before_cutoff(
        db_path=tmp_db.DB_PATH,
        cutoff_utc=cutoff,
        output_dir=str(exports_dir),
        retain_days=retain_days,
    )

    out = db.prune_snapshot_history_tables(retain_days=retain_days, require_archive=True)
    assert out["skipped"] is False
    assert out["live_snapshot_history_deleted"] >= 1

    conn = db.get_conn()
    n_old = conn.execute(
        "SELECT COUNT(*) FROM live_snapshot_history WHERE snapshot_id = ?",
        ("snap_old",),
    ).fetchone()[0]
    n_new = conn.execute(
        "SELECT COUNT(*) FROM live_snapshot_history WHERE snapshot_id = ?",
        ("snap_new",),
    ).fetchone()[0]
    picks = conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]
    metrics_before = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    rounds_before = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
    conn.close()

    assert int(n_old) == 0
    assert int(n_new) >= 1
    assert int(picks) >= 1
    assert int(metrics_before) >= 0
    assert int(rounds_before) >= 0
