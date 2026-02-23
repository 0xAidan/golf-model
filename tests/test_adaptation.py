"""Tests for market performance aggregation and adaptation logic."""
import pytest
from src.adaptation import (
    compute_roi_pct,
    aggregate_market_performance_for_tournament,
    get_rolling_market_performance,
    get_adaptation_state,
    check_recovery,
)


def test_compute_roi_pct_positive():
    assert compute_roi_pct(10.0, 12.0) == 20.0


def test_compute_roi_pct_negative():
    assert compute_roi_pct(10.0, 8.0) == -20.0


def test_compute_roi_pct_zero_wagered():
    assert compute_roi_pct(0, 0) is None


def test_compute_roi_pct_none_wagered():
    assert compute_roi_pct(None, 5.0) is None


def test_compute_roi_pct_breakeven():
    assert compute_roi_pct(10.0, 10.0) == 0.0


def test_aggregate_market_performance_empty():
    """No prediction_log entries -> empty dict."""
    result = aggregate_market_performance_for_tournament(99999)
    assert result == {}


def test_get_rolling_market_performance_no_data():
    """No market_performance rows -> zeroed summary."""
    result = get_rolling_market_performance("outright")
    assert result["total_bets"] == 0
    assert result["roi_pct"] is None


def test_adaptation_state_below_min_sample():
    """Under 15 bets -> always 'normal', no adaptation."""
    state = get_adaptation_state("outright")
    assert state["state"] == "normal"
    assert state["ev_threshold"] == 0.05
    assert state["stake_multiplier"] == 1.0
    assert state["suppress"] is False


def test_check_recovery_no_data():
    """No data -> should_unfreeze False."""
    result = check_recovery("outright")
    assert result["should_unfreeze"] is False
    assert result["wins_in_window"] == 0


def test_compute_roi_pct_rounding():
    """ROI should be rounded to 2 decimal places."""
    result = compute_roi_pct(3.0, 3.7)
    assert result == 23.33
