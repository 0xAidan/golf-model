"""Tests for live refresh policy and API endpoints."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


def test_live_refresh_policy_detects_live_window():
    from src.live_refresh_policy import detect_window_mode

    dt = datetime(2026, 4, 9, 13, 0, tzinfo=ZoneInfo("America/New_York"))  # Thursday 1pm ET
    assert detect_window_mode(now=dt) == "live_window"


def test_live_refresh_policy_detects_off_window():
    from src.live_refresh_policy import detect_window_mode

    dt = datetime(2026, 4, 7, 11, 0, tzinfo=ZoneInfo("America/New_York"))  # Tuesday 11am ET
    assert detect_window_mode(now=dt) == "off_window"


def test_live_refresh_status_endpoint(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "cadence_mode": "live_window"},
    )
    monkeypatch.setattr(
        "src.autoresearch_settings.get_settings",
        lambda: {"live_refresh": {"enabled": True, "tour": "pga"}},
    )

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"]["running"] is True
    assert body["settings"]["tour"] == "pga"


def test_live_refresh_snapshot_endpoint_handles_missing_snapshot(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {})

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["snapshot"] is None


def test_live_refresh_start_and_stop_endpoints(monkeypatch):
    import app as app_module

    calls = {"set_settings": []}

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "src.autoresearch_settings.get_settings",
        lambda: {"live_refresh": {"enabled": False, "tour": "pga"}},
    )
    monkeypatch.setattr(
        "src.autoresearch_settings.set_settings",
        lambda payload: calls["set_settings"].append(payload) or payload,
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.start_live_refresh",
        lambda tour="pga": {"running": True, "tour": tour},
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.stop_live_refresh",
        lambda: {"running": False},
    )

    client = TestClient(app_module.app)
    start_response = client.post("/api/live-refresh/start", json={"tour": "pga"})
    stop_response = client.post("/api/live-refresh/stop")

    assert start_response.status_code == 200
    assert start_response.json()["status"]["running"] is True
    assert stop_response.status_code == 200
    assert stop_response.json()["status"]["running"] is False
    assert calls["set_settings"], "Expected settings updates when starting/stopping live refresh."

