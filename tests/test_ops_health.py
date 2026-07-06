"""Tests for ops health endpoint."""

from fastapi.testclient import TestClient


def test_ops_health_endpoint(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "snapshot_age_seconds": 10},
    )
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {"generated_at": "2099-01-01T00:00:00+00:00"})
    monkeypatch.setattr(
        "src.runtime_paths.read_heartbeat",
        lambda: {
            "app_root": "/tmp/test",
            "data_dir": "/tmp/test/data",
            "snapshot_path": "/tmp/test/data/live_refresh_snapshot.json",
            "updated_at": "2099-01-01T00:00:00+00:00",
            "running": True,
        },
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
    monkeypatch.setattr(
        "src.runtime_paths.get_app_root",
        lambda: __import__("pathlib").Path("/tmp/test"),
    )
    monkeypatch.setattr(
        "src.runtime_paths.detect_split_brain",
        lambda heartbeat=None: {
            "split_brain_suspected": False,
            "reasons": [],
            "identity": {"app_root": "/tmp/test"},
            "heartbeat": heartbeat,
            "heartbeat_age_seconds": 0,
        },
    )
    monkeypatch.setattr(
        "src.grading_reconciliation.reconcile_grading",
        lambda **kwargs: {
            "status": "ok",
            "events_with_ungraded_positive_ev": 0,
            "orphan_outcomes": 0,
        },
    )
    monkeypatch.setattr(
        "src.disk_guard.get_disk_state",
        lambda _path: {
            "free_mb": 12000,
            "warn_mb": None,
            "hard_mb": None,
            "state": "healthy",
            "path": "/tmp/test",
        },
    )
    monkeypatch.setattr("src.worker_restart.read_worker_restart_request", lambda: None)

    client = TestClient(app_module.app)
    response = client.get("/api/ops/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["identity"]["app_root"] == "/tmp/test"
    assert body["live_refresh"]["running"] is True
    assert body["grading"]["status"] == "ok"
    assert body["disk"]["state"] == "healthy"


def test_ops_health_includes_persisted_auto_grade(monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {
            "running": True,
            "snapshot_age_seconds": 10,
            "last_auto_grade_at": "2099-01-01T00:00:00+00:00",
            "last_auto_grade_status": {"status": "complete"},
        },
    )
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {"generated_at": "2099-01-01T00:00:00+00:00"})
    monkeypatch.setattr(
        "src.runtime_paths.read_heartbeat",
        lambda: {
            "updated_at": "2099-01-01T00:00:00+00:00",
            "running": True,
        },
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
        lambda _path: {"free_mb": 12000, "warn_mb": 10240, "hard_mb": 5120, "state": "healthy", "path": str(tmp_path)},
    )
    monkeypatch.setattr("src.worker_restart.read_worker_restart_request", lambda: None)

    client = TestClient(app_module.app)
    response = client.get("/api/ops/health")
    body = response.json()
    assert body["live_refresh"]["last_auto_grade_at"] == "2099-01-01T00:00:00+00:00"


def test_post_worker_restart_queues_request(monkeypatch):
    import app as app_module

    queued: dict = {}

    def _queue(*, requested_by: str = "api"):
        queued["requested_by"] = requested_by
        return {
            "request_id": "req-1",
            "requested_at": "2099-01-01T00:00:00+00:00",
            "requested_by": requested_by,
            "status": "pending",
        }

    monkeypatch.setattr("src.worker_restart.request_worker_restart", _queue)

    client = TestClient(app_module.app)
    response = client.post("/api/ops/worker/restart", json={"requested_by": "system-page"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "queued"
    assert queued["requested_by"] == "system-page"
