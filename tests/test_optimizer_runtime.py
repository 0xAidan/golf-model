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
