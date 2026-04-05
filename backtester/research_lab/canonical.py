"""Canonical evaluation for autoresearch v2: typed results shared by walk-forward and checkpoint pilots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backtester.autoresearch_config import (
    ContractValidationError,
    build_strategy_from_overrides,
    load_pilot_contract,
    load_strategy_overrides,
    strategy_hash,
    validate_contract_documents,
)
from backtester.checkpoint_replay import (
    assert_checkpoint_temporal_integrity,
    get_pilot_checkpoints,
    replay_checkpoint,
    summarize_checkpoint_results,
)
from backtester.model_registry import get_live_weekly_model, get_research_champion
from backtester.strategy import StrategyConfig
from backtester.weighted_walkforward import (
    compute_blended_score,
    evaluate_guardrails,
    evaluate_weighted_walkforward,
)
from src import config as src_config
from src.db import ensure_initialized

# Checkpoint CLI / pilot contract must stay aligned with docs/autoresearch/pilot_contract.json
CHECKPOINT_SCRIPT_EVALUATOR_VERSION = 1

# Walk-forward benchmark spec version (independent of checkpoint contract until unified)
EVAL_CONTRACT_VERSION_WALK_FORWARD = 2


def compute_objective_vector_higher_is_better(summary_metrics: dict[str, Any]) -> tuple[float, float, float, float]:
    """
    Pareto objectives (all higher is better): ROI, CLV, negative calibration error, negative drawdown.
    """
    roi = float(summary_metrics.get("weighted_roi_pct", 0.0) or 0.0)
    clv = float(summary_metrics.get("weighted_clv_avg", 0.0) or 0.0)
    cal = float(summary_metrics.get("weighted_calibration_error", 0.0) or 0.0)
    dd = float(summary_metrics.get("max_drawdown_pct", 0.0) or 0.0)
    return (roi, clv, -cal, -dd)


@dataclass(frozen=True)
class WalkForwardBenchmarkSpec:
    """Benchmark parameters for weighted walk-forward replay (same semantics as evaluate_weighted_walkforward)."""

    years: list[int] | None = None
    min_train_events: int = 2
    test_window_size: int = 1
    weighting_mode: str = "full_season_weighted"
    events: list[dict[str, Any]] | None = None
    eval_contract_version: int = EVAL_CONTRACT_VERSION_WALK_FORWARD


@dataclass
class EvaluationResult:
    """Unified evaluation result for dashboard, CLI, and future Optuna integration."""

    mode: str
    eval_contract_version: int
    summary_metrics: dict[str, Any]
    baseline_summary_metrics: dict[str, Any]
    guardrail_results: dict[str, Any]
    blended_score: float
    objective_vector: tuple[float, float, float, float]
    feasible: bool
    checkpoint_payload: dict[str, Any] | None = None
    walk_forward_extras: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable summary (excludes non-serializable nested objects)."""
        return {
            "mode": self.mode,
            "eval_contract_version": self.eval_contract_version,
            "summary_metrics": dict(self.summary_metrics),
            "baseline_summary_metrics": dict(self.baseline_summary_metrics),
            "guardrail_results": dict(self.guardrail_results),
            "blended_score": self.blended_score,
            "objective_vector": list(self.objective_vector),
            "feasible": self.feasible,
            "metadata": dict(self.metadata) if self.metadata else None,
        }

    def to_legacy_checkpoint_eval_dict(self) -> dict[str, Any]:
        """Legacy shape used by scripts/run_autoresearch_eval.py stdout contract."""
        if self.checkpoint_payload is None:
            raise ValueError("to_legacy_checkpoint_eval_dict requires checkpoint_payload")
        return {
            "metric": self.blended_score,
            "guardrails": self.guardrail_results,
            "sample": int(self.summary_metrics.get("total_bets", 0) or 0),
            "checkpoint_summary": self.checkpoint_payload,
            "metadata": self.metadata or {},
        }


def _feasible_from_summary(summary_metrics: dict[str, Any]) -> bool:
    min_bets = int(src_config.get_autoresearch_guardrail_params().get("min_bets", 30))
    return int(summary_metrics.get("total_bets", 0) or 0) >= min_bets


def evaluation_from_walk_forward_dict(
    raw: dict[str, Any],
    *,
    eval_contract_version: int = EVAL_CONTRACT_VERSION_WALK_FORWARD,
) -> EvaluationResult:
    """Wrap the dict returned by evaluate_weighted_walkforward into EvaluationResult."""
    summary = raw["summary_metrics"]
    baseline_summary = raw["baseline_summary_metrics"]
    guardrails = raw["guardrail_results"]
    blended = compute_blended_score(summary, guardrails)
    extras: dict[str, Any] = {}
    if raw.get("segmented_metrics") is not None:
        extras["segmented_metrics"] = raw["segmented_metrics"]
    if raw.get("baseline_segmented_metrics") is not None:
        extras["baseline_segmented_metrics"] = raw["baseline_segmented_metrics"]
    if raw.get("splits") is not None:
        extras["splits"] = raw["splits"]
    return EvaluationResult(
        mode="walk_forward",
        eval_contract_version=eval_contract_version,
        summary_metrics=summary,
        baseline_summary_metrics=baseline_summary,
        guardrail_results=guardrails,
        blended_score=blended,
        objective_vector=compute_objective_vector_higher_is_better(summary),
        feasible=_feasible_from_summary(summary),
        walk_forward_extras=extras or None,
        metadata=None,
    )


def evaluate_walk_forward_benchmark(
    strategy: StrategyConfig,
    baseline_strategy: StrategyConfig,
    spec: WalkForwardBenchmarkSpec,
    *,
    precomputed_baseline: list[dict[str, Any]] | None = None,
) -> EvaluationResult:
    """Run weighted walk-forward and return a canonical EvaluationResult."""
    raw = evaluate_weighted_walkforward(
        strategy=strategy,
        baseline_strategy=baseline_strategy,
        events=spec.events,
        years=spec.years,
        min_train_events=spec.min_train_events,
        test_window_size=spec.test_window_size,
        weighting_mode=spec.weighting_mode,
        precomputed_baseline=precomputed_baseline,
    )
    return evaluation_from_walk_forward_dict(raw, eval_contract_version=spec.eval_contract_version)


def evaluate_checkpoint_pilot(
    strategy_overrides_path: Path | None = None,
) -> EvaluationResult:
    """
    Immutable checkpoint pilot evaluation (same logic as legacy scripts/run_autoresearch_eval._evaluate).
    """
    ensure_initialized()
    validate_contract_documents()
    contract = load_pilot_contract()
    if int(contract["evaluation_contract_version"]) != CHECKPOINT_SCRIPT_EVALUATOR_VERSION:
        raise ContractValidationError(
            f"evaluation_contract_version mismatch: {contract['evaluation_contract_version']} "
            f"!= {CHECKPOINT_SCRIPT_EVALUATOR_VERSION}"
        )

    baseline = get_research_champion("global") or get_live_weekly_model("global")
    overrides = load_strategy_overrides(strategy_overrides_path)
    candidate = build_strategy_from_overrides(overrides, baseline)

    pilot = get_pilot_checkpoints()
    event = pilot["pilot_event"]
    checkpoints = pilot["checkpoints"]

    candidate_results: list[dict[str, Any]] = []
    baseline_results: list[dict[str, Any]] = []
    for checkpoint in checkpoints:
        as_of = checkpoint["as_of_date"]
        assert_checkpoint_temporal_integrity(event["event_id"], event["year"], as_of)
        candidate_results.append(
            replay_checkpoint(
                event_id=event["event_id"],
                year=event["year"],
                strategy=candidate,
                as_of_date=as_of,
                checkpoint_id=checkpoint["id"],
            )
        )
        baseline_results.append(
            replay_checkpoint(
                event_id=event["event_id"],
                year=event["year"],
                strategy=baseline,
                as_of_date=as_of,
                checkpoint_id=checkpoint["id"],
            )
        )

    candidate_summary = summarize_checkpoint_results(candidate_results)
    baseline_summary = summarize_checkpoint_results(baseline_results)
    guardrails = evaluate_guardrails(candidate_summary, baseline_summary)
    blended_score = compute_blended_score(candidate_summary, guardrails)

    checkpoint_payload = {
        "event": event,
        "checkpoint_set_id": contract["checkpoint_set_id"],
        "candidate": candidate_summary,
        "baseline": baseline_summary,
        "checkpoints": candidate_results,
    }

    metadata = {
        "strategy_hash": strategy_hash(overrides),
        "pilot_contract_version": contract["pilot_contract_version"],
        "evaluation_contract_version": contract["evaluation_contract_version"],
        "evaluator_version": CHECKPOINT_SCRIPT_EVALUATOR_VERSION,
    }

    return EvaluationResult(
        mode="checkpoint_pilot",
        eval_contract_version=int(contract["evaluation_contract_version"]),
        summary_metrics=candidate_summary,
        baseline_summary_metrics=baseline_summary,
        guardrail_results=guardrails,
        blended_score=blended_score,
        objective_vector=compute_objective_vector_higher_is_better(candidate_summary),
        feasible=_feasible_from_summary(candidate_summary),
        checkpoint_payload=checkpoint_payload,
        metadata=metadata,
    )
