"""Marketing / public-post gates (stricter than internal is_value)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.marketing_safety import assess_matchup_marketing, assess_placement_marketing


def test_placement_fails_when_absolute_edge_too_small():
    row = {
        "bet_type": "outright",
        "ev_prob": 0.012,
        "market_implied_prob_raw": 0.011,
        "market_prob": 0.011,
        "ev": 0.20,
        "best_odds": 8000,
        "suspicious": False,
        "speculative": False,
        "ev_capped": False,
        "odds_quality": {},
    }
    safe, warnings = assess_placement_marketing(row)
    assert safe is False
    assert any("edge" in w.lower() for w in warnings)


def test_outright_long_price_fails_public_ev_cap_when_edge_is_real():
    """At +17500, meeting min absolute edge implies huge EV vs public cap."""
    row = {
        "bet_type": "outright",
        "ev_prob": 0.0267,
        "market_implied_prob_raw": 100.0 / 17600.0,
        "market_prob": 100.0 / 17600.0,
        "ev": 0.0267 * 176.0 - 1.0,
        "best_odds": 17500,
        "suspicious": False,
        "speculative": False,
        "ev_capped": False,
        "odds_quality": {},
    }
    safe, warnings = assess_placement_marketing(row)
    assert safe is False
    joined = " ".join(warnings).lower()
    assert "public cap" in joined or "long-shot" in joined


def test_matchup_passes_with_solid_edge():
    row = {
        "ev_prob": 0.62,
        "model_win_prob": 0.62,
        "market_implied_prob_raw": 0.565,
        "implied_prob": 0.565,
        "ev": 0.10,
    }
    safe, warnings = assess_matchup_marketing(row)
    assert safe is True
    assert warnings == []
