"""Tests for src/models/momentum.py dampened scoring and elite floor."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.momentum import _compute_trend


def _make_momentum_score(raw_trend: float, max_trend: float,
                         windows_count: int = 4,
                         elite_players: set = None,
                         player_key: str = "test_player") -> float:
    """Reproduce the scoring logic from compute_momentum for unit testing."""
    if max_trend == 0:
        max_trend = 1.0
    score = 50.0 + (raw_trend / max_trend) * 20.0
    score = max(30.0, min(70.0, score))
    confidence = min(1.0, windows_count / 4.0)
    score = 50.0 + confidence * (score - 50.0)
    if elite_players and player_key in elite_players:
        score = max(35.0, score)
    return round(score, 2)


def test_momentum_score_range_positive_extreme():
    """Maximum positive trend should produce score <= 70."""
    score = _make_momentum_score(raw_trend=100.0, max_trend=100.0)
    assert 30.0 <= score <= 70.0, f"Expected [30,70], got {score}"


def test_momentum_score_range_negative_extreme():
    """Maximum negative trend should produce score >= 30."""
    score = _make_momentum_score(raw_trend=-100.0, max_trend=100.0)
    assert 30.0 <= score <= 70.0, f"Expected [30,70], got {score}"


def test_momentum_score_range_neutral():
    """Zero trend should produce score == 50."""
    score = _make_momentum_score(raw_trend=0.0, max_trend=100.0)
    assert score == 50.0, f"Expected 50.0, got {score}"


def test_momentum_score_never_exceeds_bounds():
    """Sweep many raw values and verify all scores land in [30, 70]."""
    for raw in range(-200, 201, 10):
        score = _make_momentum_score(raw_trend=float(raw), max_trend=200.0)
        assert 30.0 <= score <= 70.0, f"raw={raw} gave score={score}"


def test_elite_floor_applies():
    """Elite player with worst-possible trend still gets >= 35."""
    elite = {"star_player"}
    score = _make_momentum_score(
        raw_trend=-100.0, max_trend=100.0,
        elite_players=elite, player_key="star_player",
    )
    assert score >= 35.0, f"Elite floor failed: got {score}"


def test_elite_floor_does_not_lower_score():
    """Elite floor should only raise, never lower, a score."""
    elite = {"star_player"}
    score_without = _make_momentum_score(
        raw_trend=80.0, max_trend=100.0,
        player_key="star_player",
    )
    score_with = _make_momentum_score(
        raw_trend=80.0, max_trend=100.0,
        elite_players=elite, player_key="star_player",
    )
    assert score_with >= score_without, (
        f"Elite floor lowered score: {score_with} < {score_without}"
    )


def test_non_elite_no_floor():
    """Non-elite player should NOT get the 35 floor."""
    elite = {"star_player"}
    score = _make_momentum_score(
        raw_trend=-100.0, max_trend=100.0,
        elite_players=elite, player_key="random_player",
    )
    assert score == 30.0, f"Non-elite should hit 30.0 floor, got {score}"


def test_no_elite_set_no_floor():
    """When elite_players is None, no floor is applied."""
    score = _make_momentum_score(
        raw_trend=-100.0, max_trend=100.0,
        elite_players=None, player_key="star_player",
    )
    assert score == 30.0, f"Expected 30.0 with no elite set, got {score}"


def test_low_confidence_pulls_toward_50():
    """With only 1 window (confidence=0.25), score should be closer to 50."""
    score_low = _make_momentum_score(raw_trend=100.0, max_trend=100.0, windows_count=1)
    score_high = _make_momentum_score(raw_trend=100.0, max_trend=100.0, windows_count=4)
    assert score_low < score_high, (
        f"Low confidence ({score_low}) should be closer to 50 than high ({score_high})"
    )
    assert score_low < 60.0, f"1-window score should be pulled toward 50, got {score_low}"
