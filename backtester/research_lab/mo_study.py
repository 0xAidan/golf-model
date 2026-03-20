"""Multi-objective Optuna study over StrategyConfig using canonical walk-forward evaluation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import optuna
from optuna.storages import RDBStorage
from optuna.trial import TrialState

from backtester.research_lab.canonical import EvaluationResult, WalkForwardBenchmarkSpec, evaluate_walk_forward_benchmark
from backtester.research_lab.param_space import strategy_from_optuna_trial
from backtester.strategy import StrategyConfig

_logger = logging.getLogger("research_lab.mo_study")

DEFAULT_OPTUNA_DIR = Path("output") / "research" / "optuna"


def default_storage_path() -> Path:
    return DEFAULT_OPTUNA_DIR / "studies.db"


def make_objective(
    *,
    baseline: StrategyConfig,
    benchmark_spec: WalkForwardBenchmarkSpec,
    evaluate_fn: Callable[[StrategyConfig, StrategyConfig, WalkForwardBenchmarkSpec], EvaluationResult] | None = None,
) -> Callable[[optuna.Trial], tuple[float, float, float, float]]:
    """Return an Optuna objective that maximizes all four canonical objectives (higher is better)."""
    eval_fn = evaluate_fn or evaluate_walk_forward_benchmark

    def objective(trial: optuna.Trial) -> tuple[float, float, float, float]:
        candidate = strategy_from_optuna_trial(trial, baseline)
        result = eval_fn(candidate, baseline, benchmark_spec)
        trial.set_user_attr("feasible", result.feasible)
        trial.set_user_attr("guardrail_passed", bool(result.guardrail_results.get("passed", False)))
        trial.set_user_attr("blended_score", result.blended_score)
        trial.set_user_attr("weighted_roi_pct", float(result.summary_metrics.get("weighted_roi_pct", 0.0) or 0.0))
        trial.set_user_attr("weighted_clv_avg", float(result.summary_metrics.get("weighted_clv_avg", 0.0) or 0.0))
        roi, clv, neg_cal, neg_dd = result.objective_vector
        return (roi, clv, neg_cal, neg_dd)

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


def run_mo_study(
    *,
    n_trials: int,
    baseline: StrategyConfig,
    benchmark_spec: WalkForwardBenchmarkSpec,
    study_name: str,
    storage_path: Path | None = None,
    n_jobs: int = 1,
    evaluate_fn: Callable[[StrategyConfig, StrategyConfig, WalkForwardBenchmarkSpec], EvaluationResult] | None = None,
) -> optuna.Study:
    """
    Run n_trials of multi-objective optimization and return the study.

    Sequential by default (n_jobs=1) to avoid SQLite + golf.db contention.
    """
    study = create_or_load_study(study_name, storage_path=storage_path)
    objective = make_objective(baseline=baseline, benchmark_spec=benchmark_spec, evaluate_fn=evaluate_fn)
    study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs, show_progress_bar=False)
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
        "n_complete_trials": len(complete),
        "trial_max_roi_pct": trial_max_roi,
        "trial_max_clv": trial_max_clv,
        "pareto_max_roi_pct": pareto_max_roi,
        "pareto_max_clv": pareto_max_clv,
        "pareto_promotable_count": pareto_promotable,
        "n_pareto": len(pareto_trials),
    }
