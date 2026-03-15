"""OpenAI-first theory generation for research candidates."""

from __future__ import annotations

import hashlib
import json
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
                            "properties": {
                                "w_sg_total": {"type": ["number", "null"]},
                                "w_sg_app": {"type": ["number", "null"]},
                                "w_sg_ott": {"type": ["number", "null"]},
                                "w_sg_arg": {"type": ["number", "null"]},
                                "w_sg_putt": {"type": ["number", "null"]},
                                "w_form": {"type": ["number", "null"]},
                                "w_course_fit": {"type": ["number", "null"]},
                                "w_sub_course_fit": {"type": ["number", "null"]},
                                "w_sub_form": {"type": ["number", "null"]},
                                "w_sub_momentum": {"type": ["number", "null"]},
                                "stat_window": {"type": ["integer", "null"]},
                                "min_ev": {"type": ["number", "null"]},
                                "max_implied_prob": {"type": ["number", "null"]},
                                "min_model_prob": {"type": ["number", "null"]},
                                "kelly_fraction": {"type": ["number", "null"]},
                                "softmax_temp": {"type": ["number", "null"]},
                                "ai_adj_cap": {"type": ["number", "null"]},
                                "use_weather": {"type": ["boolean", "null"]},
                            },
                            "required": [
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
                            ],
                            "additionalProperties": False,
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
        if key in ALLOWED_OVERRIDE_FIELDS and value is not None:
            values[key] = value
    values["name"] = f"{base.name or 'baseline'}_theory_{index + 1}"
    values["description"] = title
    return StrategyConfig(**values)


def _get_recent_results_context(limit: int = 10) -> str:
    """Query recent evaluated proposals for context in the prompt."""
    try:
        from src import db
        conn = db.get_conn()
        rows = conn.execute(
            """
            SELECT name, summary_metrics_json, guardrail_results_json, strategy_config_json
            FROM research_proposals
            WHERE summary_metrics_json IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        if not rows:
            return "No prior results available."
        lines = []
        for r in rows:
            metrics = json.loads(r["summary_metrics_json"]) if r["summary_metrics_json"] else {}
            guardrails = json.loads(r["guardrail_results_json"]) if r["guardrail_results_json"] else {}
            roi = metrics.get("weighted_roi_pct", 0)
            clv = metrics.get("weighted_clv_avg", 0)
            passed = guardrails.get("passed", False)
            lines.append(f"  - {r['name']}: ROI={roi:+.2f}%, CLV={clv:.4f}, guardrails={'pass' if passed else 'fail'}")
        return "\n".join(lines)
    except Exception:
        return "Could not load prior results."


def _get_existing_strategy_hashes() -> set[str]:
    """Return hashes of already-evaluated strategy configs to avoid duplicates."""
    try:
        from src import db
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT DISTINCT strategy_config_json FROM research_proposals WHERE strategy_config_json IS NOT NULL"
        ).fetchall()
        conn.close()
        return {hashlib.md5(r["strategy_config_json"].encode()).hexdigest() for r in rows}
    except Exception:
        return set()


def _strategy_hash(strategy: StrategyConfig) -> str:
    config_json = json.dumps(
        {k: v for k, v in vars(strategy).items() if not k.startswith("_")},
        sort_keys=True,
    )
    return hashlib.md5(config_json.encode()).hexdigest()


def _build_openai_prompt(base: StrategyConfig, max_candidates: int, scope: str, years: list[int] | None) -> str:
    prior_context = _get_recent_results_context(10)
    return (
        "You are optimizing a golf betting model. Generate candidate strategy theories.\n\n"
        "## Model architecture\n"
        "The production model uses PIT (point-in-time) sub-model composites for 2024+ events:\n"
        "  - w_sub_course_fit: weight for course fit sub-model\n"
        "  - w_sub_form: weight for recent form sub-model\n"
        "  - w_sub_momentum: weight for momentum sub-model\n"
        "These three weights are normalized to sum to 1.0. They are the PRIMARY levers.\n"
        "Legacy SG weights (w_sg_total, w_sg_app, etc.) are fallback for older events.\n\n"
        "## Betting parameters (also important)\n"
        "  - min_ev: minimum expected value threshold to place a bet (higher = fewer, more selective bets)\n"
        "  - kelly_fraction: Kelly criterion fraction for sizing (higher = more aggressive)\n"
        "  - softmax_temp: temperature for probability conversion (lower = more concentrated)\n"
        "  - max_implied_prob: filter out heavy favorites above this threshold\n\n"
        f"## Current baseline\n{base.to_json()}\n\n"
        f"## Recent evaluation results (what's been tried):\n{prior_context}\n\n"
        f"Scope: {scope} | Evaluation years: {years or 'default'} | Max candidates: {max_candidates}\n\n"
        "Generate {max_candidates} diverse, practical experiments. Focus on:\n"
        "1. Varying w_sub_* weights (the actual production levers)\n"
        "2. Adjusting min_ev and kelly_fraction for bet selection/sizing\n"
        "3. Exploring different softmax temperatures\n"
        "4. Build on what worked in recent results, avoid repeating failures\n"
        "Prioritize strategies that improve ROI relative to baseline without CLV regression."
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
    candidates = generate_neighbor_strategies(base, n=max_candidates + 3, perturbation=0.05)
    for index, strategy in enumerate(candidates[:max_candidates]):
        theories.append(
            {
                "title": f"Neighbor search {index + 1}",
                "hypothesis": f"Test nearby parameter changes around {base.name or 'baseline'}.",
                "why_it_may_work": "Local search explores nearby PIT sub-model weights and betting parameters.",
                "source_type": "fallback_neighbor",
                "novelty_score": 0.2,
                "duplicate_marker": "",
                "ranking_hint": 0.2,
                "strategy": strategy,
                "strategy_overrides": {},
            }
        )
    return theories


def _deduplicate_theories(
    theories: list[dict[str, Any]], existing_hashes: set[str]
) -> list[dict[str, Any]]:
    """Remove theories whose strategy config has already been evaluated."""
    unique = []
    for theory in theories:
        h = _strategy_hash(theory["strategy"])
        if h not in existing_hashes:
            existing_hashes.add(h)
            unique.append(theory)
        else:
            logger.info("Skipping duplicate theory: %s", theory.get("title", "?"))
    return unique


def generate_candidate_theories(
    base: StrategyConfig,
    *,
    max_candidates: int = 5,
    scope: str = "global",
    years: list[int] | None = None,
) -> list[dict[str, Any]]:
    existing_hashes = _get_existing_strategy_hashes()

    if is_ai_available():
        try:
            theories = _openai_theories(base, max_candidates, scope, years)
            if theories:
                theories = _deduplicate_theories(theories, existing_hashes)
                if theories:
                    return theories
                logger.warning("All OpenAI theories were duplicates; falling back to neighbor search.")
            else:
                logger.warning("OpenAI returned no candidate theories; falling back to neighbor search.")
        except Exception as exc:
            logger.warning("OpenAI theory generation failed; falling back to neighbor search: %s", exc)
    else:
        logger.warning("AI provider unavailable for theory engine; using neighbor fallback.")

    fallback = _fallback_theories(base, max_candidates + 5)
    fallback = _deduplicate_theories(fallback, existing_hashes)
    return fallback[:max_candidates]
