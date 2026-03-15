"""Bounded manual research-cycle orchestration for proposal-only runs."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from backtester.experiments import get_active_strategy
from backtester.model_registry import get_live_weekly_model, get_research_champion, set_research_champion
from backtester.proposals import create_proposal, get_proposal, list_proposals, update_proposal_evaluation
from backtester.research_dossier import write_research_dossier
from backtester.strategy import StrategyConfig
from backtester.theory_engine import generate_candidate_theories
from backtester.weighted_walkforward import compute_blended_score, evaluate_weighted_walkforward

FIELD_LABELS: dict[str, str] = {
    "w_sg_total": "SG total",
    "w_sg_app": "approach",
    "w_sg_ott": "off-the-tee",
    "w_sg_arg": "around-green",
    "w_sg_putt": "putting",
    "w_form": "form",
    "w_course_fit": "course fit",
    "w_sub_course_fit": "sub-course fit",
    "w_sub_form": "sub-form",
    "w_sub_momentum": "sub-momentum",
    "stat_window": "stat window",
    "min_ev": "min EV",
    "max_implied_prob": "max implied prob",
    "min_model_prob": "min model prob",
    "kelly_fraction": "kelly fraction",
    "softmax_temp": "softmax temp",
    "ai_adj_cap": "AI adjustment cap",
    "use_weather": "weather flag",
}


def _git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL)
            .strip()
        )
    except Exception:
        return None


def _git_dirty() -> bool:
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(output.strip())
    except Exception:
        return False


def _proposal_payload_from_strategy(
    theory: dict[str, Any],
    *,
    cycle_key: str,
    source: str,
    scope: str,
    baseline_strategy: StrategyConfig,
    years: list[int] | None,
    candidate_count_in_cycle: int,
    seed: int,
) -> dict[str, Any]:
    strategy: StrategyConfig = theory["strategy"]
    display_title = _derive_display_title(theory, strategy, baseline_strategy)
    what_tested = _build_what_tested(theory, strategy, baseline_strategy)
    return {
        "name": display_title,
        "hypothesis": theory.get("hypothesis") or f"Evaluate candidate strategy {strategy.name or 'candidate'} against current baseline",
        "strategy_config": {
            key: value for key, value in vars(strategy).items() if not key.startswith("_")
        },
        "baseline_strategy": {
            key: value for key, value in vars(baseline_strategy).items() if not key.startswith("_")
        },
        "cycle_key": cycle_key,
        "source": source,
        "scope": scope,
        "program_version": "v1",
        "event_weighting_mode": "full_season_weighted",
        "candidate_count_in_cycle": candidate_count_in_cycle,
        "years": years,
        "filters": {"scope": scope},
        "theory_metadata": {
            "title": display_title,
            "raw_title": theory.get("title"),
            "source_type": theory.get("source_type", source),
            "why_it_may_work": theory.get("why_it_may_work"),
            "what_tested": what_tested,
            "novelty_score": theory.get("novelty_score"),
            "duplicate_marker": theory.get("duplicate_marker"),
            "ranking_hint": theory.get("ranking_hint"),
            "strategy_overrides": theory.get("strategy_overrides", {}),
        },
        "repro_metadata": {
            "seed": seed,
            "program_version": "v1",
            "code_commit": _git_commit(),
            "git_dirty": _git_dirty(),
            "years": years,
            "theory_source": theory.get("source_type", source),
        },
    }


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (int, float)):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _strategy_change_descriptions(
    strategy: StrategyConfig,
    baseline_strategy: StrategyConfig,
    *,
    max_items: int = 3,
) -> list[str]:
    base_values = vars(baseline_strategy)
    candidate_values = vars(strategy)
    changes: list[tuple[float, str]] = []
    for key, label in FIELD_LABELS.items():
        if key not in base_values or key not in candidate_values:
            continue
        new_value = candidate_values.get(key)
        old_value = base_values.get(key)
        if new_value == old_value:
            continue
        weight = 1.0
        if isinstance(new_value, (int, float)) and isinstance(old_value, (int, float)):
            weight = abs(float(new_value) - float(old_value))
        direction = "set to"
        if isinstance(new_value, (int, float)) and isinstance(old_value, (int, float)):
            if float(new_value) > float(old_value):
                direction = "increased to"
            elif float(new_value) < float(old_value):
                direction = "decreased to"
        description = f"{label} {direction} {_format_value(new_value)} (was {_format_value(old_value)})"
        changes.append((weight, description))
    changes.sort(key=lambda item: item[0], reverse=True)
    return [desc for _, desc in changes[:max_items]]


def _derive_display_title(theory: dict[str, Any], strategy: StrategyConfig, baseline_strategy: StrategyConfig) -> str:
    title = (theory.get("title") or "").strip()
    if title and not title.lower().startswith("neighbor search"):
        return title
    changes = _strategy_change_descriptions(strategy, baseline_strategy, max_items=1)
    if changes:
        return changes[0].capitalize()
    return title or strategy.name or "Candidate strategy test"


def _build_what_tested(theory: dict[str, Any], strategy: StrategyConfig, baseline_strategy: StrategyConfig) -> str:
    hypothesis = (theory.get("hypothesis") or "").strip()
    changes = _strategy_change_descriptions(strategy, baseline_strategy, max_items=3)
    if not changes:
        return hypothesis or "Tested a nearby parameter variation against the current baseline."
    change_text = "; ".join(changes)
    if hypothesis:
        return f"{hypothesis} Key parameter shifts: {change_text}."
    return f"Tested these parameter shifts: {change_text}."


def _next_attempt_hint(guardrail_results: dict[str, Any]) -> str:
    reasons = guardrail_results.get("reasons") or []
    if "insufficient_sample" in reasons:
        return "Increase sample size or broaden benchmark years before trusting this variant."
    if "clv_regression" in reasons:
        return "Keep ROI ideas but tune for better market alignment to improve CLV."
    if "calibration_regression" in reasons:
        return "Reduce aggressive probability shifts and retest calibration-focused variants."
    if "drawdown_regression" in reasons:
        return "Lower risk concentration and explore milder weight adjustments."
    return "Iterate on the strongest changed factor while keeping guardrails stable."


def _build_run_summary(
    summary_metrics: dict[str, Any],
    baseline_summary_metrics: dict[str, Any],
    guardrail_results: dict[str, Any],
) -> tuple[str, bool]:
    roi = float(summary_metrics.get("weighted_roi_pct", 0.0) or 0.0)
    base_roi = float(baseline_summary_metrics.get("weighted_roi_pct", 0.0) or 0.0)
    clv = float(summary_metrics.get("weighted_clv_avg", 0.0) or 0.0)
    base_clv = float(baseline_summary_metrics.get("weighted_clv_avg", 0.0) or 0.0)
    passed = bool(guardrail_results.get("passed", False))
    positive = passed and roi > base_roi and clv >= base_clv
    if positive:
        return (
            f"Positive test: ROI {roi:.2f}% beat baseline {base_roi:.2f}% and guardrails passed.",
            True,
        )
    if not passed:
        return (
            f"Blocked by guardrails: ROI {roi:.2f}% vs baseline {base_roi:.2f}%.",
            False,
        )
    return (
        f"Not promoted: ROI {roi:.2f}% vs baseline {base_roi:.2f}%, CLV {clv:.3f} vs {base_clv:.3f}.",
        False,
    )


def _should_promote_research_champion(candidate_ranking: dict[str, Any]) -> bool:
    summary = candidate_ranking["summary_metrics"]
    baseline_summary = candidate_ranking["baseline_summary_metrics"]
    guardrails = candidate_ranking["guardrail_results"]

    if not guardrails.get("passed", False):
        return False
    if summary.get("weighted_roi_pct", 0.0) <= 0:
        return False
    if summary.get("weighted_roi_pct", 0.0) <= baseline_summary.get("weighted_roi_pct", 0.0):
        return False
    if summary.get("weighted_clv_avg", 0.0) < baseline_summary.get("weighted_clv_avg", 0.0):
        return False
    if summary.get("total_bets", 0) < 100:
        return False
    return True


def run_research_cycle(
    *,
    max_candidates: int = 5,
    years: list[int] | None = None,
    source: str = "manual",
    scope: str = "global",
    output_dir: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    baseline_strategy = get_research_champion(scope) or get_live_weekly_model(scope) or get_active_strategy(scope)
    candidate_theories = generate_candidate_theories(
        baseline_strategy,
        max_candidates=max_candidates,
        scope=scope,
        years=years,
    )[:max_candidates]

    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "output",
            "research",
        )
    os.makedirs(output_dir, exist_ok=True)

    cycle_key = f"{source}:{scope}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}:{seed}:{len(candidate_theories)}"
    evaluated_ids: list[int] = []
    candidate_rankings: list[dict[str, Any]] = []
    source_types = sorted({theory.get("source_type", source) for theory in candidate_theories})
    theory_engine_mode = "fallback_local_search" if source_types == ["fallback_neighbor"] else ", ".join(source_types)

    for theory in candidate_theories:
        strategy = theory["strategy"]
        payload = _proposal_payload_from_strategy(
            theory,
            cycle_key=cycle_key,
            source=source,
            scope=scope,
            baseline_strategy=baseline_strategy,
            years=years,
            candidate_count_in_cycle=len(candidate_theories),
            seed=seed,
        )
        proposal_id = create_proposal(**payload)
        proposal = get_proposal(proposal_id)
        evaluation = evaluate_weighted_walkforward(
            strategy=strategy,
            baseline_strategy=baseline_strategy,
            events=None,
            years=years,
            min_train_events=2,
            test_window_size=1,
        )
        artifact_paths = write_research_dossier(
            proposal=proposal,
            evaluation=evaluation,
            repro_metadata=payload["repro_metadata"],
            output_dir=output_dir,
        )
        enriched_guardrails = dict(evaluation["guardrail_results"])
        summary_text, positive_test = _build_run_summary(
            evaluation["summary_metrics"],
            evaluation["baseline_summary_metrics"],
            enriched_guardrails,
        )
        enriched_guardrails["summary"] = summary_text
        enriched_guardrails["is_positive_test"] = positive_test
        enriched_guardrails["next_attempt_hint"] = _next_attempt_hint(enriched_guardrails)
        enriched_guardrails["baseline_summary_metrics"] = evaluation["baseline_summary_metrics"]
        update_proposal_evaluation(
            proposal_id,
            summary_metrics=evaluation["summary_metrics"],
            segmented_metrics=evaluation["segmented_metrics"],
            guardrail_results=enriched_guardrails,
            artifact_markdown_path=artifact_paths["markdown_path"],
            artifact_manifest_path=artifact_paths["manifest_path"],
        )
        evaluated_ids.append(proposal_id)
        candidate_rankings.append(
            {
                "proposal_id": proposal_id,
                "proposal_name": payload["name"],
                "strategy_name": strategy.name,
                "source_type": theory.get("source_type", source),
                "summary_metrics": evaluation["summary_metrics"],
                "baseline_summary_metrics": evaluation["baseline_summary_metrics"],
                "guardrail_results": enriched_guardrails,
                "blended_score": compute_blended_score(
                    evaluation["summary_metrics"],
                    enriched_guardrails,
                ),
                "artifact_markdown_path": artifact_paths["markdown_path"],
                "artifact_manifest_path": artifact_paths["manifest_path"],
                "theory_title": payload["name"],
                "why_it_may_work": theory.get("why_it_may_work"),
                "ready_for_live_review": (
                    enriched_guardrails.get("passed", False)
                    and evaluation["summary_metrics"].get("weighted_roi_pct", 0.0) > 0
                ),
            }
        )

    proposals = [get_proposal(proposal_id) for proposal_id in evaluated_ids]
    candidate_rankings.sort(key=lambda item: item["blended_score"], reverse=True)
    winner = candidate_rankings[0] if candidate_rankings else None
    research_champion_updated = False
    promotion_decision = "no_candidates"
    if winner and _should_promote_research_champion(winner):
        winning_proposal = get_proposal(winner["proposal_id"])
        strategy = StrategyConfig.from_json(winning_proposal["strategy_config_json"])
        theory_metadata = json.loads(winning_proposal.get("theory_metadata_json") or "{}")
        set_research_champion(
            strategy,
            scope=scope,
            source=winner.get("source_type", source),
            proposal_id=winner["proposal_id"],
            theory_metadata=theory_metadata,
            notes=f"Auto-promoted from optimizer cycle {cycle_key}",
        )
        research_champion_updated = True
        promotion_decision = "updated_research_champion"
    elif winner:
        promotion_decision = "kept_current_research_champion"
    return {
        "cycle_key": cycle_key,
        "proposals_created": len(candidate_theories),
        "proposals_evaluated": len(proposals),
        "proposals": proposals,
        "top_candidates": candidate_rankings[:5],
        "winner": winner,
        "theory_engine_mode": theory_engine_mode,
        "research_champion_updated": research_champion_updated,
        "promotion_decision": promotion_decision,
        "ready_for_live_review": bool(winner and winner.get("ready_for_live_review")),
    }
