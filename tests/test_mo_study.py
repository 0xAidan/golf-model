"""Tests for Optuna multi-objective study (mocked evaluation)."""

import sys
from pathlib import Path

import optuna
from optuna.trial import FixedTrial, TrialState

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_strategy_from_optuna_trial_softmax_sums_to_one():
    from backtester.research_lab.param_space import strategy_from_optuna_trial
    from backtester.strategy import StrategyConfig

    trial = FixedTrial(
        {
            "logit_sub_course_fit": 0.0,
            "logit_sub_form": 1.0,
            "logit_sub_momentum": -0.5,
            "min_ev": 0.05,
            "kelly_fraction": 0.25,
            "softmax_temp": 1.0,
            "max_implied_prob": 0.5,
        }
    )
    base = StrategyConfig(name="base")
    cfg = strategy_from_optuna_trial(trial, base)
    s = cfg.w_sub_course_fit + cfg.w_sub_form + cfg.w_sub_momentum
    assert abs(s - 1.0) < 1e-5


def test_run_mo_study_with_mock_eval(tmp_path):
    from backtester.research_lab.canonical import EvaluationResult, WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import run_mo_study, study_summary
    from backtester.strategy import StrategyConfig

    def fake_eval(candidate, baseline, spec):
        return EvaluationResult(
            mode="walk_forward",
            eval_contract_version=2,
            summary_metrics={
                "weighted_roi_pct": 2.5,
                "weighted_clv_avg": 0.1,
                "weighted_calibration_error": 0.02,
                "max_drawdown_pct": 3.0,
                "total_bets": 100,
            },
            baseline_summary_metrics={},
            guardrail_results={"passed": True, "reasons": [], "verdict": "promising"},
            blended_score=5.0,
            objective_vector=(2.5, 0.1, -0.02, -3.0),
            feasible=True,
        )

    base = StrategyConfig(name="b")
    spec = WalkForwardBenchmarkSpec(years=[2024])
    db_path = tmp_path / "opt.db"
    study = run_mo_study(
        n_trials=4,
        baseline=base,
        benchmark_spec=spec,
        study_name="unit_test_mo",
        storage_path=db_path,
        evaluate_fn=fake_eval,
    )
    complete = [t for t in study.trials if t.state == TrialState.COMPLETE]
    assert len(complete) == 4
    summ = study_summary(study)
    assert summ["n_trials"] == 4
    assert summ["n_pareto"] >= 1
    assert len(summ["pareto_trials"]) == summ["n_pareto"]

    from backtester.research_lab.mo_study import study_dashboard_metrics

    dash = study_dashboard_metrics(study)
    assert dash["n_complete_trials"] == 4
    assert dash["trial_max_roi_pct"] == 2.5
    assert dash["trial_max_clv"] == 0.1
    assert dash["pareto_promotable_count"] >= 1


def test_run_scalar_study_with_mock_eval(tmp_path):
    from backtester.research_lab.canonical import EvaluationResult, WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import run_scalar_study, study_scalar_dashboard_metrics, study_scalar_summary
    from backtester.strategy import StrategyConfig

    def fake_eval(candidate, baseline, spec):
        return EvaluationResult(
            mode="walk_forward",
            eval_contract_version=2,
            summary_metrics={
                "weighted_roi_pct": 3.0,
                "weighted_clv_avg": 0.11,
                "weighted_calibration_error": 0.02,
                "max_drawdown_pct": 3.0,
                "total_bets": 100,
            },
            baseline_summary_metrics={},
            guardrail_results={"passed": True, "reasons": [], "verdict": "promising"},
            blended_score=6.0,
            objective_vector=(3.0, 0.11, -0.02, -3.0),
            feasible=True,
        )

    base = StrategyConfig(name="b")
    spec = WalkForwardBenchmarkSpec(years=[2024])
    db_path = tmp_path / "opt_scalar.db"
    study = run_scalar_study(
        n_trials=3,
        baseline=base,
        benchmark_spec=spec,
        study_name="unit_test_scalar",
        scalar_metric="blended_score",
        storage_path=db_path,
        evaluate_fn=fake_eval,
    )
    summ = study_scalar_summary(study)
    assert summ["study_kind"] == "scalar"
    assert summ["best_value"] == 6.0
    dash = study_scalar_dashboard_metrics(study)
    assert dash["study_kind"] == "scalar"
    assert dash["n_complete_trials"] == 3


def test_resolve_scalar_study_name_varies_by_metric_and_benchmark():
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import resolve_scalar_study_name

    study_name = "golf_scalar_dashboard"
    spec_2024 = WalkForwardBenchmarkSpec(years=[2024])
    spec_2025 = WalkForwardBenchmarkSpec(years=[2025])

    roi_name = resolve_scalar_study_name(
        study_name,
        benchmark_spec=spec_2024,
        scalar_metric="weighted_roi_pct",
    )
    blended_name = resolve_scalar_study_name(
        study_name,
        benchmark_spec=spec_2024,
        scalar_metric="blended_score",
    )
    next_year_name = resolve_scalar_study_name(
        study_name,
        benchmark_spec=spec_2025,
        scalar_metric="weighted_roi_pct",
    )

    assert roi_name != blended_name
    assert roi_name != next_year_name
    assert roi_name.startswith(study_name)


def test_scalar_summary_distinguishes_best_overall_from_promotable_trial():
    from backtester.research_lab.mo_study import (
        study_scalar_dashboard_metrics,
        study_scalar_summary,
    )

    study = optuna.create_study(direction="maximize")
    study.add_trial(
        optuna.trial.create_trial(
            params={},
            distributions={},
            value=12.0,
            user_attrs={
                "feasible": False,
                "guardrail_passed": False,
                "weighted_roi_pct": 12.0,
                "weighted_clv_avg": 0.08,
                "blended_score": 12.0,
            },
            state=TrialState.COMPLETE,
        )
    )
    study.add_trial(
        optuna.trial.create_trial(
            params={},
            distributions={},
            value=8.5,
            user_attrs={
                "feasible": True,
                "guardrail_passed": True,
                "weighted_roi_pct": 8.5,
                "weighted_clv_avg": 0.06,
                "blended_score": 8.5,
            },
            state=TrialState.COMPLETE,
        )
    )

    summary = study_scalar_summary(study)
    assert summary["best_value"] == 12.0
    assert summary["best_trial"]["number"] == 0
    assert summary["best_promotable_value"] == 8.5
    assert summary["best_promotable_trial"]["number"] == 1
    assert [trial["number"] for trial in summary["recent_trials"]] == [1, 0]

    dashboard = study_scalar_dashboard_metrics(study)
    assert dashboard["best_value"] == 12.0
    assert dashboard["best_promotable_value"] == 8.5
    assert dashboard["pareto_promotable_count"] == 1
