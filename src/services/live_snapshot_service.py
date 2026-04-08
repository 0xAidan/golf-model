"""
Shared helpers for always-on dashboard snapshot generation.
"""

from __future__ import annotations

from typing import Any

VALID_TOURS = {"pga", "euro", "kft", "alt"}


def _sanitize_tour(tour: str | None) -> str:
    candidate = str(tour or "pga").strip().lower()
    return candidate if candidate in VALID_TOURS else "pga"


def run_snapshot_analysis(
    *,
    tour: str = "pga",
    tournament_name: str | None = None,
    course_name: str | None = None,
    mode: str = "full",
    enable_ai: bool = False,
    enable_backfill: bool = False,
) -> dict[str, Any]:
    from src.services.golf_model_service import GolfModelService
    from src.strategy_resolution import build_pipeline_strategy_config, resolve_runtime_strategy

    strategy, strategy_meta = resolve_runtime_strategy("global")
    pipeline_cfg = build_pipeline_strategy_config(strategy)
    service = GolfModelService(tour=_sanitize_tour(tour), strategy_config=pipeline_cfg)
    result = service.run_analysis(
        tournament_name=tournament_name,
        course_name=course_name,
        enable_ai=enable_ai,
        enable_backfill=enable_backfill,
        include_methodology=False,
        mode=mode,
        strategy_source="config",
        strategy_meta_override=strategy_meta,
        apply_ai_adjustments=False,
    )
    if not result.get("output_file") and result.get("card_filepath"):
        result["output_file"] = result["card_filepath"]
    result["model_lane"] = strategy_meta.get("strategy_source", "default")
    result["strategy_meta"] = strategy_meta
    result["live_model_name"] = strategy.name or pipeline_cfg.get("name", "strategy")
    return result

