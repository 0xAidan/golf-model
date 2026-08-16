"""Snapshot/summary APIs must read JSON even when SQLite is dead."""

import sqlite3

from fastapi.testclient import TestClient


def test_live_refresh_summary_without_sqlite(monkeypatch, tmp_path):
    import app as app_module

    snapshot = {
        "generated_at": "2099-01-01T00:00:00+00:00",
        "event_context": {"event_name": "FedEx St. Jude Championship"},
        "live_tournament": {"event_name": "FedEx St. Jude Championship", "active": True},
    }

    def _boom():
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr("src.db.ensure_initialized", _boom)
    monkeypatch.setattr(
        "app.live_db_status_fields",
        lambda timeout_seconds=5.0: {
            "db_ok": False,
            "db_state": "corrupt",
            "rebuild_state": "rebuilding",
            "db_error": "malformed",
        },
    )
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": False, "snapshot_age_seconds": 120, "split_brain_suspected": False},
    )
    monkeypatch.setattr("src.runtime_paths.read_heartbeat", lambda: {"phase": "db_malformed"})
    monkeypatch.setattr("backtester.dashboard_runtime.manual_trigger_pending", lambda: False)

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["db_ok"] is False
    assert body["snapshot"]["event_context"]["event_name"] == "FedEx St. Jude Championship"
    assert body["data_state"] == "stale"
