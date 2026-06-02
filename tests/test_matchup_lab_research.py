import sqlite3

import scripts.run_matchup_lab_research as lab


def _seed_pit_audit_db() -> sqlite3.Connection:
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
    conn.execute(
        "INSERT INTO pit_rolling_stats (event_id, year, player_key, rounds_used) VALUES ('evt1', 2026, 'a', 2)"
    )
    conn.execute(
        "INSERT INTO pit_rolling_stats (event_id, year, player_key, rounds_used) VALUES ('evt2', 2026, 'b', 2)"
    )
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES ('a', '2026-01-01', 1.0)")
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES ('a', '2026-01-02', 1.0)")
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES ('b', '2026-01-01', 1.0)")
    conn.execute("INSERT INTO rounds (player_key, event_completed, sg_total) VALUES ('b', '2026-01-02', 1.0)")
    conn.commit()
    return conn


def test_window_contract_is_disjoint():
    assert lab.PRIMARY_DATE_END < lab.HOLDOUT_DATE_START


def test_run_pit_audit_reports_event_level_failures(monkeypatch):
    conn = _seed_pit_audit_db()
    monkeypatch.setattr("scripts.run_matchup_lab_research.db.get_conn", lambda: conn)

    def _fake_assert(event_id: str, year: int, as_of_date: str) -> None:
        if event_id == "evt2":
            raise ValueError("Temporal leakage detected")

    monkeypatch.setattr("scripts.run_matchup_lab_research.assert_checkpoint_temporal_integrity", _fake_assert)

    windows = {
        "primary": [
            {"event_id": "evt1", "year": 2026, "event_date": "2026-02-10"},
            {"event_id": "evt2", "year": 2026, "event_date": "2026-02-17"},
        ],
        "holdout": [],
    }
    report = lab._run_pit_audit(windows)
    assert report["events_checked"] == 2
    assert report["events_failed"] == 1
    assert report["status"] == "fail"
    failed = [row for row in report["event_audit"] if not row["assert_checkpoint_temporal_integrity_passed"]]
    assert len(failed) == 1
    assert failed[0]["event_id"] == "evt2"
