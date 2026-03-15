import sqlite3

import pytest

from backtester.checkpoint_replay import assert_checkpoint_temporal_integrity


def _seed_temporal_guard_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE pit_rolling_stats (
            event_id TEXT,
            year INTEGER,
            player_key TEXT,
            rounds_used INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE rounds (
            player_key TEXT,
            event_completed TEXT,
            sg_total REAL
        )
        """
    )
    return conn


def test_checkpoint_temporal_integrity_raises_on_leakage(monkeypatch):
    conn = _seed_temporal_guard_db()
    conn.execute("INSERT INTO pit_rolling_stats (event_id, year, player_key, rounds_used) VALUES (?, ?, ?, ?)", ("7", 2026, "player_a", 5))
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES (?, ?, ?)", ("player_a", "2026-02-01", 1.0))
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES (?, ?, ?)", ("player_a", "2026-02-05", 1.0))
    conn.commit()

    monkeypatch.setattr("backtester.checkpoint_replay.db.get_conn", lambda: conn)
    with pytest.raises(ValueError, match="Temporal leakage detected"):
        assert_checkpoint_temporal_integrity("7", 2026, "2026-02-19")


def test_checkpoint_temporal_integrity_passes_when_history_is_sufficient(monkeypatch):
    conn = _seed_temporal_guard_db()
    conn.execute("INSERT INTO pit_rolling_stats (event_id, year, player_key, rounds_used) VALUES (?, ?, ?, ?)", ("7", 2026, "player_a", 2))
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES (?, ?, ?)", ("player_a", "2026-02-01", 1.0))
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES (?, ?, ?)", ("player_a", "2026-02-05", 1.0))
    conn.commit()

    monkeypatch.setattr("backtester.checkpoint_replay.db.get_conn", lambda: conn)
    assert_checkpoint_temporal_integrity("7", 2026, "2026-02-19")

