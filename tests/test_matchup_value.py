"""Tests for real matchup value calculator."""
import pytest
from src.matchup_value import find_matchup_value_bets, _american_to_implied_prob, _parse_best_odds


def test_american_to_implied_prob_positive():
    assert abs(_american_to_implied_prob(100) - 0.5) < 0.001


def test_american_to_implied_prob_negative():
    assert abs(_american_to_implied_prob(-200) - 0.6667) < 0.01


def test_american_to_implied_prob_zero():
    assert _american_to_implied_prob(0) is None


def test_parse_best_odds_nested():
    matchup = {
        "odds": {
            "draftkings": {"p1": 110, "p2": -130},
            "fanduel": {"p1": 105, "p2": -125},
        }
    }
    p1, p2 = _parse_best_odds(matchup)
    assert p1 == (110, "draftkings")
    assert p2 == (-125, "fanduel")


def test_parse_best_odds_top_level():
    matchup = {"p1_odds": 110, "p2_odds": -130}
    p1, p2 = _parse_best_odds(matchup)
    assert p1 == (110, "datagolf")
    assert p2 == (-130, "datagolf")


def test_parse_best_odds_empty():
    p1, p2 = _parse_best_odds({})
    assert p1 is None
    assert p2 is None


def test_find_matchup_value_bets_empty_odds():
    """No matchup odds -> no bets."""
    result = find_matchup_value_bets([], [], ev_threshold=0.05)
    assert result == []


def test_find_matchup_value_bets_no_composite_match():
    """Matchup players not in composite results -> no bets."""
    matchups = [{"p1_player_name": "John Doe", "p2_player_name": "Jane Doe"}]
    composite = [{"player_key": "someone_else", "player_display": "Someone Else",
                  "composite": 70.0, "form": 60.0, "course_fit": 55.0}]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.05)
    assert result == []


def test_find_matchup_value_bets_basic():
    """Basic matchup with clear edge should return value bet."""
    composite = [
        {"player_key": "scottie_scheffler", "player_display": "Scottie Scheffler",
         "composite": 80.0, "form": 90.0, "course_fit": 70.0, "momentum": 60.0},
        {"player_key": "davis_thompson", "player_display": "Davis Thompson",
         "composite": 50.0, "form": 40.0, "course_fit": 45.0, "momentum": 50.0},
    ]
    matchups = [{
        "p1_player_name": "Scottie Scheffler",
        "p2_player_name": "Davis Thompson",
        "p1_odds": 110,
        "p2_odds": -130,
    }]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01)
    assert len(result) >= 1
    assert result[0]["pick"] == "Scottie Scheffler"
    assert result[0]["ev"] > 0
    assert result[0]["model_win_prob"] > 0.5
    assert result[0]["adaptation_state"] == "normal"


def test_find_matchup_value_bets_picks_stronger_player():
    """Should always pick the player with higher composite, even if listed second."""
    composite = [
        {"player_key": "player_a", "player_display": "Player A",
         "composite": 40.0, "form": 50.0, "course_fit": 50.0, "momentum": 50.0},
        {"player_key": "player_b", "player_display": "Player B",
         "composite": 75.0, "form": 80.0, "course_fit": 70.0, "momentum": 60.0},
    ]
    matchups = [{
        "p1_player_name": "Player A",
        "p2_player_name": "Player B",
        "p1_odds": -130,
        "p2_odds": 110,
    }]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01)
    assert len(result) >= 1
    assert result[0]["pick"] == "Player B"


def test_find_matchup_value_bets_no_odds_data():
    """Matchup with no odds at all -> skipped."""
    composite = [
        {"player_key": "scottie_scheffler", "player_display": "Scottie Scheffler",
         "composite": 80.0, "form": 90.0, "course_fit": 70.0, "momentum": 60.0},
        {"player_key": "davis_thompson", "player_display": "Davis Thompson",
         "composite": 50.0, "form": 40.0, "course_fit": 45.0, "momentum": 50.0},
    ]
    matchups = [{
        "p1_player_name": "Scottie Scheffler",
        "p2_player_name": "Davis Thompson",
    }]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01)
    assert result == []


def test_find_matchup_value_bets_equal_composites():
    """Equal composites -> no edge -> skipped."""
    composite = [
        {"player_key": "player_a", "player_display": "Player A",
         "composite": 60.0, "form": 60.0, "course_fit": 60.0, "momentum": 50.0},
        {"player_key": "player_b", "player_display": "Player B",
         "composite": 60.0, "form": 60.0, "course_fit": 60.0, "momentum": 50.0},
    ]
    matchups = [{
        "p1_player_name": "Player A",
        "p2_player_name": "Player B",
        "p1_odds": 100,
        "p2_odds": -120,
    }]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01)
    assert result == []


def test_find_matchup_value_bets_ev_threshold_filters():
    """Matchups below EV threshold should be excluded."""
    composite = [
        {"player_key": "player_a", "player_display": "Player A",
         "composite": 52.0, "form": 51.0, "course_fit": 50.0, "momentum": 50.0},
        {"player_key": "player_b", "player_display": "Player B",
         "composite": 50.0, "form": 50.0, "course_fit": 50.0, "momentum": 50.0},
    ]
    matchups = [{
        "p1_player_name": "Player A",
        "p2_player_name": "Player B",
        "p1_odds": -110,
        "p2_odds": -110,
    }]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.50)
    assert result == []


def test_find_matchup_value_bets_sorted_by_ev():
    """Results should be sorted by EV descending."""
    composite = [
        {"player_key": "a", "player_display": "A", "composite": 90.0, "form": 90.0, "course_fit": 80.0, "momentum": 50.0},
        {"player_key": "b", "player_display": "B", "composite": 50.0, "form": 50.0, "course_fit": 50.0, "momentum": 50.0},
        {"player_key": "c", "player_display": "C", "composite": 70.0, "form": 70.0, "course_fit": 60.0, "momentum": 50.0},
        {"player_key": "d", "player_display": "D", "composite": 50.0, "form": 50.0, "course_fit": 50.0, "momentum": 50.0},
    ]
    matchups = [
        {"p1_player_name": "C", "p2_player_name": "D", "p1_odds": 120, "p2_odds": -140},
        {"p1_player_name": "A", "p2_player_name": "B", "p1_odds": 150, "p2_odds": -170},
    ]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01)
    assert len(result) >= 2
    assert result[0]["ev"] >= result[1]["ev"]
