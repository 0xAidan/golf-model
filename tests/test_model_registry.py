"""Tests for research champion and live weekly model separation."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.db as db

_original_path = db.DB_PATH


def setup_module():
    tmp = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp
    db._DB_INITIALIZED = False
    db.ensure_initialized()


def teardown_module():
    if os.path.exists(db.DB_PATH):
        os.unlink(db.DB_PATH)
    db.DB_PATH = _original_path
    db._DB_INITIALIZED = False


def test_research_champion_does_not_change_live_model():
    from backtester.model_registry import (
        get_live_weekly_model,
        get_research_champion,
        set_research_champion,
    )
    from backtester.strategy import StrategyConfig

    live_before = get_live_weekly_model("global")
    set_research_champion(
        StrategyConfig(name="research_candidate", min_ev=0.08),
        scope="global",
        source="optimizer",
        notes="auto-update research lane only",
    )

    research = get_research_champion("global")
    live_after = get_live_weekly_model("global")

    assert research.name == "research_candidate"
    assert live_after.name == live_before.name


def test_manual_promotion_and_rollback_preserve_audit_history():
    from backtester.model_registry import (
        get_live_weekly_model,
        promote_research_champion_to_live,
        rollback_live_weekly_model,
        set_live_weekly_model,
        set_research_champion,
    )
    from backtester.strategy import StrategyConfig

    set_live_weekly_model(
        StrategyConfig(name="live_v1", min_ev=0.05),
        scope="global",
        promoted_by="manual",
        notes="seed live model",
    )
    set_research_champion(
        StrategyConfig(name="research_v2", min_ev=0.07),
        scope="global",
        source="optimizer",
        notes="better research model",
    )

    promoted = promote_research_champion_to_live(
        scope="global",
        promoted_by="manual-review",
        notes="approved for weekly use",
        enforce_gates=False,
    )
    live_after_promote = get_live_weekly_model("global")
    rollback = rollback_live_weekly_model(
        scope="global",
        promoted_by="manual-review",
        notes="revert to prior live model",
    )
    live_after_rollback = get_live_weekly_model("global")

    assert promoted["strategy"].name == "research_v2"
    assert live_after_promote.name == "research_v2"
    assert rollback["strategy"].name == "live_v1"
    assert live_after_rollback.name == "live_v1"


def test_promotion_gates_can_block_live_promotion(monkeypatch):
    from backtester.model_registry import (
        PromotionGateError,
        promote_research_champion_to_live,
        set_research_champion,
    )
    from backtester.strategy import StrategyConfig

    set_research_champion(
        StrategyConfig(name="research_blocked", min_ev=0.07),
        scope="global",
        source="optimizer",
    )
    monkeypatch.setattr(
        "backtester.model_registry.evaluate_live_promotion_gates",
        lambda scope="global": type(
            "GateResult",
            (),
            {"passed": False, "reasons": ["minimum_bets_not_met"], "metrics": {"total_bets": 42}},
        )(),
    )

    try:
        promote_research_champion_to_live(scope="global", enforce_gates=True)
        assert False, "Expected promotion to be blocked"
    except PromotionGateError as exc:
        assert "minimum_bets_not_met" in exc.result.reasons


def test_upcoming_prediction_uses_resolved_strategy_pipeline(monkeypatch):
    import app as app_module
    from backtester.strategy import StrategyConfig
    from fastapi.testclient import TestClient

    captured = {}

    class FakeService:
        def __init__(self, tour="pga", strategy_config=None):
            captured["strategy_config"] = strategy_config or {}

        def run_analysis(self, **kwargs):
            captured["run_analysis_kwargs"] = kwargs
            return {
                "status": "complete",
                "event_name": "Test Event",
                "field_size": 10,
                "output_file": "output/test.md",
            }

    strat = StrategyConfig(name="live_lane_model", min_ev=0.09)
    monkeypatch.setattr(
        "src.strategy_resolution.resolve_runtime_strategy",
        lambda scope="global": (strat, {"strategy_source": "live", "strategy_name": "live_lane_model"}),
    )
    monkeypatch.setattr("src.services.golf_model_service.GolfModelService", FakeService)

    client = TestClient(app_module.app)
    response = client.post("/api/simple/upcoming-prediction", json={"tour": "pga"})

    assert response.status_code == 200
    assert captured["strategy_config"]["name"] == "live_lane_model"
    assert captured["run_analysis_kwargs"].get("strategy_source") == "config"
    body = response.json()
    assert body.get("model_lane") == "live"
