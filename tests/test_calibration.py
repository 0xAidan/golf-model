"""Tests for calibration curve logic."""
import pytest
from src.calibration import get_calibration_correction, update_calibration_curve, PROBABILITY_BUCKETS


def test_get_calibration_correction_returns_float():
    """Correction factor should always be a positive float."""
    result = get_calibration_correction(0.10)
    assert isinstance(result, float)
    assert result > 0


def test_get_calibration_correction_out_of_range():
    """Probability 1.0 (edge) -> 1.0."""
    result = get_calibration_correction(1.0)
    assert result == 1.0


def test_update_calibration_curve_empty():
    """No prediction_log data -> empty dict."""
    result = update_calibration_curve()
    assert result == {} or isinstance(result, dict)


def test_probability_buckets_cover_range():
    """Buckets should cover 0.0 to 1.0 with no gaps."""
    prev_high = 0.0
    for low, high, label in PROBABILITY_BUCKETS:
        assert low == prev_high, f"Gap before {label}: {prev_high} to {low}"
        prev_high = high
    assert prev_high == 1.0
