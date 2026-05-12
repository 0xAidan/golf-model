"""Hand-checked EV + matchup tier golden cases."""

from __future__ import annotations

import pytest

from src import config
from src.matchup_value import matchup_tier_and_rationale
from src.odds_utils import american_to_decimal, american_to_implied_prob, is_valid_odds
from src.value import compute_ev


def test_invalid_odds_flagged_for_pipeline() -> None:
    assert is_valid_odds(0) is False
    assert is_valid_odds(None) is False
def test_compute_ev_539_at_plus100() -> None:
    """p_ev=0.539, +100 → implied 0.5, decimal 2.0, EV = 0.078."""
    american = 100
    assert american_to_implied_prob(american) == pytest.approx(0.5)
    assert american_to_decimal(american) == pytest.approx(2.0)
    ev = compute_ev(0.539, american)
    assert ev == pytest.approx(0.078, rel=0, abs=1e-12)


def test_compute_ev_display_vs_ev_prob() -> None:
    """Same American line: different EV when EV uses calibrated prob vs display."""
    american = 200  # +200 → implied 1/3, decimal 3.0
    ev_display = compute_ev(0.30, american)
    ev_calibrated = compute_ev(0.36, american)
    assert ev_display == pytest.approx(-0.1)
    assert ev_calibrated == pytest.approx(0.08)


def test_matchup_tier_high_ev_low_gap_is_lean() -> None:
    """EV% in GOOD band but gap below GOOD gap → LEAN with structure rationale."""
    tier, drivers, rationale = matchup_tier_and_rationale(
        ev_pct=config.MATCHUP_TIER_GOOD_EV_PCT + 2.0,
        gap=config.MATCHUP_TIER_GOOD_GAP - 0.5,
    )
    assert tier == "LEAN"
    assert drivers["ev_good_band_met"] is True
    assert drivers["gap_good_met"] is False
    assert "structure gate" in rationale.lower()


def test_matchup_tier_same_ev_higher_gap_is_good() -> None:
    tier, drivers, _r = matchup_tier_and_rationale(
        ev_pct=config.MATCHUP_TIER_GOOD_EV_PCT + 2.0,
        gap=config.MATCHUP_TIER_GOOD_GAP + 1.0,
    )
    assert tier == "GOOD"
    assert drivers["good_tier_ev_and_gap_met"] is True


def test_matchup_tier_strong_requires_gap() -> None:
    """STRONG needs both EV band and gap > STRONG_GAP — high EV alone is not enough."""
    tier, _, rationale = matchup_tier_and_rationale(
        ev_pct=config.MATCHUP_TIER_STRONG_EV_PCT + 1.0,
        gap=config.MATCHUP_TIER_GOOD_GAP - 1.0,
    )
    assert tier == "LEAN"
    assert "structure" in rationale.lower() or "below" in rationale.lower()


def test_ratio_vs_v5_tie_ev_algebra_consistency_when_no_tie() -> None:
    """With tie_prob=0, void-tie EV reduces to decimal formula vs win prob."""
    from src.matchup_value import _v5_matchup_ev_void_tie

    p = 0.539
    dec = 2.0
    implied = 0.5
    ratio_ev = (p / implied) - 1.0
    v5_ev = _v5_matchup_ev_void_tie(p, dec, 0.0)
    assert v5_ev == pytest.approx(ratio_ev, rel=0, abs=1e-9)


def test_compute_ev_heavy_favorite_and_longshot() -> None:
    """Sanity EV at common American extremes."""
    assert compute_ev(0.72, -250) == pytest.approx(0.008, rel=0, abs=1e-9)
    assert compute_ev(0.02, 4000) == pytest.approx(-0.18, rel=0, abs=1e-6)


def test_compute_ev_zero_american_is_invalid_math() -> None:
    """american_to_decimal(0)==1.0 → EV is model-1 (caller should gate on is_valid_odds)."""
    assert compute_ev(0.5, 0) == pytest.approx(-0.5)
