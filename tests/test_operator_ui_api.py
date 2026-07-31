"""API tests for lightweight operator projections."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import app


NOW = datetime(2026, 7, 31, 16, 0, tzinfo=timezone.utc)


def _snapshot() -> dict:
    section = {
        "source_event_id": "evt-100",
        "event_name": "The Open",
        "course_name": "Royal Test",
        "rankings": [{"player_name": "Champion Player", "rank": 1}],
        "matchup_bets": [{"player_name": "Champion Player", "ev": 0.12}],
        "value_bets": [],
        "leaderboard": [],
        "eligibility": {"verified": True, "code": "field_verified"},
    }
    return {
        "snapshot_id": "snap-100",
        "generated_at": NOW.isoformat(),
        "live_tournament": section,
        "upcoming_tournament": None,
        "lab_live_tournament": None,
        "lab_upcoming_tournament": None,
    }


def _patch_runtime(monkeypatch, snapshot: dict) -> None:
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "split_brain_suspected": False},
    )
    monkeypatch.setattr(
        "src.routes.operator_ui._snapshot_stale_after_seconds",
        lambda: 900,
    )


def test_bootstrap_returns_lightweight_projection(monkeypatch):
    _patch_runtime(monkeypatch, _snapshot())
    client = TestClient(app)

    response = client.get("/api/operator/bootstrap")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "operator-read-model/v1"
    assert body["tracks"]["champion"]["live"]["event_id"] == "evt-100"
    assert "rankings" not in body
    assert len(response.content) < 3_000


def test_board_conditional_get_uses_snapshot_etag(monkeypatch):
    _patch_runtime(monkeypatch, _snapshot())
    client = TestClient(app)

    first = client.get("/api/operator/board?track=champion&mode=live&event_id=evt-100")

    assert first.status_code == 200
    assert first.json()["rankings"] == [{"player_name": "Champion Player", "rank": 1}]
    assert first.headers["etag"]

    second = client.get(
        "/api/operator/board?track=champion&mode=live&event_id=evt-100",
        headers={"If-None-Match": first.headers["etag"]},
    )

    assert second.status_code == 304
    assert second.content == b""


def test_board_challenger_missing_lane_does_not_use_champion(monkeypatch):
    _patch_runtime(monkeypatch, _snapshot())
    client = TestClient(app)

    response = client.get("/api/operator/board?track=challenger&mode=live&event_id=evt-100")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "unavailable"
    assert body["reason"]["code"] == "challenger_lane_unavailable"
    assert body["rankings"] == []
