"""API tests for model registry and optimizer runtime controls."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_model_registry_promotion_endpoint(monkeypatch):
    import app as app_module
    from backtester.strategy import StrategyConfig

    monkeypatch.setattr(
        "backtester.model_registry.promote_research_champion_to_live",
        lambda **kwargs: {"strategy": StrategyConfig(name="live_promoted", min_ev=0.07)},
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/model-registry/promote-research-to-live",
        json={"scope": "global", "reviewer": "manual", "notes": "ship it"},
    )

    assert response.status_code == 200
    assert response.json()["live_weekly_model"]["name"] == "live_promoted"


def test_model_registry_promotion_endpoint_handles_guardrail_block(monkeypatch):
    import app as app_module

    class FakePromotionError(ValueError):
        def __init__(self):
            self.result = type(
                "GateResult",
                (),
                {"reasons": ["minimum_bets_not_met"], "metrics": {"total_bets": 12}},
            )()
            super().__init__("blocked")

    monkeypatch.setattr(
        "backtester.model_registry.promote_research_champion_to_live",
        lambda **kwargs: (_ for _ in ()).throw(FakePromotionError()),
    )
    monkeypatch.setattr(
        "backtester.model_registry.PromotionGateError",
        FakePromotionError,
    )
    monkeypatch.setattr(
        "backtester.model_registry.evaluate_live_promotion_gates",
        lambda scope="global": type("GateResult", (), {"passed": False, "reasons": ["minimum_bets_not_met"], "metrics": {"total_bets": 12}})(),
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/model-registry/promote-research-to-live",
        json={"scope": "global", "reviewer": "manual", "notes": "ship it"},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["decision"] == "blocked_by_guardrails"
    assert "minimum_bets_not_met" in payload["blocked_reason"]


def test_optimizer_start_stop_and_status_endpoints(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        "backtester.optimizer_runtime.start_continuous_optimizer",
        lambda **kwargs: {"running": True, "run_count": 0, "last_cycle_key": None},
    )
    monkeypatch.setattr(
        "backtester.optimizer_runtime.stop_continuous_optimizer",
        lambda: {"running": False, "run_count": 2, "last_cycle_key": "cycle-2"},
    )
    monkeypatch.setattr(
        "backtester.optimizer_runtime.get_optimizer_status",
        lambda: {"running": True, "run_count": 1, "last_cycle_key": "cycle-1"},
    )
    monkeypatch.setattr(
        "src.datagolf.get_datagolf_throttle_status",
        lambda: {"requests_in_window": 5, "max_requests": 45, "cached_entries": 3},
    )

    client = TestClient(app_module.app)

    start_response = client.post("/api/optimizer/start", json={"interval_seconds": 60, "max_candidates": 2})
    status_response = client.get("/api/optimizer/status")
    stop_response = client.post("/api/optimizer/stop")

    assert start_response.status_code == 200
    assert start_response.json()["optimizer"]["running"] is True
    assert status_response.status_code == 200
    assert status_response.json()["datagolf"]["max_requests"] == 45
    assert stop_response.status_code == 200
    assert stop_response.json()["optimizer"]["running"] is False


def test_autoresearch_batch_endpoint(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        "backtester.research_cycle.run_research_cycle",
        lambda **kwargs: {
            "cycle_key": "cycle",
            "winner": {"strategy_name": "candidate_a", "blended_score": 3.2},
            "promotion_decision": "kept_current_research_champion",
        },
    )

    client = TestClient(app_module.app)
    response = client.post(
        "/api/autoresearch/run-batch",
        json={"scope": "global", "cycles": 2, "max_candidates": 2, "years": [2024, 2025]},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "complete"
    assert payload["cycles"] == 2
    assert len(payload["runs"]) == 2
    assert payload["best_winner"]["strategy_name"] == "candidate_a"
