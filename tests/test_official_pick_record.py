"""Tests for official pick record dedupe."""

from src.official_pick_record import dedupe_grading_picks, grading_matchup_key


def test_round_and_tournament_matchups_stay_separate():
    picks = [
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "matchup",
            "market_type": "round_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "market_odds": "-110",
        },
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "matchup",
            "market_type": "tournament_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "market_odds": "-105",
        },
    ]
    assert grading_matchup_key(picks[0]) != grading_matchup_key(picks[1])
    assert len(dedupe_grading_picks(picks)) == 2


def test_same_identity_keeps_best_odds():
    picks = [
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "matchup",
            "market_type": "tournament_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "market_odds": "-110",
        },
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "matchup",
            "market_type": "tournament_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "market_odds": "+120",
        },
    ]
    deduped = dedupe_grading_picks(picks)
    assert len(deduped) == 1
    assert deduped[0]["market_odds"] == "+120"
