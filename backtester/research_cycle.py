"""Bounded manual research-cycle orchestration for proposal-only runs."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from backtester.autoresearch_data_health import validate_autoresearch_data_health
from backtester.experiments import get_active_strategy
from backtester.model_registry import (
    get_live_weekly_model,
    get_research_champion,
    get_research_champion_record,
    set_research_champion,
)
from backtester.proposals import approve_proposal, create_proposal, get_proposal, list_proposals, update_proposal_evaluation
from backtester.research_dossier import write_research_dossier
from backtester.research_lab.canonical import EVAL_CONTRACT_VERSION_WALK_FORWARD, evaluation_from_walk_forward_dict
from backtester.strategy import StrategyConfig
from backtester.theory_engine import generate_candidate_theories
from backtester.weighted_walkforward import compute_blended_score, evaluate_weighted_walkforward
from src.autoresearch_env import autoresearch_auto_apply_enabled
from src.autoresearch_settings import get_guardrail_mode

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


PIT_EVALUATION_YEARS = [2024, 2025]


def _should_promote_research_champion(candidate_ranking: dict[str, Any]) -> bool:
    """True if candidate passes full bar for approval and live promotion."""
    summary = candidate_ranking["summary_metrics"]
    baseline_summary = candidate_ranking["baseline_summary_metrics"]
    guardrails = candidate_ranking["guardrail_results"]

    if not guardrails.get("passed", False):
        return False
    if summary.get("weighted_roi_pct", 0.0) <= baseline_summary.get("weighted_roi_pct", 0.0):
        return False
    if summary.get("weighted_clv_avg", 0.0) < baseline_summary.get("weighted_clv_avg", 0.0):
        return False
    if summary.get("total_bets", 0) < 50:
        return False
    return True


def _should_use_as_iteration_baseline(candidate_ranking: dict[str, Any]) -> bool:
    """True if we should set this candidate as research champion so the next cycle iterates from it."""
    summary = candidate_ranking["summary_metrics"]
    baseline_summary = candidate_ranking["baseline_summary_metrics"]
    guardrails = candidate_ranking["guardrail_results"]
    if not guardrails.get("passed", False):
        return False
    candidate_roi = summary.get("weighted_roi_pct")
    baseline_roi = baseline_summary.get("weighted_roi_pct")
    if candidate_roi is None or baseline_roi is None:
        return False
    return float(candidate_roi) > float(baseline_roi)


def get_current_baseline_metrics(scope: str = "global") -> dict[str, Any]:
    """
    Return current baseline ROI and CLV for the dashboard / engine "since start" snapshot.
    Uses the latest evaluated proposal's baseline_summary_metrics (same notion as dashboard).
    Returns dict with weighted_roi_pct and weighted_clv_avg; values are None if no data.
    """
    from src import db

    conn = db.get_conn()
    row = conn.execute(
        """
        SELECT guardrail_results_json
        FROM research_proposals
        WHERE scope = ?
          AND status IN ('evaluated', 'approved', 'converted')
          AND guardrail_results_json IS NOT NULL
        ORDER BY COALESCE(evaluated_at, created_at) DESC, id DESC
        LIMIT 1
        """,
        (scope,),
    ).fetchone()
    conn.close()
    if not row or not row["guardrail_results_json"]:
        return {"weighted_roi_pct": None, "weighted_clv_avg": None}
    try:
        guardrails = json.loads(row["guardrail_results_json"])
        baseline = guardrails.get("baseline_summary_metrics") or {}
        return {
            "weighted_roi_pct": baseline.get("weighted_roi_pct"),
            "weighted_clv_avg": baseline.get("weighted_clv_avg"),
        }
    except (json.JSONDecodeError, TypeError):
        return {"weighted_roi_pct": None, "weighted_clv_avg": None}


def _get_global_best_proposal_for_iteration(
    scope: str,
    current_champion_roi: float | None,
    pool_limit: int = 200,
) -> dict[str, Any] | None:
    """
    Return the single best evaluated proposal (by ROI) that passes guardrails and
    beats current_champion_roi, so the cycle can set it as research champion.
    Uses same pool and sort as dashboard best-candidates (recently evaluated first, then by ROI).
    """
    from src import db

    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT id, name, strategy_config_json, theory_metadata_json,
               summary_metrics_json, guardrail_results_json
        FROM research_proposals
        WHERE scope = ?
          AND status IN ('evaluated', 'approved', 'converted')
          AND summary_metrics_json IS NOT NULL
          AND guardrail_results_json IS NOT NULL
        ORDER BY COALESCE(evaluated_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (scope, pool_limit),
    ).fetchall()
    conn.close()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        try:
            summary = json.loads(row["summary_metrics_json"] or "{}")
            guardrails = json.loads(row["guardrail_results_json"] or "{}")
            if not guardrails.get("passed", False):
                continue
            roi = summary.get("weighted_roi_pct")
            if roi is None:
                continue
            if current_champion_roi is not None and float(roi) <= float(current_champion_roi):
                continue
            candidates.append({
                "id": row["id"],
                "name": row["name"],
                "strategy_config_json": row["strategy_config_json"],
                "theory_metadata_json": row["theory_metadata_json"],
                "summary_metrics": summary,
                "guardrail_results": guardrails,
            })
        except (json.JSONDecodeError, TypeError):
            continue

    if not candidates:
        return None
    # Best by ROI (then CLV for tiebreak)
    candidates.sort(
        key=lambda c: (
            c["summary_metrics"].get("weighted_roi_pct", -999),
            c["summary_metrics"].get("weighted_clv_avg", -999),
        ),
        reverse=True,
    )
    return candidates[0]


def run_research_cycle(
    *,
    max_candidates: int = 5,
    years: list[int] | None = PIT_EVALUATION_YEARS,
    source: str = "manual",
    scope: str = "global",
    output_dir: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    data_health = validate_autoresearch_data_health(years=years)
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

    cached_baseline: list[dict[str, Any]] | None = None

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
            precomputed_baseline=cached_baseline,
        )
        if cached_baseline is None:
            cached_baseline = evaluation.get("baseline_event_results")
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
                "canonical_evaluation": evaluation_from_walk_forward_dict(evaluation).to_dict(),
            }
        )

    proposals = [get_proposal(proposal_id) for proposal_id in evaluated_ids]
    # Rank by best ROI first (highest weighted_roi_pct), then CLV, then blended_score.
    # Winner = strategy we iterate from; should be the one with best ROI that beats baseline.
    candidate_rankings.sort(
        key=lambda item: (
            item["summary_metrics"].get("weighted_roi_pct", -999),
            item["summary_metrics"].get("weighted_clv_avg", -999),
            item["blended_score"],
        ),
        reverse=True,
    )
    winner = candidate_rankings[0] if candidate_rankings else None
    research_champion_updated = False
    promotion_decision = "no_candidates"
    auto_apply = autoresearch_auto_apply_enabled()

    # Always iterate from the best: set research champion to winner whenever they beat baseline
    # (guardrails passed, ROI > baseline) so the next cycle generates candidates from it.
    # When AUTORESEARCH_AUTO_APPLY is unset/false (default), skip registry writes — report-only.
    if winner and _should_use_as_iteration_baseline(winner):
        winning_proposal = get_proposal(winner["proposal_id"])
        strategy = StrategyConfig.from_json(winning_proposal["strategy_config_json"])
        theory_metadata = json.loads(winning_proposal.get("theory_metadata_json") or "{}")
        if auto_apply:
            set_research_champion(
                strategy,
                scope=scope,
                source=winner.get("source_type", source),
                proposal_id=winner["proposal_id"],
                theory_metadata=theory_metadata,
                notes=f"Auto-promoted from optimizer cycle {cycle_key}",
            )
            research_champion_updated = True
            if _should_promote_research_champion(winner):
                approve_proposal(
                    winner["proposal_id"],
                    reviewer="autoresearch_cycle",
                    notes=f"Auto-approved: promoted as research champion from cycle {cycle_key}",
                )
                promotion_decision = "updated_research_champion"
            else:
                promotion_decision = "updated_iteration_baseline"
        else:
            promotion_decision = "report_only"
    elif winner:
        promotion_decision = "kept_current_research_champion"

    # Promote the global best to iteration baseline so we iterate from the true top candidate,
    # not only from this cycle's winner. Stops "same 3" / going in circles when the best
    # proposal is from an earlier cycle.
    current_champion_roi: float | None = None
    if winner and research_champion_updated:
        current_champion_roi = winner["summary_metrics"].get("weighted_roi_pct")
    elif candidate_rankings:
        current_champion_roi = candidate_rankings[0]["baseline_summary_metrics"].get("weighted_roi_pct")
    if current_champion_roi is not None:
        current_champion_roi = float(current_champion_roi)
    champion_record = get_research_champion_record(scope)
    current_champion_proposal_id = (champion_record.get("proposal_id") if champion_record else None) or None

    global_best = _get_global_best_proposal_for_iteration(scope, current_champion_roi)
    if global_best and global_best["id"] != current_champion_proposal_id:
        strategy = StrategyConfig.from_json(global_best["strategy_config_json"])
        theory_metadata = json.loads(global_best.get("theory_metadata_json") or "{}")
        if auto_apply:
            set_research_champion(
                strategy,
                scope=scope,
                source="autoresearch_global_best",
                proposal_id=global_best["id"],
                theory_metadata=theory_metadata,
                notes="Auto-promoted as global best by ROI for next iteration",
            )
            research_champion_updated = True
            if promotion_decision == "kept_current_research_champion":
                promotion_decision = "updated_iteration_baseline"
        elif promotion_decision == "kept_current_research_champion":
            promotion_decision = "report_only"

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
        "autoresearch_auto_apply": auto_apply,
        "ready_for_live_review": bool(winner and winner.get("ready_for_live_review")),
        "data_health": data_health,
        "guardrail_mode": get_guardrail_mode(),
        "eval_contract_version_walk_forward": EVAL_CONTRACT_VERSION_WALK_FORWARD,
    }
