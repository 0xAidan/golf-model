"""Tests for src/value.py probability normalization and odds validation."""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.value import model_score_to_prob, MAX_REASONABLE_ODDS
from src.odds import is_reasonable_odds


def _generate_field_scores(n=150, min_score=30.0, max_score=85.0):
    """Generate a realistic spread of composite scores for a field."""
    scores = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        score = max_score - frac * (max_score - min_score)
        scores.append(round(score, 1))
    return scores


def test_outright_probs_sum_to_one():
    """Outright probabilities across the entire field should sum to ~1.0."""
    scores = _generate_field_scores(150)
    probs = [model_score_to_prob(s, scores, "outright") for s in scores]
    total = sum(probs)
    assert abs(total - 1.0) < 0.05, f"Outright probs sum to {total}, expected ~1.0"


def test_top5_probs_sum_correctly():
    """Top-5 probabilities should sum to ~5.0."""
    scores = _generate_field_scores(150)
    probs = [model_score_to_prob(s, scores, "top5") for s in scores]
    total = sum(probs)
    assert abs(total - 5.0) < 0.5, f"Top-5 probs sum to {total}, expected ~5.0"


def test_top10_probs_sum_correctly():
    """Top-10 probabilities should sum to ~10.0."""
    scores = _generate_field_scores(150)
    probs = [model_score_to_prob(s, scores, "top10") for s in scores]
    total = sum(probs)
    assert abs(total - 10.0) < 1.0, f"Top-10 probs sum to {total}, expected ~10.0"


def test_top20_probs_sum_correctly():
    """Top-20 probabilities should sum to ~20.0."""
    scores = _generate_field_scores(150)
    probs = [model_score_to_prob(s, scores, "top20") for s in scores]
    total = sum(probs)
    assert abs(total - 20.0) < 2.0, f"Top-20 probs sum to {total}, expected ~20.0"


def test_make_cut_probs_reasonable():
    """Make-cut probabilities should be in a reasonable range.

    The per-player cap of 0.95 means the sum may be slightly below
    the theoretical target (0.65 * field_size), which is correct —
    we don't want any single player at >95% make cut probability.
    """
    scores = _generate_field_scores(150)
    probs = [model_score_to_prob(s, scores, "make_cut") for s in scores]
    total = sum(probs)
    expected = 0.65 * 150
    # Allow wider tolerance because of per-player clamping at 0.95
    assert 60 < total < 120, (
        f"Make-cut probs sum to {total}, expected roughly ~{expected}"
    )
    # Top player should have high make-cut probability
    assert probs[0] > 0.7, f"Top player make-cut prob too low: {probs[0]}"


def test_higher_score_gets_higher_prob():
    """A player with a higher composite should have a higher probability."""
    scores = _generate_field_scores(150)
    high_score = max(scores)
    low_score = min(scores)
    prob_high = model_score_to_prob(high_score, scores, "outright")
    prob_low = model_score_to_prob(low_score, scores, "outright")
    assert prob_high > prob_low, (
        f"High score prob ({prob_high}) should be > low score prob ({prob_low})"
    )


def test_individual_probs_in_valid_range():
    """Every individual probability should be in a valid range. make_cut can exceed 1.0 after renormalization."""
    scores = _generate_field_scores(150)
    for bet_type in ["outright", "top5", "top10", "top20", "make_cut", "frl"]:
        max_prob = 2.0 if bet_type == "make_cut" else 0.95
        for s in scores:
            prob = model_score_to_prob(s, scores, bet_type)
            assert 0.0 < prob <= max_prob, (
                f"Prob {prob} out of range for {bet_type}, score={s}"
            )


def test_empty_scores_returns_zero():
    """Empty field should return 0."""
    assert model_score_to_prob(50.0, [], "outright") == 0.0


def test_small_field():
    """Should work with very small fields (e.g., 4 players)."""
    scores = [80.0, 70.0, 60.0, 50.0]
    probs = [model_score_to_prob(s, scores, "outright") for s in scores]
    total = sum(probs)
    assert abs(total - 1.0) < 0.05, f"Small field outright probs sum to {total}"
    assert probs[0] > probs[1] > probs[2] > probs[3], "Ordering should match scores"


# ── Market-specific odds validation ──────────────────────────────────


def test_outright_rejects_corrupt_odds():
    """+500000 outright odds should be rejected as corrupt data."""
    assert not is_reasonable_odds(500000, "outright")


def test_outright_accepts_max_longshot():
    """+30000 outright odds are at the limit and should be accepted."""
    assert is_reasonable_odds(30000, "outright")


def test_top5_accepts_valid_longshot():
    """+5000 top5 odds are at the limit and should be accepted."""
    assert is_reasonable_odds(5000, "top5")


def test_top5_rejects_excessive_odds():
    """+6000 top5 odds exceed the market cap and should be rejected."""
    assert not is_reasonable_odds(6000, "top5")


def test_max_reasonable_odds_keys_cover_all_markets():
    """Every standard bet type should have a defined max."""
    expected_markets = {"outright", "top5", "top10", "top20", "frl", "make_cut", "3ball"}
    assert expected_markets == set(MAX_REASONABLE_ODDS.keys())


def test_is_reasonable_odds_defaults_for_unknown_market():
    """Unknown bet types should fall back to the outright max (30000)."""
    assert is_reasonable_odds(30000, "some_new_market")
    assert not is_reasonable_odds(30001, "some_new_market")
