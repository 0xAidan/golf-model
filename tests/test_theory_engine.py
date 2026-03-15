"""Tests for OpenAI-first theory generation with local fallback."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_generate_candidate_theories_prefers_openai(monkeypatch):
    """When AI is available, theory generation should use it by default."""
    from backtester.strategy import StrategyConfig
    from backtester.theory_engine import generate_candidate_theories

    monkeypatch.setattr("backtester.theory_engine.is_ai_available", lambda: True)
    monkeypatch.setattr(
        "backtester.theory_engine.call_ai",
        lambda *args, **kwargs: {
            "theories": [
                {
                    "title": "Raise EV threshold",
                    "hypothesis": "A slightly higher EV floor may reduce weak bets.",
                    "why_it_may_work": "Recent tests may be overbetting thin edges.",
                    "source_type": "openai",
                    "novelty_score": 0.81,
                    "duplicate_marker": "",
                    "ranking_hint": 0.74,
                    "strategy_overrides": {"min_ev": 0.07, "stat_window": 24},
                }
            ]
        },
    )

    theories = generate_candidate_theories(
        StrategyConfig(name="baseline", min_ev=0.05),
        max_candidates=1,
        scope="global",
        years=[2024, 2025],
    )

    assert len(theories) == 1
    theory = theories[0]
    assert theory["source_type"] == "openai"
    assert theory["title"] == "Raise EV threshold"
    assert theory["strategy"].min_ev == 0.07
    assert theory["why_it_may_work"] == "Recent tests may be overbetting thin edges."


def test_generate_candidate_theories_falls_back_to_local_neighbors(monkeypatch):
    """If AI is unavailable, local theory generation should still work."""
    from backtester.strategy import StrategyConfig
    from backtester.theory_engine import generate_candidate_theories

    monkeypatch.setattr("backtester.theory_engine.is_ai_available", lambda: False)
    monkeypatch.setattr(
        "backtester.theory_engine.generate_neighbor_strategies",
        lambda base, n=5, perturbation=0.03: [
            StrategyConfig(name="neighbor_a", min_ev=0.06),
            StrategyConfig(name="neighbor_b", min_ev=0.07),
        ],
    )

    theories = generate_candidate_theories(
        StrategyConfig(name="baseline", min_ev=0.05),
        max_candidates=2,
        scope="global",
        years=[2024, 2025],
    )

    assert len(theories) == 2
    assert theories[0]["source_type"] == "fallback_neighbor"
    assert theories[0]["strategy"].min_ev == 0.06
    assert theories[0]["why_it_may_work"]
