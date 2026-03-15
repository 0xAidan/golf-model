"""OpenAI-first theory generation for research candidates."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from backtester.experiments import generate_neighbor_strategies
from backtester.strategy import StrategyConfig
from src.ai_brain import call_ai, is_ai_available

logger = logging.getLogger("theory_engine")

THEORY_SCHEMA = {
    "name": "research_theories",
    "schema": {
        "type": "object",
        "properties": {
            "theories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "hypothesis": {"type": "string"},
                        "why_it_may_work": {"type": "string"},
                        "source_type": {"type": "string"},
                        "novelty_score": {"type": "number"},
                        "duplicate_marker": {"type": "string"},
                        "ranking_hint": {"type": "number"},
                        "strategy_overrides": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                    "required": [
                        "title",
                        "hypothesis",
                        "why_it_may_work",
                        "source_type",
                        "novelty_score",
                        "duplicate_marker",
                        "ranking_hint",
                        "strategy_overrides",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["theories"],
        "additionalProperties": False,
    },
}

ALLOWED_OVERRIDE_FIELDS = {
    "w_sg_total",
    "w_sg_app",
    "w_sg_ott",
    "w_sg_arg",
    "w_sg_putt",
    "w_form",
    "w_course_fit",
    "w_sub_course_fit",
    "w_sub_form",
    "w_sub_momentum",
    "stat_window",
    "min_ev",
    "max_implied_prob",
    "min_model_prob",
    "kelly_fraction",
    "softmax_temp",
    "ai_adj_cap",
    "use_weather",
}


def _apply_overrides(base: StrategyConfig, overrides: dict[str, Any], index: int, title: str) -> StrategyConfig:
    values = asdict(base)
    for key, value in (overrides or {}).items():
        if key in ALLOWED_OVERRIDE_FIELDS:
            values[key] = value
    values["name"] = f"{base.name or 'baseline'}_theory_{index + 1}"
    values["description"] = title
    return StrategyConfig(**values)


def _build_openai_prompt(base: StrategyConfig, max_candidates: int, scope: str, years: list[int] | None) -> str:
    return (
        "Invent candidate golf betting strategy theories for the existing model.\n"
        f"Scope: {scope}\n"
        f"Years for evaluation: {years or 'default historical sample'}\n"
        f"Max candidates: {max_candidates}\n"
        "Return only practical, bounded experiments that change StrategyConfig fields.\n"
        f"Baseline strategy JSON: {base.to_json()}\n"
        "Prioritize explainable ideas that could improve ROI without major CLV, calibration, or drawdown regressions."
    )


def _openai_theories(base: StrategyConfig, max_candidates: int, scope: str, years: list[int] | None) -> list[dict[str, Any]]:
    response = call_ai(
        _build_openai_prompt(base, max_candidates, scope, years),
        system_prompt=(
            "You are the golf model research theorist. Generate candidate theories as valid JSON only. "
            "Every idea must include why it may work and only use StrategyConfig-compatible overrides."
        ),
        response_schema=THEORY_SCHEMA,
    )
    theories = []
    for index, item in enumerate((response or {}).get("theories", [])[:max_candidates]):
        strategy = _apply_overrides(base, item.get("strategy_overrides", {}), index, item.get("title", "Theory"))
        theories.append(
            {
                "title": item.get("title") or f"OpenAI Theory {index + 1}",
                "hypothesis": item.get("hypothesis") or "OpenAI-generated theory",
                "why_it_may_work": item.get("why_it_may_work") or "",
                "source_type": item.get("source_type") or "openai",
                "novelty_score": float(item.get("novelty_score", 0.5)),
                "duplicate_marker": item.get("duplicate_marker") or "",
                "ranking_hint": float(item.get("ranking_hint", 0.5)),
                "strategy": strategy,
                "strategy_overrides": item.get("strategy_overrides", {}),
            }
        )
    return theories


def _fallback_theories(base: StrategyConfig, max_candidates: int) -> list[dict[str, Any]]:
    theories = []
    for index, strategy in enumerate(generate_neighbor_strategies(base, n=max_candidates, perturbation=0.03)[:max_candidates]):
        theories.append(
            {
                "title": f"Neighbor search {index + 1}",
                "hypothesis": f"Test nearby parameter changes around {base.name or 'baseline'}.",
                "why_it_may_work": "Local fallback search explores nearby settings when OpenAI is unavailable.",
                "source_type": "fallback_neighbor",
                "novelty_score": 0.2,
                "duplicate_marker": "",
                "ranking_hint": 0.2,
                "strategy": strategy,
                "strategy_overrides": {},
            }
        )
    return theories


def generate_candidate_theories(
    base: StrategyConfig,
    *,
    max_candidates: int = 5,
    scope: str = "global",
    years: list[int] | None = None,
) -> list[dict[str, Any]]:
    if is_ai_available():
        try:
            theories = _openai_theories(base, max_candidates, scope, years)
            if theories:
                return theories
            logger.warning("OpenAI returned no candidate theories; falling back to neighbor search.")
        except Exception as exc:
            logger.warning("OpenAI theory generation failed; falling back to neighbor search: %s", exc)
    else:
        logger.warning("AI provider unavailable for theory engine; using neighbor fallback.")
    return _fallback_theories(base, max_candidates)
