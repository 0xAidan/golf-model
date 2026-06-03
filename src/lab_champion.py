"""Load promoted lab matchup champion (Optuna trial 327) for the Cockpit Lab lane only."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from backtester.strategy import StrategyConfig
from src.strategy_resolution import build_pipeline_strategy_config

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CHAMPION_PATH = _REPO_ROOT / "config" / "lab_matchup_champion_trial327.json"


@lru_cache(maxsize=4)
def _load_champion_bundle(path: str | None = None) -> dict[str, Any]:
    champion_path = Path(path) if path else _DEFAULT_CHAMPION_PATH
    if not champion_path.is_file():
        raise FileNotFoundError(f"Lab champion config not found: {champion_path}")
    return json.loads(champion_path.read_text(encoding="utf-8"))


def load_lab_champion_strategy(*, path: str | None = None) -> StrategyConfig:
    """StrategyConfig for lab snapshot recompute (matchup-lab robust winner)."""
    bundle = _load_champion_bundle(path)
    raw = dict(bundle.get("strategy") or {})
    raw.setdefault("name", bundle.get("id", "lab_champion"))
    return StrategyConfig(**raw)


def build_lab_pipeline_config(strategy: StrategyConfig, *, path: str | None = None) -> dict[str, Any]:
    """
    Pipeline dict for GolfModelService: composite blend, matchup knobs, SG weights, filters.
    """
    bundle = _load_champion_bundle(path)
    pipeline = build_pipeline_strategy_config(strategy)
    pipeline["lab_champion_id"] = str(bundle.get("id") or strategy.name)
    pipeline["platt_a"] = float(strategy.platt_a)
    pipeline["platt_b"] = float(strategy.platt_b)
    pipeline["min_composite_gap"] = float(strategy.min_composite_gap)
    pipeline["max_win_prob_cap"] = float(strategy.max_win_prob_cap)
    pipeline["dg_matchup_blend_weight"] = float(strategy.dg_matchup_blend_weight)
    pipeline["model_matchup_blend_weight"] = float(strategy.model_matchup_blend_weight)
    pipeline["w_sub_course_fit"] = float(strategy.w_sub_course_fit)
    pipeline["w_sub_form"] = float(strategy.w_sub_form)
    pipeline["w_sub_momentum"] = float(strategy.w_sub_momentum)
    filters = dict(bundle.get("matchup_filters") or {})
    pipeline["matchup_filters"] = filters
    sg = dict(bundle.get("sg_weights") or {})
    if sg:
        pipeline["sg_weights"] = sg
    return pipeline


def lab_champion_meta(*, path: str | None = None) -> dict[str, Any]:
    bundle = _load_champion_bundle(path)
    return {
        "lab_champion_id": bundle.get("id"),
        "lab_champion_study": bundle.get("study"),
        "lab_champion_primary_roi_pct": bundle.get("primary_roi_pct"),
        "lab_champion_holdout_roi_pct": bundle.get("holdout_roi_pct"),
    }


def invalidate_lab_champion_cache() -> None:
    """Test helper."""
    _load_champion_bundle.cache_clear()
