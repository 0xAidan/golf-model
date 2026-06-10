"""Tests for the runtime-health recorder and silent-fallback surfacing (defect P1-1)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import runtime_health


def test_recorder_ring_buffer_and_filter():
    runtime_health.clear()
    runtime_health.record_strategy_config_error("global", "active_strategy", "boom")
    runtime_health.record_strategy_config_error("global", "model_registry", "bad json")
    events = runtime_health.recent_strategy_config_errors()
    assert len(events) == 2
    assert events[-1]["source"] == "model_registry"
    assert events[0]["kind"] == "strategy_config_error"
    runtime_health.clear()
    assert runtime_health.recent_strategy_config_errors() == []


def test_corrupt_active_strategy_records_error_and_falls_back(tmp_db):
    """A corrupt active_strategy JSON must fall back to default AND surface a degradation."""
    from backtester import experiments
    from src import db

    runtime_health.clear()
    conn = db.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO active_strategy (scope, strategy_config_json) VALUES (?, ?)",
        ("global", "{not valid json"),
    )
    conn.commit()
    conn.close()

    strategy = experiments.get_active_strategy("global")
    # Falls back to a safe default rather than raising.
    assert strategy is not None

    errors = runtime_health.recent_strategy_config_errors()
    assert any(e["source"] == "active_strategy" for e in errors)
    runtime_health.clear()
