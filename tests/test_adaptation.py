"""Tests for market performance aggregation and adaptation logic."""
import pytest
from src.adaptation import compute_roi_pct


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
