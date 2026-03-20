"""
Single source of truth for which StrategyConfig runs in production (CLI, web, workers).

Priority: live weekly model -> research champion -> active_strategy (experiments) -> default.
"""

from __future__ import annotations

import logging
from typing import Any

from backtester.experiments import get_active_strategy
from backtester.model_registry import get_live_weekly_model_record, get_research_champion_record
from backtester.strategy import StrategyConfig

logger = logging.getLogger(__name__)


def strategy_from_record(record: dict | None) -> StrategyConfig | None:
    """Parse a model-registry row into StrategyConfig."""
    if not record:
        return None
    strategy_json = record.get("strategy_config_json")
    if not strategy_json:
        return None
    try:
        return StrategyConfig.from_json(strategy_json)
    except Exception:
        logger.warning("Failed to parse strategy config JSON, skipping", exc_info=True)
        return None


def resolve_runtime_strategy(scope: str = "global") -> tuple[StrategyConfig, dict[str, Any]]:
    """
    Resolve strategy with explicit fallback (same chain as run_predictions CLI).

    Returns (strategy, meta) where meta includes strategy_source and strategy_name.
    """
    live_record = get_live_weekly_model_record(scope)
    live_strategy = strategy_from_record(live_record)
    if live_strategy:
        return live_strategy, {
            "strategy_source": "live",
            "strategy_record_id": live_record.get("id") if live_record else None,
            "strategy_name": live_strategy.name or "live_weekly_model",
        }

    research_record = get_research_champion_record(scope)
    research_strategy = strategy_from_record(research_record)
    if research_strategy:
        return research_strategy, {
            "strategy_source": "research_champion",
            "strategy_record_id": research_record.get("id") if research_record else None,
            "strategy_name": research_strategy.name or "research_champion",
        }

    active_strategy = get_active_strategy(scope)
    if active_strategy:
        return active_strategy, {
            "strategy_source": "active_strategy",
            "strategy_record_id": None,
            "strategy_name": active_strategy.name or "active_strategy",
        }

    default_strategy = StrategyConfig(name="default")
    return default_strategy, {
        "strategy_source": "default",
        "strategy_record_id": None,
        "strategy_name": "default",
    }


def map_strategy_to_runtime_settings(strategy: StrategyConfig) -> dict[str, Any]:
    """Map StrategyConfig to live pipeline knobs (blend weights, EV, markets)."""
    allowed_markets: set[str] = set()
    market_map = {
        "win": "outright",
        "top_5": "top5",
        "top_10": "top10",
        "top_20": "top20",
        "frl": "frl",
        "make_cut": "make_cut",
    }
    for market in strategy.markets or []:
        mapped = market_map.get(market)
        if mapped:
            allowed_markets.add(mapped)

    return {
        "blend_weights": {
            "course_fit": float(strategy.w_sub_course_fit),
            "form": float(strategy.w_sub_form),
            "momentum": float(strategy.w_sub_momentum),
        },
        "ev_threshold": float(strategy.min_ev),
        "kelly_fraction": float(strategy.kelly_fraction),
        "allowed_markets": allowed_markets or {"outright", "top5", "top10", "top20"},
    }


def build_pipeline_strategy_config(strategy: StrategyConfig) -> dict[str, Any]:
    """
    Dict for GolfModelService / value layer: merged weights + thresholds.

    Includes top-level w_sub_* so compute_composite can apply PIT-aligned weights
    when strategy_config is passed (see composite.compute_composite).
    """
    market_map = {
        "win": "outright",
        "top_5": "top5",
        "top_10": "top10",
        "top_20": "top20",
        "frl": "frl",
        "make_cut": "make_cut",
    }
    allowed_markets = {market_map.get(m, m) for m in (strategy.markets or [])}
    return {
        "name": strategy.name or "strategy",
        "weights": {
            "course_fit": float(strategy.w_sub_course_fit),
            "form": float(strategy.w_sub_form),
            "momentum": float(strategy.w_sub_momentum),
        },
        "w_sub_course_fit": float(strategy.w_sub_course_fit),
        "w_sub_form": float(strategy.w_sub_form),
        "w_sub_momentum": float(strategy.w_sub_momentum),
        "ev_threshold": float(strategy.min_ev),
        "kelly_fraction": float(strategy.kelly_fraction),
        "matchup_ev_threshold": float(strategy.matchup_ev_threshold),
        "allowed_markets": allowed_markets or {"outright", "top5", "top10", "top20"},
    }
