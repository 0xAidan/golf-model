import pytest


def test_promotion_policy_blocks_without_holdout(monkeypatch):
    from backtester import model_registry
    from backtester.strategy import StrategyConfig

    monkeypatch.setattr(model_registry, "get_research_champion_record", lambda scope="global": {"id": 1, "strategy": StrategyConfig(name="x")})
    monkeypatch.setattr(
        model_registry,
        "evaluate_live_promotion_gates",
        lambda scope="global": type("Gate", (), {"passed": False, "reasons": ["minimum_bets_not_met"], "metrics": {"total_bets": 1}})(),
    )

    with pytest.raises(model_registry.PromotionGateError):
        model_registry.promote_research_champion_to_live(scope="global", enforce_gates=True)

