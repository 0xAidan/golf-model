"""
Shared helpers for always-on dashboard snapshot generation.
"""

from __future__ import annotations

from typing import Any

VALID_TOURS = {"pga", "euro", "kft", "alt"}


def _sanitize_tour(tour: str | None) -> str:
    candidate = str(tour or "pga").strip().lower()
    return candidate if candidate in VALID_TOURS else "pga"


def run_lab_snapshot_analysis(
    *,
    tour: str = "pga",
    event_id: str | None = None,
    tournament_name: str | None = None,
    course_name: str | None = None,
    mode: str = "full",
    enable_ai: bool = False,
    enable_backfill: bool = False,
    champion_path: str | None = None,
) -> dict[str, Any]:
    """
    Cockpit Lab lane only: promoted matchup-lab champion (trial 327), not production strategy.
    """
    from src.lab_champion import (
        build_lab_pipeline_config,
        lab_champion_meta,
        load_lab_champion_strategy,
    )
    from src.services.golf_model_service import GolfModelService
    from src import config

    strategy = load_lab_champion_strategy(path=champion_path)
    pipeline_cfg = build_lab_pipeline_config(strategy, path=champion_path)
    resolved_variant = str(strategy.model_variant or "v5").strip().lower()
    if resolved_variant not in config.ALLOWED_MODEL_VARIANTS:
        resolved_variant = "v5"

    try:
        service = GolfModelService(
            tour=_sanitize_tour(tour),
            strategy_config=pipeline_cfg,
            model_variant=resolved_variant,
        )
    except TypeError:
        service = GolfModelService(tour=_sanitize_tour(tour), strategy_config=pipeline_cfg)

    from src.track_registry import compute_config_hash

    strategy_meta = {
        "strategy_source": "lab_champion",
        "strategy_name": strategy.name or "lab_champion",
        "strategy_record_id": None,
        "model_variant": resolved_variant,
        "track": "lab",
        "config_hash": compute_config_hash(resolved_variant, pipeline_cfg),
        **lab_champion_meta(path=champion_path),
    }
    result = service.run_analysis(
        event_id=event_id,
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
    result["model_lane"] = "lab_champion"
    result["model_variant"] = resolved_variant
    result["strategy_meta"] = strategy_meta
    result["live_model_name"] = strategy.name or pipeline_cfg.get("name", "lab_champion")
    return result


def run_snapshot_analysis(
    *,
    tour: str = "pga",
    event_id: str | None = None,
    tournament_name: str | None = None,
    course_name: str | None = None,
    mode: str = "full",
    enable_ai: bool = False,
    enable_backfill: bool = False,
    model_variant: str | None = None,
) -> dict[str, Any]:
    from src.services.golf_model_service import GolfModelService
    from src.strategy_resolution import build_pipeline_strategy_config, resolve_runtime_strategy
    from src import config

    resolved_variant = str(model_variant or config.DEFAULT_MODEL_VARIANT).strip().lower()
    if resolved_variant not in config.ALLOWED_MODEL_VARIANTS:
        resolved_variant = config.DEFAULT_MODEL_VARIANT

    from src.track_registry import compute_config_hash

    strategy, strategy_meta = resolve_runtime_strategy("global")
    pipeline_cfg = build_pipeline_strategy_config(strategy)
    try:
        service = GolfModelService(
            tour=_sanitize_tour(tour),
            strategy_config=pipeline_cfg,
            model_variant=resolved_variant,
        )
    except TypeError:
        # Backward-compat for tests or lightweight fakes that don't accept model_variant yet.
        service = GolfModelService(tour=_sanitize_tour(tour), strategy_config=pipeline_cfg)
    strategy_meta = dict(strategy_meta or {})
    strategy_meta["model_variant"] = resolved_variant
    strategy_meta["track"] = "dashboard"
    strategy_meta["config_hash"] = compute_config_hash(resolved_variant, pipeline_cfg)
    result = service.run_analysis(
        event_id=event_id,
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
    result["model_variant"] = resolved_variant
    result["strategy_meta"] = strategy_meta
    result["live_model_name"] = strategy.name or pipeline_cfg.get("name", "strategy")
    return result

