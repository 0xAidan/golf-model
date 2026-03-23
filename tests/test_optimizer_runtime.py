"""Tests for the continuous optimizer runtime."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_optimizer_runtime_can_start_and_stop(monkeypatch):
    from backtester import optimizer_runtime

    calls = {"count": 0}

    def fake_run_autoresearch_cycle(**kwargs):
        calls["count"] += 1
        return {"cycle_key": f"cycle-{calls['count']}", "winner": None}

    monkeypatch.setattr(
        "backtester.optimizer_runtime.run_autoresearch_cycle",
        fake_run_autoresearch_cycle,
    )

    optimizer_runtime.stop_continuous_optimizer()
    started = optimizer_runtime.start_continuous_optimizer(
        scope="global",
        interval_seconds=0.05,
        max_candidates=1,
        years=[2025],
        engine_mode="research_cycle",
    )
    time.sleep(0.12)
    status_while_running = optimizer_runtime.get_optimizer_status()
    stopped = optimizer_runtime.stop_continuous_optimizer()
    status_after_stop = optimizer_runtime.get_optimizer_status()

    assert started["running"] is True
    assert status_while_running["running"] is True
    assert status_while_running["run_count"] >= 1
    assert calls["count"] >= 1
    assert stopped["running"] is False
    assert status_after_stop["running"] is False


def test_optimizer_runtime_can_record_manual_scalar_result():
    from backtester import optimizer_runtime

    optimizer_runtime.stop_continuous_optimizer()
    optimizer_runtime.record_manual_autoresearch_result(
        {
            "evaluation_mode": "optuna_scalar",
            "optuna_scalar_summary": {
                "best_value": 4.4,
                "best_promotable_trial": {
                    "number": 2,
                    "value": 4.4,
                    "user_attrs": {"feasible": True, "guardrail_passed": True},
                },
                "recent_trials": [],
            },
        },
        scope="global",
        engine_mode="optuna_scalar",
        scalar_objective="weighted_roi_pct",
        optuna_scalar_study_name="golf_scalar_simple",
    )
    status = optimizer_runtime.get_optimizer_status()

    assert status["engine_mode"] == "optuna_scalar"
    assert status["scalar_objective"] == "weighted_roi_pct"
    assert status["optuna_scalar_study_name"] == "golf_scalar_simple"
    assert status["last_result"]["evaluation_mode"] == "optuna_scalar"
    assert status["last_run_finished_at"] is not None


def test_optimizer_runtime_reset_clears_manual_state():
    from backtester import optimizer_runtime

    optimizer_runtime.record_manual_autoresearch_result(
        {
            "evaluation_mode": "optuna_scalar",
            "optuna_scalar_summary": {
                "best_value": 4.4,
                "best_promotable_trial": {
                    "number": 2,
                    "value": 4.4,
                    "user_attrs": {"feasible": True, "guardrail_passed": True},
                },
                "recent_trials": [],
            },
        },
        scope="global",
        engine_mode="optuna_scalar",
        scalar_objective="weighted_roi_pct",
        optuna_scalar_study_name="golf_scalar_simple",
    )

    reset = optimizer_runtime.reset_optimizer_state()

    assert reset["running"] is False
    assert reset["run_count"] == 0
    assert reset["last_result"] is None
    assert reset["last_run_finished_at"] is None
    assert reset["last_error"] is None
    assert reset["engine_mode"] == "optuna_scalar"
    assert reset["scalar_objective"] == "weighted_roi_pct"
    assert reset["optuna_scalar_study_name"] == "golf_scalar_simple"
