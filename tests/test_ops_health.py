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
        "src.runtime_paths.detect_split_brain",
        lambda heartbeat=None: {
            "split_brain_suspected": False,
            "reasons": [],
            "identity": {"app_root": "/tmp/test"},
            "heartbeat": heartbeat,
            "heartbeat_age_seconds": 0,
        },
    )

    client = TestClient(app_module.app)
    response = client.get("/api/ops/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["identity"]["app_root"] == "/tmp/test"
    assert body["live_refresh"]["running"] is True
