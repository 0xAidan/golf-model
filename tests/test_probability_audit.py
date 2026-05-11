"""Tests for src/probability_audit field-sum helpers."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.probability_audit import (
    dg_market_sums,
    monotonicity_violations_for_player,
    softmax_field_sum,
    summarize_field_probability_health,
)
from src.value import model_score_to_prob


def test_softmax_top15_targets_fifteen_mass():
    scores = [80.0 - i * 0.3 for i in range(40)]
    probs = [model_score_to_prob(s, scores, "top15") for s in scores]
    assert sum(probs) == pytest.approx(15.0, abs=0.5)


def test_softmax_field_sum_helper_matches_manual():
    comp = [{"composite": float(85 - i)} for i in range(30)]
    s = softmax_field_sum(comp, "outright")
    scores = [r["composite"] for r in comp]
    manual = sum(model_score_to_prob(x, scores, "outright") for x in scores)
    assert s == pytest.approx(manual, rel=1e-9)


def test_dg_market_sums_empty():
    assert dg_market_sums({}, ("top5",)) == {"top5": 0.0}


def test_monotonicity_flags_inversion():
    row = {"outright": 0.25, "top5": 0.20}
    v = monotonicity_violations_for_player(row)
    assert any("outright" in x for x in v)


def test_summarize_field_probability_health_shape():
    comp = [{"composite": float(90 - i)} for i in range(20)]
    dg = {"a": {"top5": 0.1, "top10": 0.05}}
    r = summarize_field_probability_health(comp, dg)
    assert "softmax_sums" in r and "dg_sums" in r
    assert "top15_note" in r
