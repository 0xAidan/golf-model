"""Unit tests for lab / v5 research hooks (isolated from baseline variant)."""

from __future__ import annotations

from src.lab_field_context import compute_field_strength_context
from src.lab_data_integrity import evaluate_lab_data_integrity
from src.matchup_value import _estimate_matchup_tie_probability, _v5_matchup_ev_void_tie
from src.models import form as form_module


def test_exponential_recent_weights_normalized():
    wts = form_module._v5_exponential_recent_weights(4, 0.35)
    assert len(wts) == 4
    assert abs(sum(wts) - 1.0) < 1e-9
    assert wts[0] > wts[-1]


def test_tie_probability_decreases_with_gap():
    t1 = _estimate_matchup_tie_probability(1.0, 0.2)
    t2 = _estimate_matchup_tie_probability(25.0, 0.2)
    assert t2 < t1


def test_void_tie_ev_reduces_to_binary_when_tie_zero():
    dec = 2.0
    p = 0.55
    ev0 = _v5_matchup_ev_void_tie(p, dec, 0.0)
    ev_alt = p * (dec - 1.0) - (1.0 - p)
    assert abs(ev0 - ev_alt) < 1e-9


def test_lab_data_integrity_returns_shape():
    report = evaluate_lab_data_integrity(-999999)
    assert "status" in report and "warnings" in report


def test_field_strength_context_empty_db():
    ctx = compute_field_strength_context(-999999)
    assert "index" in ctx
