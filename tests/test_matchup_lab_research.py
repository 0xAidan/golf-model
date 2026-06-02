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


def test_select_max_roi_trial_winners_prefers_robust_gate():
    class _Trial:
        def __init__(self, number, primary_n, holdout_n, primary_roi, holdout_roi, value=1.0):
            self.number = number
            self.value = value
            self.params = {}
            self.user_attrs = {
                "primary_n": primary_n,
                "holdout_n": holdout_n,
                "primary_roi_pct": primary_roi,
                "holdout_roi_pct": holdout_roi,
                "primary_hit_rate_pct": 50.0,
                "holdout_hit_rate_pct": 50.0,
                "primary_brier": 0.25,
                "holdout_brier": 0.25,
                "primary_drawdown_pct": 0.0,
                "holdout_drawdown_pct": 0.0,
            }

    complete = [
        _Trial(1, 81, 67, 58.0, 25.0),
        _Trial(2, 276, 203, 16.59, 9.05),
        _Trial(3, 301, 203, 13.8, 9.05),
        _Trial(4, 250, 199, 20.0, 7.0),
    ]
    complete.sort(key=lambda t: float(t.user_attrs["primary_roi_pct"]), reverse=True)
    winners = lab._select_max_roi_trial_winners(complete)
    assert winners["best_unconstrained"]["number"] == 1
    assert winners["best_legacy_constrained"]["number"] == 2
    assert winners["best_robust_constrained"]["number"] == 3


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
