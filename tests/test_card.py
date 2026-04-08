"""Tests for betting card output."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_generate_card_surfaces_top20_ranking_flags(tmp_path):
    from src.card import generate_card

    card_path = generate_card(
        tournament_name="Masters Tournament",
        course_name="Augusta National Golf Club",
        composite_results=[
            {
                "rank": 1,
                "player_key": "collin_morikawa",
                "player_display": "Collin Morikawa",
                "composite": 75.8,
                "course_fit": 76.0,
                "form": 79.9,
                "momentum": 56.9,
                "momentum_direction": "warming",
                "form_flags": ["layoff_risk", "injury_watch"],
                "form_notes": ["last competitive round 32 days ago"],
            }
        ],
        value_bets={},
        output_dir=str(tmp_path),
        matchup_bets=[],
        strategy_meta={
            "strategy_source": "live",
            "strategy_name": "verified_baseline_v4.2",
            "runtime_settings": {
                "blend_weights": {"course_fit": 0.45, "form": 0.45, "momentum": 0.10},
                "ev_threshold": 0.08,
            },
        },
        mode="full",
    )

    content = card_path.read_text(encoding="utf-8") if hasattr(card_path, "read_text") else open(card_path, "r", encoding="utf-8").read()

    assert "Ranking flags" in content
    assert "Collin Morikawa" in content
    assert "layoff_risk, injury_watch" in content
    assert "last competitive round 32 days ago" in content
