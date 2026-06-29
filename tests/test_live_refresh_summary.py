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
