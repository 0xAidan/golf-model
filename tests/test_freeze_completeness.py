"""Regression tests for freeze/readiness pick completeness."""

from src import db
from src.event_pick_freeze import ensure_event_grading_readiness
from src.services.golf_model_service import GolfModelService


def test_displayed_picks_keep_both_matchup_market_types_through_readiness(tmp_db):
    event_id = "905"
    year = 2026
    tid = db.get_or_create_tournament(
        "Freeze Completeness Open",
        year=year,
        event_id=event_id,
    )
    service = GolfModelService(model_variant="baseline")

    service._store_displayed_picks(
        tid=tid,
        value_bets={
            "top10": [
                {
                    "player_key": "scottie_scheffler",
                    "player_display": "Scottie Scheffler",
                    "best_odds": 450,
                    "best_book": "bet365",
                    "model_prob": 0.24,
                    "market_prob": 0.19,
                    "ev": 0.08,
                    "confidence": "high",
                }
            ]
        },
        matchup_bets=[
            {
                "pick_key": "cameron_young",
                "opponent_key": "rory_mcilroy",
                "pick": "Cameron Young",
                "opponent": "Rory McIlroy",
                "book": "fanduel",
                "odds": -110,
                "ev": 0.07,
                "model_win_prob": 0.56,
                "implied_prob": 0.52,
                "tier": "GOOD",
                "why": "72-hole edge",
                "market_type": "tournament_matchups",
            },
            {
                "pick_key": "cameron_young",
                "opponent_key": "rory_mcilroy",
                "pick": "Cameron Young",
                "opponent": "Rory McIlroy",
                "book": "fanduel",
                "odds": 100,
                "ev": 0.06,
                "model_win_prob": 0.55,
                "implied_prob": 0.50,
                "tier": "GOOD",
                "why": "Round edge",
                "market_type": "round_matchups",
            },
        ],
        matchup_failed_candidates=[],
        composite=[
            {
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "composite": 99.0,
                "course_fit": 1.5,
                "form": 1.2,
                "momentum": 0.9,
            },
            {
                "player_key": "cameron_young",
                "player_display": "Cameron Young",
                "composite": 88.0,
                "course_fit": 1.0,
                "form": 0.7,
                "momentum": 0.4,
            },
        ],
    )

    report = ensure_event_grading_readiness(
        event_id,
        year=year,
        event_name="Freeze Completeness Open",
    )

    assert report["status"] == "ready"
    assert report["positive_ev_picks"] == 3
    assert report["ledger_rows"] == 3
    assert report["ungraded_positive_ev"] == 3

    conn = tmp_db.get_conn()
    picks = conn.execute(
        """
        SELECT bet_type, market_type, player_key, opponent_key, market_odds
        FROM picks
        WHERE tournament_id = ?
        ORDER BY bet_type, market_type, market_odds
        """,
        (tid,),
    ).fetchall()
    ledger_rows = conn.execute(
        """
        SELECT bet_type, market_type, player_key, opponent_key, odds
        FROM pick_ledger
        WHERE event_id = ?
        ORDER BY bet_type, market_type, odds
        """,
        (event_id,),
    ).fetchall()
    conn.close()

    matchup_market_types = [
        row["market_type"] for row in picks if row["bet_type"] == "matchup"
    ]
    assert matchup_market_types == ["round_matchups", "tournament_matchups"]

    ledger_matchup_market_types = [
        row["market_type"] for row in ledger_rows if row["bet_type"] == "matchup"
    ]
    assert ledger_matchup_market_types == ["round_matchups", "tournament_matchups"]
