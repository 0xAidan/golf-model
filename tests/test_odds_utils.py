"""Tests for src/odds_utils canonical conversions and Masters-style EV fixtures."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.odds_utils import american_to_decimal, american_to_implied_prob
from src.value import compute_ev


def test_american_to_decimal_masters_samples():
    assert american_to_decimal(17500) == pytest.approx(176.0)
    assert american_to_decimal(1300) == pytest.approx(14.0)
    assert american_to_decimal(8000) == pytest.approx(81.0)
    assert american_to_decimal(10026) == pytest.approx(101.26)
    neg = american_to_decimal(-130)
    assert neg == pytest.approx(1.0 + 100.0 / 130.0)


def test_american_to_implied_masters_samples():
    assert american_to_implied_prob(17500) == pytest.approx(100.0 / 17600.0, rel=1e-9)
    assert american_to_implied_prob(1300) == pytest.approx(100.0 / 1400.0, rel=1e-9)
    assert american_to_implied_prob(-130) == pytest.approx(130.0 / 230.0, rel=1e-9)


def test_ev_kitayama_outright_plus17500():
    p = 0.0069
    ev = compute_ev(p, 17500)
    assert ev == pytest.approx(p * 176.0 - 1.0, rel=1e-9)
    assert ev * 100 == pytest.approx(21.44, abs=0.02)


def test_ev_mcnealy_top5_plus1300_dead_heat_matches_legacy_headline_band():
    """8.7% EV band when EV uses dead-heat-adjusted prob vs ~14.4% on raw blend."""
    blend = 0.0817
    ev_raw = compute_ev(blend, 1300)
    assert ev_raw * 100 == pytest.approx(14.38, abs=0.05)
    ev_prob = blend * (1.0 - config.DEAD_HEAT_DISCOUNT_TOP5)
    ev_dh = compute_ev(ev_prob, 1300)
    assert ev_dh * 100 == pytest.approx(8.66, abs=0.05)


def test_ev_minwoo_minus130():
    ev = compute_ev(0.628, -130)
    assert ev * 100 == pytest.approx(11.08, abs=0.05)
