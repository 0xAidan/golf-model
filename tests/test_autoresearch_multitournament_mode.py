import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_autoresearch_batch_runs_multiple_cycles(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        "backtester.research_cycle.run_research_cycle",
        lambda **kwargs: {"cycle_key": "x", "winner": {"blended_score": 1.0, "strategy_name": "candidate"}},
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/autoresearch/run-batch",
        json={"scope": "global", "cycles": 3, "max_candidates": 1, "years": [2024, 2025]},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["cycles"] == 3
    assert len(payload["runs"]) == 3

