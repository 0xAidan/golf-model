"""Multi-objective and scalar Optuna studies over StrategyConfig (canonical walk-forward evaluation)."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Literal

import optuna
from optuna.storages import RDBStorage
from optuna.trial import TrialState

from backtester.autoresearch_config import strategy_hash
from backtester.research_lab.benchmark_fingerprint import benchmark_spec_hash
from backtester.research_lab.canonical import EvaluationResult, WalkForwardBenchmarkSpec, evaluate_walk_forward_benchmark
from backtester.research_lab.eval_timeout import default_max_trial_seconds, run_with_timeout
from backtester.research_lab.ledger import append_ledger_row, ledger_row_from_optuna_trial
from backtester.research_lab.param_space import strategy_from_optuna_trial
from backtester.strategy import StrategyConfig

_logger = logging.getLogger("research_lab.mo_study")

DEFAULT_OPTUNA_DIR = Path("output") / "research" / "optuna"

_DOMINATED_FAIL = (-1e9, -1e9, -1e9, -1e9)


def default_storage_path() -> Path:
    return DEFAULT_OPTUNA_DIR / "studies.db"


def _compose_study_name(base_name: str, suffix: str) -> str:
    clean_base = (base_name or "study").strip() or "study"
    remaining = max(1, 120 - len(suffix) - 2)
    return f"{clean_base[:remaining]}__{suffix}"


def resolve_scalar_study_name(
    study_name: str,
    *,
    benchmark_spec: WalkForwardBenchmarkSpec,
    scalar_metric: Literal["blended_score", "weighted_roi_pct"] = "blended_score",
) -> str:
    bench_hash = benchmark_spec_hash(benchmark_spec)[:8]
    suffix = f"{scalar_metric}_{bench_hash}"
    return _compose_study_name(study_name, suffix)


def make_objective(
    *,
    baseline: StrategyConfig,
    benchmark_spec: WalkForwardBenchmarkSpec,
    study_name: str,
    evaluate_fn: Callable[[StrategyConfig, StrategyConfig, WalkForwardBenchmarkSpec], EvaluationResult] | None = None,
    max_trial_seconds: float | None = None,
) -> Callable[[optuna.Trial], tuple[float, float, float, float]]:
    """Return an Optuna objective that maximizes all four canonical objectives (higher is better)."""
    eval_fn = evaluate_fn or evaluate_walk_forward_benchmark
    bench_hash = benchmark_spec_hash(benchmark_spec)
    ev_ver = benchmark_spec.eval_contract_version
    max_sec = max_trial_seconds if max_trial_seconds is not None else default_max_trial_seconds()

    def objective(trial: optuna.Trial) -> tuple[float, float, float, float]:
        candidate = strategy_from_optuna_trial(trial, baseline)
        sh = strategy_hash(asdict(candidate))

        def _eval() -> EvaluationResult:
            return eval_fn(candidate, baseline, benchmark_spec)

        t0 = time.perf_counter()
        result, err = run_with_timeout(_eval, timeout_seconds=max_sec)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        if err or result is None:
            row = ledger_row_from_optuna_trial(
                source="optuna_mo",
                study_name=study_name,
                trial_number=trial.number,
                params=dict(trial.params),
                user_attrs={"feasible": False, "guardrail_passed": False},
                values=None,
                duration_ms=duration_ms,
                error=err or "no_result",
                eval_contract_version=ev_ver,
                benchmark_spec_hash=bench_hash,
                strategy_hash=sh,
            )
            append_ledger_row(row)
            trial.set_user_attr("error", err or "no_result")
            return _DOMINATED_FAIL

        trial.set_user_attr("feasible", result.feasible)
        trial.set_user_attr("guardrail_passed", bool(result.guardrail_results.get("passed", False)))
        trial.set_user_attr("blended_score", result.blended_score)
        trial.set_user_attr("weighted_roi_pct", float(result.summary_metrics.get("weighted_roi_pct", 0.0) or 0.0))
        trial.set_user_attr("weighted_clv_avg", float(result.summary_metrics.get("weighted_clv_avg", 0.0) or 0.0))
        roi, clv, neg_cal, neg_dd = result.objective_vector
        vals = [roi, clv, neg_cal, neg_dd]
        row = ledger_row_from_optuna_trial(
            source="optuna_mo",
            study_name=study_name,
            trial_number=trial.number,
            params=dict(trial.params),
            user_attrs=dict(trial.user_attrs),
            values=vals,
            duration_ms=duration_ms,
            error=None,
            eval_contract_version=ev_ver,
            benchmark_spec_hash=bench_hash,
            strategy_hash=sh,
        )
        append_ledger_row(row)
        return (roi, clv, neg_cal, neg_dd)

    return objective


def make_scalar_objective(
    *,
    baseline: StrategyConfig,
    benchmark_spec: WalkForwardBenchmarkSpec,
    study_name: str,
    scalar_metric: Literal["blended_score", "weighted_roi_pct"] = "blended_score",
    evaluate_fn: Callable[[StrategyConfig, StrategyConfig, WalkForwardBenchmarkSpec], EvaluationResult] | None = None,
    max_trial_seconds: float | None = None,
) -> Callable[[optuna.Trial], float]:
    """Single-objective: maximize blended_score or weighted_roi_pct."""
    eval_fn = evaluate_fn or evaluate_walk_forward_benchmark
    bench_hash = benchmark_spec_hash(benchmark_spec)
    ev_ver = benchmark_spec.eval_contract_version
    max_sec = max_trial_seconds if max_trial_seconds is not None else default_max_trial_seconds()

    def objective(trial: optuna.Trial) -> float:
        candidate = strategy_from_optuna_trial(trial, baseline)
        sh = strategy_hash(asdict(candidate))

        def _eval() -> EvaluationResult:
            return eval_fn(candidate, baseline, benchmark_spec)

        t0 = time.perf_counter()
        result, err = run_with_timeout(_eval, timeout_seconds=max_sec)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        if err or result is None:
            row = ledger_row_from_optuna_trial(
                source="optuna_scalar",
                study_name=study_name,
                trial_number=trial.number,
                params=dict(trial.params),
                user_attrs={"feasible": False, "guardrail_passed": False},
                values=None,
                duration_ms=duration_ms,
                error=err or "no_result",
                eval_contract_version=ev_ver,
                benchmark_spec_hash=bench_hash,
                strategy_hash=sh,
                scalar_metric=None,
                scalar_metric_name=scalar_metric,
            )
            append_ledger_row(row)
            trial.set_user_attr("error", err or "no_result")
            return -1e12

        trial.set_user_attr("feasible", result.feasible)
        trial.set_user_attr("guardrail_passed", bool(result.guardrail_results.get("passed", False)))
        trial.set_user_attr("blended_score", result.blended_score)
        trial.set_user_attr("weighted_roi_pct", float(result.summary_metrics.get("weighted_roi_pct", 0.0) or 0.0))
        trial.set_user_attr("weighted_clv_avg", float(result.summary_metrics.get("weighted_clv_avg", 0.0) or 0.0))
        if scalar_metric == "weighted_roi_pct":
            val = float(result.summary_metrics.get("weighted_roi_pct", 0.0) or 0.0)
        else:
            val = float(result.blended_score)
        row = ledger_row_from_optuna_trial(
            source="optuna_scalar",
            study_name=study_name,
            trial_number=trial.number,
            params=dict(trial.params),
            user_attrs=dict(trial.user_attrs),
            values=[val],
            duration_ms=duration_ms,
            error=None,
            eval_contract_version=ev_ver,
            benchmark_spec_hash=bench_hash,
            strategy_hash=sh,
            scalar_metric=val,
            scalar_metric_name=scalar_metric,
        )
        append_ledger_row(row)
        return val

    return objective


def create_or_load_study(
    study_name: str,
    *,
    storage_path: Path | None = None,
) -> optuna.Study:
    """
    Create or load a multi-objective study (4 objectives, all maximize).

    Uses SQLite storage under output/research/optuna/ by default (gitignored).
    """
    path = storage_path or default_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.resolve()}"
    storage = RDBStorage(url)
    return optuna.create_study(
        study_name=study_name,
        storage=storage,
        directions=["maximize", "maximize", "maximize", "maximize"],
        load_if_exists=True,
    )


def create_or_load_scalar_study(
    study_name: str,
    *,
    storage_path: Path | None = None,
) -> optuna.Study:
    """Single-objective study (maximize scalar). Separate study name from MO studies."""
    path = storage_path or default_storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.resolve()}"
    storage = RDBStorage(url)
    return optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="maximize",
        load_if_exists=True,
    )


def run_mo_study(
    *,
    n_trials: int,
    baseline: StrategyConfig,
    benchmark_spec: WalkForwardBenchmarkSpec,
    study_name: str,
    storage_path: Path | None = None,
    n_jobs: int = 1,
    evaluate_fn: Callable[[StrategyConfig, StrategyConfig, WalkForwardBenchmarkSpec], EvaluationResult] | None = None,
    max_trial_seconds: float | None = None,
) -> optuna.Study:
    """
    Run n_trials of multi-objective optimization and return the study.

    Sequential by default (n_jobs=1) to avoid SQLite + golf.db contention.
    """
    study = create_or_load_study(study_name, storage_path=storage_path)
    objective = make_objective(
        baseline=baseline,
        benchmark_spec=benchmark_spec,
        study_name=study.study_name,
        evaluate_fn=evaluate_fn,
        max_trial_seconds=max_trial_seconds,
    )
    study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs, show_progress_bar=False)
    return study


def _log_scalar_trial_terminal(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
    """Print progress to stdout so the dashboard process shows activity between cycle start/end."""
    parts = [
        "[AUTORESEARCH]",
        "optuna_scalar",
        f"trial={trial.number}",
        f"state={trial.state.name}",
    ]
    if trial.value is not None:
        parts.append(f"value={float(trial.value):.6f}")
    line = " ".join(parts)
    print(line, flush=True)
    _logger.info("%s", line)


def run_scalar_study(
    *,
    n_trials: int,
    baseline: StrategyConfig,
    benchmark_spec: WalkForwardBenchmarkSpec,
    study_name: str,
    scalar_metric: Literal["blended_score", "weighted_roi_pct"] = "blended_score",
    storage_path: Path | None = None,
    n_jobs: int = 1,
    evaluate_fn: Callable[[StrategyConfig, StrategyConfig, WalkForwardBenchmarkSpec], EvaluationResult] | None = None,
    max_trial_seconds: float | None = None,
) -> optuna.Study:
    """Maximize one scalar (default: blended_score). Uses separate Optuna study name from MO."""
    effective_study_name = resolve_scalar_study_name(
        study_name,
        benchmark_spec=benchmark_spec,
        scalar_metric=scalar_metric,
    )
    study = create_or_load_scalar_study(effective_study_name, storage_path=storage_path)
    print(
        f"[AUTORESEARCH] optuna_scalar batch starting study={study.study_name} n_trials={n_trials}",
        flush=True,
    )
    _logger.info(
        "optuna_scalar batch starting study=%s n_trials=%s",
        study.study_name,
        n_trials,
    )
    objective = make_scalar_objective(
        baseline=baseline,
        benchmark_spec=benchmark_spec,
        study_name=study.study_name,
        scalar_metric=scalar_metric,
        evaluate_fn=evaluate_fn,
        max_trial_seconds=max_trial_seconds,
    )
    study.optimize(
        objective,
        n_trials=n_trials,
        n_jobs=n_jobs,
        show_progress_bar=False,
        callbacks=[_log_scalar_trial_terminal],
    )
    return study


def study_summary(study: optuna.Study) -> dict[str, Any]:
    """Compact JSON-serializable summary: Pareto trial count and best_trials params."""
    try:
        best = study.best_trials
    except Exception:
        best = []
    return {
        "study_name": study.study_name,
        "n_trials": len([t for t in study.trials if t.state == TrialState.COMPLETE]),
        "n_pareto": len(best),
        "pareto_trials": [
            {
                "number": t.number,
                "values": list(t.values) if t.values else [],
                "params": t.params,
                "user_attrs": dict(t.user_attrs),
            }
            for t in best
        ],
    }


def study_scalar_summary(study: optuna.Study) -> dict[str, Any]:
    """Summary for single-objective studies."""
    complete = [t for t in study.trials if t.state == TrialState.COMPLETE and t.value is not None]
    best_trial = None
    best_value = None
    promotable_trials = [
        t for t in complete
        if t.user_attrs.get("feasible") and t.user_attrs.get("guardrail_passed")
    ]
    best_promotable_trial = None
    best_promotable_value = None
    if complete:
        try:
            best_trial = study.best_trial
            best_value = study.best_value
        except ValueError:
            pass
    if promotable_trials:
        best_promotable_trial = max(promotable_trials, key=lambda trial: float(trial.value or float("-inf")))
        best_promotable_value = best_promotable_trial.value
    recent_trials = [
        {
            "number": trial.number,
            "value": trial.value,
            "params": trial.params,
            "user_attrs": dict(trial.user_attrs),
        }
        for trial in sorted(complete, key=lambda item: item.number, reverse=True)[:3]
    ]
    return {
        "study_name": study.study_name,
        "study_kind": "scalar",
        "n_trials": len(complete),
        "best_value": best_value,
        "best_trial": (
            {
                "number": best_trial.number,
                "value": best_trial.value,
                "params": best_trial.params,
                "user_attrs": dict(best_trial.user_attrs),
            }
            if best_trial
            else None
        ),
        "best_promotable_value": best_promotable_value,
        "best_promotable_trial": (
            {
                "number": best_promotable_trial.number,
                "value": best_promotable_trial.value,
                "params": best_promotable_trial.params,
                "user_attrs": dict(best_promotable_trial.user_attrs),
            }
            if best_promotable_trial
            else None
        ),
        "recent_trials": recent_trials,
    }


def study_dashboard_metrics(study: optuna.Study) -> dict[str, Any]:
    """
    Aggregate metrics for the dashboard when engine_mode is Optuna MO.

    The top blended-score candidate from research_proposals is not the same as the
    multi-objective study; use max ROI/CLV over completed trials for honest summaries.
    """
    complete = [t for t in study.trials if t.state == TrialState.COMPLETE and t.values]
    trial_max_roi: float | None = None
    trial_max_clv: float | None = None
    for t in complete:
        vals = t.values or []
        if len(vals) < 2:
            continue
        r, c = float(vals[0]), float(vals[1])
        trial_max_roi = r if trial_max_roi is None else max(trial_max_roi, r)
        trial_max_clv = c if trial_max_clv is None else max(trial_max_clv, c)

    try:
        pareto_trials = study.best_trials
    except Exception:
        pareto_trials = []

    pareto_max_roi: float | None = None
    pareto_max_clv: float | None = None
    pareto_promotable = 0
    for t in pareto_trials:
        vals = t.values or []
        if len(vals) >= 2:
            r, c = float(vals[0]), float(vals[1])
            pareto_max_roi = r if pareto_max_roi is None else max(pareto_max_roi, r)
            pareto_max_clv = c if pareto_max_clv is None else max(pareto_max_clv, c)
        ua = dict(t.user_attrs)
        if ua.get("feasible") and ua.get("guardrail_passed"):
            pareto_promotable += 1

    return {
        "study_kind": "mo",
        "n_complete_trials": len(complete),
        "trial_max_roi_pct": trial_max_roi,
        "trial_max_clv": trial_max_clv,
        "pareto_max_roi_pct": pareto_max_roi,
        "pareto_max_clv": pareto_max_clv,
        "pareto_promotable_count": pareto_promotable,
        "n_pareto": len(pareto_trials),
    }


def study_scalar_dashboard_metrics(study: optuna.Study) -> dict[str, Any]:
    """Dashboard metrics for scalar Optuna studies."""
    complete = [t for t in study.trials if t.state == TrialState.COMPLETE]
    best_roi: float | None = None
    best_blended: float | None = None
    best_clv: float | None = None
    promotable_trials = []
    for t in complete:
        ua = dict(t.user_attrs)
        r = ua.get("weighted_roi_pct")
        if r is not None:
            rf = float(r)
            best_roi = rf if best_roi is None else max(best_roi, rf)
        c = ua.get("weighted_clv_avg")
        if c is not None:
            cf = float(c)
            best_clv = cf if best_clv is None else max(best_clv, cf)
        b = ua.get("blended_score")
        if b is not None:
            bf = float(b)
            best_blended = bf if best_blended is None else max(best_blended, bf)
        if ua.get("feasible") and ua.get("guardrail_passed"):
            promotable_trials.append(t)
    best_value = None
    best_promotable_value = None
    if complete:
        try:
            best_value = study.best_value
        except ValueError:
            pass
    if promotable_trials:
        best_promotable_value = max(float(t.value or float("-inf")) for t in promotable_trials)
    return {
        "study_kind": "scalar",
        "n_complete_trials": len(complete),
        "best_value": best_value,
        "best_promotable_value": best_promotable_value,
        "trial_max_roi_pct": best_roi,
        "trial_max_clv": best_clv,
        "best_blended_score": best_blended,
        "pareto_promotable_count": len(promotable_trials),
    }
