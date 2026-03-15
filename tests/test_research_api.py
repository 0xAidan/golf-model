"""Tests for research proposal API endpoints."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_research_run_endpoint(monkeypatch):
    """API should expose a bounded manual research-run endpoint."""
    import app as app_module

    monkeypatch.setattr(
        "backtester.research_cycle.run_research_cycle",
        lambda **kwargs: {
            "cycle_key": "manual:global:42:1",
            "proposals_created": 1,
            "proposals_evaluated": 1,
            "proposals": [],
            "top_candidates": [{"proposal_id": 12, "blended_score": 2.1}],
            "winner": {"proposal_id": 12, "blended_score": 2.1},
            "research_champion_updated": True,
        },
    )

    client = TestClient(app_module.app)
    response = client.post("/api/research/run", json={"max_candidates": 1, "years": [2025], "scope": "global"})

    assert response.status_code == 200
    assert response.json()["proposals_created"] == 1
    assert response.json()["winner"]["proposal_id"] == 12


def test_research_proposals_endpoint(monkeypatch):
    """API should list proposal rows for lightweight review."""
    import app as app_module

    monkeypatch.setattr(
        "backtester.proposals.list_proposals",
        lambda status=None, limit=100: [{"id": 1, "name": "proposal_a", "status": "evaluated"}],
    )

    client = TestClient(app_module.app)
    response = client.get("/api/research/proposals")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["name"] == "proposal_a"
