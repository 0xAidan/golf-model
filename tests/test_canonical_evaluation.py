"""Tests for backtester.research_lab.canonical evaluation primitives."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_compute_objective_vector_higher_is_better():
    from backtester.research_lab.canonical import compute_objective_vector_higher_is_better

    summary = {
        "weighted_roi_pct": 5.0,
        "weighted_clv_avg": 0.1,
        "weighted_calibration_error": 0.02,
        "max_drawdown_pct": 3.0,
    }
    roi, clv, neg_cal, neg_dd = compute_objective_vector_higher_is_better(summary)
    assert roi == 5.0
    assert clv == 0.1
    assert neg_cal == -0.02
    assert neg_dd == -3.0


def test_evaluation_from_walk_forward_dict_feasible(monkeypatch):
    from backtester.research_lab import canonical

    monkeypatch.setattr(
        "backtester.research_lab.canonical.src_config.get_autoresearch_guardrail_params",
        lambda: {
            "min_bets": 10,
            "max_clv_regression": 0.02,
            "max_calibration_regression": 0.03,
            "max_drawdown_regression": 10.0,
        },
    )
    raw = {
        "summary_metrics": {
            "total_bets": 50,
            "weighted_roi_pct": 2.0,
            "weighted_clv_avg": 0.05,
            "weighted_calibration_error": 0.04,
            "max_drawdown_pct": 1.0,
        },
        "baseline_summary_metrics": {"weighted_roi_pct": 1.0},
        "guardrail_results": {"passed": True, "reasons": [], "verdict": "promising"},
        "segmented_metrics": {},
    }
    er = canonical.evaluation_from_walk_forward_dict(raw)
    assert er.mode == "walk_forward"
    assert er.feasible is True
    assert er.objective_vector[0] == 2.0
    assert er.blended_score == canonical.compute_blended_score(raw["summary_metrics"], raw["guardrail_results"])


def test_evaluate_walk_forward_benchmark_delegates(monkeypatch):
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec, evaluate_walk_forward_benchmark
    from backtester.strategy import StrategyConfig

    called = {}

    def fake_wwf(**kwargs):
        called.update(kwargs)
        return {
            "summary_metrics": {
                "total_bets": 5,
                "weighted_roi_pct": 0.0,
                "weighted_clv_avg": 0.0,
                "weighted_calibration_error": 0.0,
                "max_drawdown_pct": 0.0,
            },
            "baseline_summary_metrics": {},
            "guardrail_results": {"passed": False, "reasons": ["insufficient_sample"], "verdict": "blocked"},
        }

    monkeypatch.setattr("backtester.research_lab.canonical.evaluate_weighted_walkforward", fake_wwf)
    monkeypatch.setattr(
        "backtester.research_lab.canonical.src_config.get_autoresearch_guardrail_params",
        lambda: {
            "min_bets": 30,
            "max_clv_regression": 0.02,
            "max_calibration_regression": 0.03,
            "max_drawdown_regression": 10.0,
        },
    )

    s = StrategyConfig(name="c")
    b = StrategyConfig(name="b")
    spec = WalkForwardBenchmarkSpec(years=[2024], min_train_events=1, test_window_size=1)
    er = evaluate_walk_forward_benchmark(s, b, spec)
    assert called["years"] == [2024]
    assert called["min_train_events"] == 1
    assert er.feasible is False


def test_evaluation_result_to_legacy_checkpoint_eval_dict():
    from backtester.research_lab.canonical import EvaluationResult

    er = EvaluationResult(
        mode="checkpoint_pilot",
        eval_contract_version=1,
        summary_metrics={"total_bets": 20, "weighted_roi_pct": 1.0},
        baseline_summary_metrics={},
        guardrail_results={"passed": True},
        blended_score=2.5,
        objective_vector=(1.0, 0.0, 0.0, 0.0),
        feasible=True,
        checkpoint_payload={"event": {}, "checkpoint_set_id": "v1", "candidate": {}, "baseline": {}, "checkpoints": []},
        metadata={"strategy_hash": "abc"},
    )
    legacy = er.to_legacy_checkpoint_eval_dict()
    assert legacy["metric"] == 2.5
    assert legacy["sample"] == 20
    assert "checkpoint_summary" in legacy
    assert legacy["metadata"]["strategy_hash"] == "abc"
