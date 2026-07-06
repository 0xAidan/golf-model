"""Tests for structured grading reports (G4)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_build_grading_report_includes_scoring_breakdown():
    from scripts.grade_tournament import build_grading_report

    report = build_grading_report(
        {
            "scored_count": 5,
            "voided_count": 2,
            "voided_picks": [
                {"pick_id": 9, "reason": "player_not_in_results"},
                {"pick_id": 10, "reason": "no_stored_round_matchup_outcome"},
            ],
            "skipped_non_positive_ev": 3,
        },
        {
            "status": "ok",
            "events": [{"ungraded_positive_ev_picks": 0}],
        },
    )

    assert report["status"] == "complete"
    assert report["scored_count"] == 5
    assert report["voided_count"] == 2
    assert report["skipped_count"] == 0
    assert report["scoring"]["voided"][0]["reason"] == "player_not_in_results"
    assert report["scoring"]["skipped_non_positive_ev"] == 3
    assert len(report["skipped_picks"]) == 2


def test_build_grading_report_partial_when_ungraded_remain():
    from scripts.grade_tournament import build_grading_report

    report = build_grading_report(
        {"scored_count": 1, "voided_count": 0, "voided_picks": []},
        {
            "status": "ok",
            "events": [{"ungraded_positive_ev_picks": 2}],
        },
    )

    assert report["status"] == "partial"
    assert report["skipped_count"] == 2
    assert "2 +EV pick(s)" in (report["message"] or "")


def test_grade_tournament_preserves_partial_status(monkeypatch, tmp_db):
    from scripts.grade_tournament import grade_tournament

    monkeypatch.setattr(
        "src.learning.score_picks_for_tournament",
        lambda tournament_id, **kwargs: {
            "status": "ok",
            "scored_count": 1,
            "voided_count": 1,
            "voided_picks": [{"pick_id": 1, "reason": "player_not_in_results"}],
        },
    )
    monkeypatch.setattr(
        "src.grading_reconciliation.reconcile_grading",
        lambda **kwargs: {
            "status": "discrepancies",
            "events": [{"ungraded_positive_ev_picks": 1}],
        },
    )
    monkeypatch.setattr(
        "scripts.grade_tournament.fetch_event_results",
        lambda event_id, year: [{
            "player_key": "a",
            "player_display": "Player A",
            "finish_position": 1,
            "finish_text": "1",
            "made_cut": 1,
        }],
    )
    monkeypatch.setattr("scripts.grade_tournament.fetch_matchup_outcomes", lambda *args, **kwargs: [])
    monkeypatch.setattr("src.learning.post_tournament_learn", lambda *args, **kwargs: {"steps": {}, "calibration": {}})
    monkeypatch.setattr(
        "src.official_pick_record.consolidate_duplicate_picks",
        lambda tournament_id: {"removed": 0, "kept": 0},
    )
    monkeypatch.setattr(
        "src.market_row_backfill.backfill_completed_market_rows_into_picks",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "src.pick_ledger.tournament_has_locked_outcomes",
        lambda tournament_id: False,
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    tid = tmp_db.get_or_create_tournament("Report Test", year=2026, event_id="990")
    report = grade_tournament("990", 2026, tournament_id=tid)

    assert report["status"] == "partial"
    assert report["grading_report"]["voided_count"] == 1
    assert report["grading_report"]["scoring"]["voided"][0]["reason"] == "player_not_in_results"


def test_ops_health_exposes_void_and_ungraded_counts(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "snapshot_age_seconds": 10},
    )
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {"generated_at": "2099-01-01T00:00:00+00:00"})
    monkeypatch.setattr(
        "src.runtime_paths.read_heartbeat",
        lambda: {"updated_at": "2099-01-01T00:00:00+00:00", "running": True},
    )
    monkeypatch.setattr(
        "src.runtime_paths.get_runtime_identity",
        lambda: {
            "app_root": "/tmp/test",
            "data_dir": "/tmp/test/data",
            "db_path": "/tmp/test/data/golf.db",
            "snapshot_path": "/tmp/test/data/live_refresh_snapshot.json",
            "production": False,
        },
    )
    monkeypatch.setattr("src.runtime_paths.get_app_root", lambda: __import__("pathlib").Path("/tmp/test"))
    monkeypatch.setattr(
        "src.runtime_paths.detect_split_brain",
        lambda heartbeat=None: {"split_brain_suspected": False, "reasons": [], "heartbeat_age_seconds": 0},
    )
    monkeypatch.setattr(
        "src.grading_reconciliation.reconcile_grading",
        lambda **kwargs: {
            "status": "discrepancies",
            "events_with_ungraded_positive_ev": 1,
            "orphan_outcomes": 0,
            "events": [
                {"void_positive_ev_picks": 2, "ungraded_positive_ev_picks": 1},
                {"void_positive_ev_picks": 1, "ungraded_positive_ev_picks": 0},
            ],
        },
    )
    monkeypatch.setattr(
        "src.disk_guard.get_disk_state",
        lambda _path: {"free_mb": 12000, "warn_mb": None, "hard_mb": None, "state": "healthy", "path": "/tmp/test"},
    )
    monkeypatch.setattr("src.worker_restart.read_worker_restart_request", lambda: None)

    client = TestClient(app_module.app)
    response = client.get("/api/ops/health")
    grading = response.json()["grading"]
    assert grading["void_positive_ev_picks"] == 3
    assert grading["ungraded_positive_ev_picks"] == 1


def test_ops_grade_job_stores_partial_result(monkeypatch, tmp_db):
    from src.db import get_conn
    from src.ops_jobs import create_job, get_job
    from src.routes.ops_jobs import _run_grade_job

    monkeypatch.setattr(
        "scripts.grade_tournament.grade_tournament",
        lambda event_id, year, event_name=None: {
            "status": "partial",
            "grading_report": {
                "status": "partial",
                "scored_count": 2,
                "voided_count": 1,
                "skipped_count": 0,
                "message": "1 void",
            },
        },
    )

    conn = get_conn()
    job_id = create_job(conn, "grade", {"event_id": "1", "year": 2026})
    conn.close()

    _run_grade_job(job_id, "1", 2026, None)

    conn = get_conn()
    job = get_job(conn, job_id)
    conn.close()
    assert job is not None
    assert job["status"] == "partial"
    assert job["result"]["grading_report"]["voided_count"] == 1
