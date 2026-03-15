import sqlite3

import pytest

from backtester.checkpoint_replay import resolve_recent_signature_event, summarize_checkpoint_results


def test_checkpoint_summary_aggregates_metrics():
    results = [
        {"metrics": {"roi_pct": 2.0, "clv_avg": 0.01, "calibration_error": 0.03, "total_bets": 10}},
        {"metrics": {"roi_pct": 4.0, "clv_avg": 0.03, "calibration_error": 0.05, "total_bets": 15}},
        {"metrics": {"roi_pct": 6.0, "clv_avg": 0.05, "calibration_error": 0.07, "total_bets": 20}},
    ]
    out = summarize_checkpoint_results(results)
    assert out["checkpoints_evaluated"] == 3
    assert out["total_bets"] == 45
    assert out["weighted_roi_pct"] == 4.0


def _seed_checkpoint_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE historical_event_info (
            event_id TEXT,
            year INTEGER,
            event_name TEXT,
            start_date TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE historical_odds (
            event_id TEXT,
            year INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE pit_rolling_stats (
            event_id TEXT,
            year INTEGER
        )
        """
    )
    return conn


def test_resolve_recent_signature_event_prefers_replay_ready_event(monkeypatch):
    conn = _seed_checkpoint_db()
    conn.execute(
        "INSERT INTO historical_event_info (event_id, year, event_name, start_date) VALUES (?, ?, ?, ?)",
        ("34", 2026, "Travelers Championship", "2026-06-25"),
    )
    conn.execute(
        "INSERT INTO historical_event_info (event_id, year, event_name, start_date) VALUES (?, ?, ?, ?)",
        ("7", 2026, "The Genesis Invitational", "2026-02-19"),
    )
    conn.execute("INSERT INTO historical_odds (event_id, year) VALUES (?, ?)", ("7", 2026))
    conn.execute("INSERT INTO pit_rolling_stats (event_id, year) VALUES (?, ?)", ("7", 2026))
    conn.commit()

    monkeypatch.setattr("backtester.checkpoint_replay.db.get_conn", lambda: conn)
    resolved = resolve_recent_signature_event()
    assert resolved.event_id == "7"
    assert resolved.year == 2026


def test_resolve_recent_signature_event_errors_without_replay_ready_data(monkeypatch):
    conn = _seed_checkpoint_db()
    conn.execute(
        "INSERT INTO historical_event_info (event_id, year, event_name, start_date) VALUES (?, ?, ?, ?)",
        ("34", 2026, "Travelers Championship", "2026-06-25"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.checkpoint_replay.db.get_conn", lambda: conn)
    with pytest.raises(ValueError, match="replay-ready"):
        resolve_recent_signature_event()

