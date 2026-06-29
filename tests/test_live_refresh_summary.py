"""Tests for live-refresh summary SWR endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import app


def test_live_refresh_summary_returns_last_good_without_blocking(monkeypatch):
    client = TestClient(app)

    fake_snapshot = {
        "generated_at": "2026-01-01T12:00:00+00:00",
        "live_tournament": {"active": True},
        "upcoming_tournament": {},
    }

    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: fake_snapshot,
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "split_brain_suspected": False},
    )

    resp = client.get("/api/live-refresh/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("snapshot") is not None
    assert body.get("data_state") in {"fresh", "stale", "split_brain"}


def test_live_refresh_summary_stale_operator_message_honest(monkeypatch):
    client = TestClient(app)
    from datetime import datetime, timedelta, timezone

    stale_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    fake_snapshot = {
        "generated_at": stale_at,
        "live_tournament": {"active": False},
        "upcoming_tournament": {"event_name": "Old Event"},
    }

    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: fake_snapshot,
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "split_brain_suspected": False, "refresh_state": "idle"},
    )
    monkeypatch.setattr("backtester.dashboard_runtime.manual_trigger_pending", lambda: False)
    monkeypatch.setattr("src.runtime_paths.read_heartbeat", lambda: {"refresh_state": "idle", "running": True})

    resp = client.get("/api/live-refresh/summary")
    body = resp.json()
    assert body.get("data_state") == "stale"
    message = body.get("operator_message") or ""
    assert "refreshing in background" not in message.lower()
    assert "refresh" in message.lower()


def test_live_refresh_summary_stale_refresh_active_message(monkeypatch):
    client = TestClient(app)
    from datetime import datetime, timedelta, timezone

    stale_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    fake_snapshot = {
        "generated_at": stale_at,
        "live_tournament": {"active": False},
        "upcoming_tournament": {"event_name": "Old Event"},
    }

    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: fake_snapshot,
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {
            "running": True,
            "split_brain_suspected": False,
            "refresh_state": "running",
            "progress": {"refresh_state": "running"},
        },
    )
    monkeypatch.setattr("backtester.dashboard_runtime.manual_trigger_pending", lambda: True)
    monkeypatch.setattr("src.runtime_paths.read_heartbeat", lambda: {"refresh_state": "running", "running": True})

    resp = client.get("/api/live-refresh/summary")
    body = resp.json()
    message = body.get("operator_message") or ""
    assert "queued" in message.lower() or "progress" in message.lower()
