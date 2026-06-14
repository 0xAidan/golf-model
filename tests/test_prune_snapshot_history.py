"""Tests for ``db.prune_snapshot_history_tables`` (operator retention)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import src.db as db


def test_prune_skips_without_env_or_days(monkeypatch, tmp_db) -> None:
    monkeypatch.delenv("SNAPSHOT_HISTORY_RETAIN_DAYS", raising=False)
    out = db.prune_snapshot_history_tables(retain_days=None)
    assert out["skipped"] is True
    assert out["live_snapshot_history_deleted"] == 0


def test_prune_deletes_rows_older_than_cutoff(tmp_db) -> None:
    conn = db.get_conn()
    conn.execute("DELETE FROM live_snapshot_history")
    conn.execute("DELETE FROM market_prediction_rows")
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    new = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    payload = '{"x": 1}'
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

    out = db.prune_snapshot_history_tables(retain_days=365, require_archive=False)
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
    conn.close()
    assert int(n_old) == 0
    assert int(n_new) >= 1
