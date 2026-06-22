"""Tests for official pick record dedupe."""

from src.official_pick_record import dedupe_grading_picks, dedupe_inventory_rows, grading_matchup_key


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
            "market_book": "fd",
        },
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "matchup",
            "market_type": "tournament_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "market_odds": "+120",
            "market_book": "dk",
        },
    ]
    deduped = dedupe_grading_picks(picks)
    assert len(deduped) == 1
    assert deduped[0]["market_odds"] == "+120"
    assert deduped[0]["market_book"] == "dk"


def test_outright_duplicates_collapse_to_one():
    picks = [
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "outright",
            "market_type": "outright",
            "player_key": "matt_fitzpatrick",
            "market_odds": "+2200",
        },
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "outright",
            "market_type": "outright",
            "player_key": "matt_fitzpatrick",
            "market_odds": "+3300",
        },
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "top10",
            "market_type": "top10",
            "player_key": "keith_mitchell",
            "market_odds": "+550",
        },
        {
            "source": "cockpit",
            "model_variant": "baseline",
            "bet_type": "top10",
            "market_type": "top10",
            "player_key": "keith_mitchell",
            "market_odds": "+650",
        },
    ]
    deduped = dedupe_grading_picks(picks)
    assert len(deduped) == 2
    by_type = {row["bet_type"]: row["market_odds"] for row in deduped}
    assert by_type["outright"] == "+3300"
    assert by_type["top10"] == "+650"


def test_inventory_dedupes_outrights_across_books():
    rows = [
        {
            "market_family": "outright",
            "bet_type": "outright",
            "market_type": "outright",
            "player_key": "matt_fitzpatrick",
            "book": "fd",
            "odds": "+2200",
            "ev": 0.05,
        },
        {
            "market_family": "outright",
            "bet_type": "outright",
            "market_type": "outright",
            "player_key": "matt_fitzpatrick",
            "book": "dk",
            "odds": "+3300",
            "ev": 0.06,
        },
    ]
    deduped = dedupe_inventory_rows(rows, lane="dashboard")
    assert len(deduped) == 1
    assert deduped[0]["odds"] == "+3300"
