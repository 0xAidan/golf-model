"""Tests for live snapshot service wiring and provenance."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_run_snapshot_analysis_passes_live_meta_override_and_disables_ai_adjustments(monkeypatch):
    from backtester.strategy import StrategyConfig
    from src.services.live_snapshot_service import run_snapshot_analysis

    captured = {}

    class FakeService:
        def __init__(self, tour="pga", strategy_config=None):
            captured["tour"] = tour
            captured["strategy_config"] = strategy_config

        def run_analysis(self, **kwargs):
            captured["run_analysis_kwargs"] = kwargs
            return {
                "status": "complete",
                "event_name": "Masters Tournament",
                "card_filepath": "output/masters_tournament_20260408.md",
            }

    strategy = StrategyConfig(
        name="verified_baseline_v4.2",
        min_ev=0.08,
        matchup_ev_threshold=0.05,
        w_sub_course_fit=0.45,
        w_sub_form=0.45,
        w_sub_momentum=0.10,
    )

    monkeypatch.setattr(
        "src.strategy_resolution.resolve_runtime_strategy",
        lambda scope="global": (
            strategy,
            {
                "strategy_source": "live",
                "strategy_record_id": 2,
                "strategy_name": "verified_baseline_v4.2",
            },
        ),
    )
    monkeypatch.setattr(
        "src.services.golf_model_service.GolfModelService",
        FakeService,
    )

    result = run_snapshot_analysis(
        tour="pga",
        tournament_name="Masters Tournament",
        course_name="Augusta National Golf Club",
        enable_ai=True,
        mode="full",
    )

    assert captured["tour"] == "pga"
    assert captured["strategy_config"]["name"] == "verified_baseline_v4.2"
    assert captured["run_analysis_kwargs"]["strategy_source"] == "config"
    assert captured["run_analysis_kwargs"]["apply_ai_adjustments"] is False
    assert captured["run_analysis_kwargs"]["strategy_meta_override"]["strategy_source"] == "live"
    assert captured["run_analysis_kwargs"]["strategy_meta_override"]["strategy_name"] == "verified_baseline_v4.2"
    assert result["model_lane"] == "live"
    assert result["output_file"] == "output/masters_tournament_20260408.md"
