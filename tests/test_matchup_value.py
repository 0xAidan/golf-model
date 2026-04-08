"""Tests for real matchup value calculator."""
import pytest
from src.odds import american_to_implied_prob
from src.matchup_value import (
    _extract_dg_prob_from_matchup,
    _parse_best_odds,
    find_matchup_value_bets,
)


def test_american_to_implied_prob_positive():
    assert abs(american_to_implied_prob(100) - 0.5) < 0.001


def test_american_to_implied_prob_negative():
    assert abs(american_to_implied_prob(-200) - 0.6667) < 0.01


def test_american_to_implied_prob_zero():
    # odds.american_to_implied_prob returns 0.0 for invalid (price 0)
    assert american_to_implied_prob(0) == 0.0


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
    """Flat DG model odds (p1_odds/p2_odds) are NOT sportsbook lines — should return None."""
    matchup = {"p1_odds": 110, "p2_odds": -130}
    p1, p2 = _parse_best_odds(matchup)
    assert p1 is None
    assert p2 is None


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
        "odds": {"bet365": {"p1": 110, "p2": -130}},
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
        "odds": {"fanduel": {"p1": -130, "p2": 110}},
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
        {"p1_player_name": "C", "p2_player_name": "D", "odds": {"caesars": {"p1": 120, "p2": -140}}},
        {"p1_player_name": "A", "p2_player_name": "B", "odds": {"caesars": {"p1": 150, "p2": -170}}},
    ]
    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01)
    assert len(result) >= 2
    assert result[0]["ev"] >= result[1]["ev"]


def test_find_matchup_value_bets_returns_all_qualifying_books(monkeypatch):
    """When no required_book is provided, all qualifying books should be returned."""
    monkeypatch.setattr("src.datagolf.fetch_dg_matchup_all_pairings", lambda tour="pga", odds_format="american": {})

    composite = [
        {
            "player_key": "player_a",
            "player_display": "Player A",
            "composite": 82.0,
            "form": 78.0,
            "course_fit": 75.0,
            "momentum": 58.0,
        },
        {
            "player_key": "player_b",
            "player_display": "Player B",
            "composite": 48.0,
            "form": 45.0,
            "course_fit": 44.0,
            "momentum": 42.0,
        },
    ]
    matchups = [
        {
            "p1_player_name": "Player A",
            "p2_player_name": "Player B",
            "odds": {
                "bet365": {"p1": 105, "p2": -125},
                "fanduel": {"p1": 112, "p2": -132},
                "draftkings": {"p1": 108, "p2": -128},
            },
        }
    ]

    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01, required_book=None)
    books = {row["book"] for row in result}
    assert "bet365" in books
    assert "fanduel" in books
    assert "draftkings" in books


def test_find_matchup_value_bets_required_book_still_supported(monkeypatch):
    """Legacy required_book mode should continue to work for scoped callers."""
    monkeypatch.setattr("src.datagolf.fetch_dg_matchup_all_pairings", lambda tour="pga", odds_format="american": {})

    composite = [
        {
            "player_key": "player_a",
            "player_display": "Player A",
            "composite": 82.0,
            "form": 78.0,
            "course_fit": 75.0,
            "momentum": 58.0,
        },
        {
            "player_key": "player_b",
            "player_display": "Player B",
            "composite": 48.0,
            "form": 45.0,
            "course_fit": 44.0,
            "momentum": 42.0,
        },
    ]
    matchups = [
        {
            "p1_player_name": "Player A",
            "p2_player_name": "Player B",
            "odds": {
                "bet365": {"p1": 105, "p2": -125},
                "fanduel": {"p1": 112, "p2": -132},
            },
        }
    ]

    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01, required_book="fanduel")
    assert result
    assert {row["book"] for row in result} == {"fanduel"}


def test_find_matchup_value_bets_returns_diagnostics(monkeypatch):
    monkeypatch.setattr("src.datagolf.fetch_dg_matchup_all_pairings", lambda tour="pga", odds_format="american": {})

    composite = [
        {
            "player_key": "player_a",
            "player_display": "Player A",
            "composite": 80.0,
            "form": 76.0,
            "course_fit": 70.0,
            "momentum": 55.0,
        },
        {
            "player_key": "player_b",
            "player_display": "Player B",
            "composite": 40.0,
            "form": 42.0,
            "course_fit": 45.0,
            "momentum": 46.0,
        },
    ]
    matchups = [
        {
            "p1_player_name": "Player A",
            "p2_player_name": "Player B",
            "odds": {"bet365": {"p1": 110, "p2": -130}},
        }
    ]
    bets, diagnostics = find_matchup_value_bets(
        composite,
        matchups,
        ev_threshold=0.01,
        return_diagnostics=True,
    )
    assert bets
    assert diagnostics["input_rows"] == 1
    assert diagnostics["selected_rows"] >= 1
    assert diagnostics["selection_state"] == "edges_available"


def test_find_matchup_value_bets_diagnostics_for_no_edges(monkeypatch):
    monkeypatch.setattr("src.datagolf.fetch_dg_matchup_all_pairings", lambda tour="pga", odds_format="american": {})
    composite = [
        {"player_key": "player_a", "player_display": "Player A", "composite": 51.0, "form": 50.0, "course_fit": 50.0, "momentum": 50.0},
        {"player_key": "player_b", "player_display": "Player B", "composite": 50.0, "form": 50.0, "course_fit": 50.0, "momentum": 50.0},
    ]
    matchups = [{"p1_player_name": "Player A", "p2_player_name": "Player B",
                 "odds": {"bet365": {"p1": -110, "p2": -110}}}]
    bets, diagnostics = find_matchup_value_bets(composite, matchups, ev_threshold=0.40, return_diagnostics=True)
    assert bets == []
    assert diagnostics["selection_state"] == "market_available_no_edges"
    assert diagnostics["reason_codes"]["below_ev_threshold"] >= 1


def test_extract_dg_prob_from_matchup_uses_nested_datagolf_prices():
    matchup = {
        "odds": {
            "bet365": {"p1": -110, "p2": -110},
            "datagolf": {"p1": -125, "p2": 105},
        }
    }

    p1_prob = _extract_dg_prob_from_matchup(matchup, "p1")
    p2_prob = _extract_dg_prob_from_matchup(matchup, "p2")

    assert p1_prob == pytest.approx(0.533, abs=0.01)
    assert p2_prob == pytest.approx(0.467, abs=0.01)


def test_find_matchup_value_bets_falls_back_to_nested_datagolf_prices(monkeypatch):
    monkeypatch.setattr("src.datagolf.fetch_dg_matchup_all_pairings", lambda tour="pga", odds_format="american": {})

    composite = [
        {
            "player_key": "patrick_cantlay",
            "player_display": "Patrick Cantlay",
            "composite": 74.0,
            "form": 75.0,
            "course_fit": 70.0,
            "momentum": 58.0,
        },
        {
            "player_key": "jake_knapp",
            "player_display": "Jake Knapp",
            "composite": 60.0,
            "form": 60.0,
            "course_fit": 55.0,
            "momentum": 40.0,
        },
    ]
    matchups = [
        {
            "p1_player_name": "Cantlay, Patrick",
            "p2_player_name": "Knapp, Jake",
            "odds": {
                "bet365": {"p1": -110, "p2": -110},
                "datagolf": {"p1": -125, "p2": 105},
            },
        }
    ]

    result = find_matchup_value_bets(composite, matchups, ev_threshold=0.01, required_book="bet365")

    assert result
    assert result[0]["pick"] == "Patrick Cantlay"
    assert result[0]["dg_win_prob"] == pytest.approx(0.533, abs=0.01)
    assert result[0]["platt_win_prob"] == pytest.approx(0.668, abs=0.01)
    assert result[0]["model_win_prob"] == pytest.approx(0.566, abs=0.02)
