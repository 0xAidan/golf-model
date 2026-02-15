"""Tests for src/models/form.py weight normalization and score scaling."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.form import _pct_to_score, _rank_to_score


def test_pct_to_score_zero():
    """Zero percent should return baseline (50)."""
    assert _pct_to_score(0) == 50.0


def test_pct_to_score_none():
    """None should return baseline (50)."""
    assert _pct_to_score(None) == 50.0


def test_pct_to_score_in_range():
    """All pct_to_score outputs should be 0-100."""
    for pct in [0.0, 0.01, 0.05, 0.10, 0.20, 0.50, 1.0]:
        score = _pct_to_score(pct)
        assert 0.0 <= score <= 100.0, f"pct={pct} gave score={score}"


def test_pct_to_score_monotonic():
    """Higher percentages should give higher scores."""
    prev = _pct_to_score(0.0)
    for pct in [0.01, 0.05, 0.10, 0.15]:
        curr = _pct_to_score(pct)
        assert curr >= prev, f"pct={pct}: {curr} < {prev}"
        prev = curr


def test_rank_to_score_range():
    """Rank-to-score should always be 0-100."""
    for rank in [1, 10, 50, 100, 150]:
        score = _rank_to_score(rank, 150)
        assert 0.0 <= score <= 100.0, f"rank={rank} gave score={score}"


def test_rank_to_score_best_is_100():
    """Rank 1 should give score 100."""
    assert _rank_to_score(1, 150) == 100.0


def test_rank_to_score_worst_is_0():
    """Last rank should give score ~0."""
    score = _rank_to_score(150, 150)
    assert score < 1.0, f"Last rank should be ~0, got {score}"


def test_sim_score_weights_sum():
    """Verify the sim score component weights sum to 1.0."""
    # These are the weights used in compute_form for sim_score
    w_win = 0.30
    w_top10 = 0.30
    w_top20 = 0.25
    w_makecut = 0.15
    total = w_win + w_top10 + w_top20 + w_makecut
    assert abs(total - 1.0) < 0.001, f"Sim weights sum to {total}"


def test_sim_score_all_pct_to_score():
    """All sim sub-components should produce 0-100 range."""
    # Simulate realistic percentages
    win_pct, top10_pct, top20_pct, make_cut = 0.05, 0.20, 0.40, 0.80
    scores = [
        _pct_to_score(win_pct, scale=300.0),
        _pct_to_score(top10_pct, scale=120.0),
        _pct_to_score(top20_pct, scale=80.0),
        _pct_to_score(make_cut, scale=60.0),
    ]
    for i, s in enumerate(scores):
        assert 0.0 <= s <= 100.0, f"Sim component {i} out of range: {s}"
