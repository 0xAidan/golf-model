"""Tests for market performance aggregation and adaptation logic."""
import pytest
from src.adaptation import (
    compute_roi_pct,
    aggregate_market_performance_for_tournament,
    get_rolling_market_performance,
    get_adaptation_state,
    check_recovery,
    log_ai_adjustment,
    evaluate_ai_adjustments,
    get_ai_adjustment_config,
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


def test_log_ai_adjustment():
    """Should log without error."""
    from src import db
    conn = db.get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO tournaments (id, name, year) VALUES (99999, 'test_tournament', 2099)"
    )
    conn.commit()
    conn.close()

    log_ai_adjustment(99999, "test_player", 3.0, "test reasoning")

    conn = db.get_conn()
    conn.execute("DELETE FROM ai_adjustments WHERE tournament_id = 99999")
    conn.execute("DELETE FROM tournaments WHERE id = 99999")
    conn.commit()
    conn.close()


def test_evaluate_ai_adjustments_empty():
    """No adjustments for tournament -> zeroed summary."""
    result = evaluate_ai_adjustments(99998)
    assert result["total"] == 0
    assert result["helpful"] == 0


def test_get_ai_adjustment_config_default():
    """With minimal data, should return enabled with cap from config (3.0 per plan)."""
    config = get_ai_adjustment_config()
    assert config["enabled"] is True
    assert config["cap"] == 3.0
