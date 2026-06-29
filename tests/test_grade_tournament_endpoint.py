"""Tests for POST /api/grade-tournament."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_grade_tournament_endpoint_returns_complete_report(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "scripts.grade_tournament.grade_tournament",
        lambda event_id, year, event_name=None: {
            "status": "complete",
            "event_id": event_id,
            "year": year,
            "steps": {"scoring": {"status": "ok"}},
        },
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/grade-tournament",
        json={"event_id": "34", "year": 2026, "event_name": "Travelers Championship"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["event_id"] == "34"


def test_grade_tournament_endpoint_maps_error_status_to_422(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "scripts.grade_tournament.grade_tournament",
        lambda event_id, year, event_name=None: {
            "status": "error",
            "message": "No results returned from DG API",
            "event_id": event_id,
            "year": year,
        },
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/grade-tournament",
        json={"event_id": "34", "year": 2026},
    )

    assert response.status_code == 422
    assert response.json()["status"] == "error"


def test_grade_tournament_endpoint_returns_500_on_exception(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)

    def _boom(*args, **kwargs):
        raise RuntimeError("retune failed")

    monkeypatch.setattr("scripts.grade_tournament.grade_tournament", _boom)

    client = TestClient(app_module.app)
    response = client.post(
        "/api/grade-tournament",
        json={"event_id": "34", "year": 2026},
    )

    assert response.status_code == 500
    assert response.json()["status"] == "error"
