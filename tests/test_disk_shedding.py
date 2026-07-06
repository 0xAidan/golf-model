"""Tests for D3a disk shedding behavior."""

from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_disk_state_levels(monkeypatch):
    from src.disk_guard import disk_state, get_disk_state

    monkeypatch.setenv("DISK_FREE_MB_WARN", "1024")
    monkeypatch.setenv("DISK_FREE_MB_HARD", "512")

    monkeypatch.setattr("shutil.disk_usage", lambda _path: SimpleNamespace(free=2 * 1024 * 1024 * 1024))
    assert disk_state("/tmp/test") == "ok"

    monkeypatch.setattr("shutil.disk_usage", lambda _path: SimpleNamespace(free=700 * 1024 * 1024))
    assert disk_state("/tmp/test") == "warn"

    monkeypatch.setattr("shutil.disk_usage", lambda _path: SimpleNamespace(free=400 * 1024 * 1024))
    assert disk_state("/tmp/test") == "hard"

    snapshot = get_disk_state("/tmp/test")
    assert snapshot["state"] == "critical"
    assert snapshot["guard_state"] == "hard"


def test_persist_snapshot_tail_sheds_when_disk_hard_and_keeps_grading(monkeypatch):
    from backtester import dashboard_runtime

    calls: list[str] = []

    monkeypatch.setattr(dashboard_runtime, "disk_state", lambda _path: "hard")
    monkeypatch.setattr(
        "src.event_pick_freeze.ensure_event_grading_readiness",
        lambda *args, **kwargs: calls.append("grading") or {"status": "ready"},
    )
    monkeypatch.setattr(
        dashboard_runtime.db,
        "store_live_snapshot_sections",
        lambda *args, **kwargs: calls.append("history") or 1,
    )
    monkeypatch.setattr(
        dashboard_runtime.db,
        "store_market_prediction_rows",
        lambda *args, **kwargs: calls.append("market") or 2,
    )
    monkeypatch.setattr(
        dashboard_runtime,
        "_build_market_prediction_rows",
        lambda **kwargs: calls.append("build_rows") or [{"row": kwargs["section_name"]}],
    )
    monkeypatch.setattr(
        "src.pick_ledger.persist_pick_ledger_from_market_rows",
        lambda *args, **kwargs: calls.append("ledger") or 3,
    )

    snapshot = {
        "live_tournament": {
            "source_event_id": "evt-1",
            "year": 2026,
            "event_name": "Test Event",
        },
        "upcoming_tournament": {},
        "legacy_tournament": {},
        "diagnostics": {},
    }
    dashboard_runtime._persist_snapshot_tail(
        snapshot=snapshot,
        snapshot_id="snap-1",
        generated_at="2099-01-01T00:00:00+00:00",
        tour="pga",
        cadence_mode="in_window",
        live_result={},
        live_diag={},
        upcoming_result={},
        legacy_result={},
        lab_rows_extra=[],
    )

    assert calls == ["grading"]
    assert snapshot["diagnostics"]["disk_guard"] == "shedding"
    assert snapshot["diagnostics"]["history_rows_written"] == 0
    assert snapshot["diagnostics"]["market_rows_written"] == 0
    assert snapshot["diagnostics"]["pick_ledger_written"] == 0
    assert snapshot["diagnostics"]["grading_readiness"] == {"status": "ready"}


def test_persist_snapshot_tail_writes_when_disk_ok(monkeypatch):
    from backtester import dashboard_runtime

    calls: list[str] = []

    monkeypatch.setattr(dashboard_runtime, "disk_state", lambda _path: "ok")
    monkeypatch.setattr(
        dashboard_runtime.db,
        "store_live_snapshot_sections",
        lambda *args, **kwargs: calls.append("history") or 11,
    )
    monkeypatch.setattr(
        dashboard_runtime,
        "_build_market_prediction_rows",
        lambda **kwargs: [{"section": kwargs["section_name"]}],
    )
    monkeypatch.setattr(
        dashboard_runtime.db,
        "store_market_prediction_rows",
        lambda rows: calls.append(f"market:{len(rows)}") or len(rows),
    )
    monkeypatch.setattr(
        "src.pick_ledger.persist_pick_ledger_from_market_rows",
        lambda rows, **kwargs: calls.append(f"ledger:{len(rows)}") or len(rows),
    )
    monkeypatch.setattr(
        "src.event_pick_freeze.ensure_event_grading_readiness",
        lambda *args, **kwargs: calls.append("grading") or {"status": "ready"},
    )

    snapshot = {
        "live_tournament": {
            "source_event_id": "evt-1",
            "year": 2026,
            "event_name": "Test Event",
        },
        "upcoming_tournament": {},
        "legacy_tournament": {},
        "diagnostics": {},
    }
    dashboard_runtime._persist_snapshot_tail(
        snapshot=snapshot,
        snapshot_id="snap-1",
        generated_at="2099-01-01T00:00:00+00:00",
        tour="pga",
        cadence_mode="in_window",
        live_result={},
        live_diag={},
        upcoming_result={},
        legacy_result={},
        lab_rows_extra=[{"section": "lab_live"}],
    )

    assert calls == ["history", "market:4", "ledger:4", "grading"]
    assert snapshot["diagnostics"]["history_rows_written"] == 11
    assert snapshot["diagnostics"]["market_rows_written"] == 4
    assert snapshot["diagnostics"]["pick_ledger_written"] == 4
    assert snapshot["diagnostics"].get("disk_guard") is None


def test_ops_health_reports_disk_floor_breached(monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "snapshot_age_seconds": 10},
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: {"generated_at": "2099-01-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        "src.runtime_paths.read_heartbeat",
        lambda: {"updated_at": "2099-01-01T00:00:00+00:00", "running": True},
    )
    monkeypatch.setattr(
        "src.runtime_paths.get_runtime_identity",
        lambda: {
            "app_root": str(tmp_path),
            "data_dir": str(tmp_path),
            "db_path": str(tmp_path / "golf.db"),
            "snapshot_path": str(tmp_path / "snapshot.json"),
            "production": False,
        },
    )
    monkeypatch.setattr("src.runtime_paths.get_app_root", lambda: tmp_path)
    monkeypatch.setattr(
        "src.runtime_paths.detect_split_brain",
        lambda heartbeat=None: {
            "split_brain_suspected": False,
            "reasons": [],
            "heartbeat_age_seconds": 0,
        },
    )
    monkeypatch.setattr(
        "src.grading_reconciliation.reconcile_grading",
        lambda **kwargs: {"status": "ok", "events_with_ungraded_positive_ev": 0, "orphan_outcomes": 0},
    )
    monkeypatch.setattr(
        "src.disk_guard.get_disk_state",
        lambda _path: {
            "free_mb": 400,
            "warn_mb": 1024,
            "hard_mb": 512,
            "state": "critical",
            "guard_state": "hard",
            "path": str(tmp_path),
        },
    )
    monkeypatch.setattr("src.worker_restart.read_worker_restart_request", lambda: None)

    client = TestClient(app_module.app)
    response = client.get("/api/ops/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["summary"] == "disk_floor_breached"
