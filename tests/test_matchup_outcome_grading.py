"""Tests for DG matchup outcome store and market-type-correct grading."""

from __future__ import annotations

import pytest

from src.matchup_outcome_store import store_matchup_outcomes
from src.scoring import determine_outcome


def _base_pick(**overrides):
    row = {
        "model_variant": "baseline",
        "source": "cockpit",
        "bet_type": "matchup",
        "player_key": "player_a",
        "player_display": "Player A",
        "opponent_key": "player_b",
        "opponent_display": "Player B",
        "composite_score": None,
        "course_fit_score": None,
        "form_score": None,
        "momentum_score": None,
        "model_prob": 0.55,
        "market_odds": "-110",
        "market_book": "bet365",
        "market_implied_prob": 0.52,
        "ev": 0.06,
        "confidence": "medium",
        "reasoning": "test",
    }
    row.update(overrides)
    return row


def test_determine_outcome_3ball_lowest_finish_wins():
    outcome = determine_outcome(
        "3ball",
        finish_position=12,
        finish_text="T12",
        made_cut=1,
        all_results=[],
        group_opponent_finishes=[20, 15],
    )
    assert outcome["hit"] == 1
    assert outcome["fraction"] == 1.0


def test_determine_outcome_3ball_push_when_tied_for_best():
    outcome = determine_outcome(
        "3ball",
        finish_position=10,
        finish_text="T10",
        made_cut=1,
        all_results=[],
        group_opponent_finishes=[10, 18],
    )
    assert outcome["is_push"] is True
    assert outcome["hit"] == 0


def test_round_matchup_uses_stored_outcome_not_72_hole(tmp_db):
    """Round matchups must grade from DG stored outcomes, not tournament finishes."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Round Match Test", year=2026, event_id="901")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 30,
                "finish_text": "T30",
                "made_cut": 1,
            },
            {
                "player_key": "player_b",
                "player_display": "Player B",
                "finish_position": 5,
                "finish_text": "T5",
                "made_cut": 1,
            },
        ],
    )
    store_matchup_outcomes(
        tid,
        "901",
        2026,
        [
            {
                "bet_type": "round_matchups",
                "p1_name": "Player A",
                "p2_name": "Player B",
                "p1_outcome_text": "win",
                "p2_outcome_text": "loss",
            }
        ],
        conn=tmp_db.get_conn(),
    )
    tmp_db.store_picks(
        [
            _base_pick(
                tournament_id=tid,
                market_type="round_matchups",
            )
        ]
    )

    result = score_picks_for_tournament(tid)
    assert result["scored"] == 1
    assert result["bet_hits"] == 1

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.hit, po.grading_authority, po.notes
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert row["hit"] == 1
    assert row["grading_authority"] == "matchup_outcome"
    assert "DG matchup" in (row["notes"] or "")


def test_round_matchup_void_without_stored_outcome(tmp_db):
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Round Void Test", year=2026, event_id="902")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 1,
                "finish_text": "1",
                "made_cut": 1,
            },
            {
                "player_key": "player_b",
                "player_display": "Player B",
                "finish_position": 2,
                "finish_text": "2",
                "made_cut": 1,
            },
        ],
    )
    tmp_db.store_picks(
        [
            _base_pick(
                tournament_id=tid,
                market_type="round_matchups",
            )
        ]
    )

    result = score_picks_for_tournament(tid)
    assert result["voided_count"] == 1
    assert result["scored"] == 0

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.grading_authority, po.notes
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert row["grading_authority"] == "void"
    assert "no_stored_round_matchup_outcome" in (row["notes"] or "")


def test_tournament_matchup_falls_back_to_stored_when_opponent_missing(tmp_db):
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Tournament Fallback", year=2026, event_id="903")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 3,
                "finish_text": "T3",
                "made_cut": 1,
            },
        ],
    )
    store_matchup_outcomes(
        tid,
        "903",
        2026,
        [
            {
                "bet_type": "tournament_matchups",
                "p1_name": "Player A",
                "p2_name": "Player B",
                "p1_outcome_text": "win",
                "p2_outcome_text": "loss",
            }
        ],
        conn=tmp_db.get_conn(),
    )
    tmp_db.store_picks(
        [
            _base_pick(
                tournament_id=tid,
                market_type="tournament_matchups",
            )
        ]
    )

    result = score_picks_for_tournament(tid)
    assert result["scored"] == 1
    assert result["bet_hits"] == 1

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.grading_authority
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert row["grading_authority"] == "matchup_outcome"


def test_3ball_graded_from_field_finishes(tmp_db):
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("3ball Field", year=2026, event_id="904")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 8,
                "finish_text": "T8",
                "made_cut": 1,
            },
            {
                "player_key": "player_c",
                "player_display": "Player C",
                "finish_position": 22,
                "finish_text": "T22",
                "made_cut": 1,
            },
            {
                "player_key": "player_d",
                "player_display": "Player D",
                "finish_position": 15,
                "finish_text": "T15",
                "made_cut": 1,
            },
        ],
    )
    store_matchup_outcomes(
        tid,
        "904",
        2026,
        [
            {
                "bet_type": "3_balls",
                "p1_name": "Player A",
                "p2_name": "Player C",
                "p1_outcome_text": "win",
                "p2_outcome_text": "loss",
            },
            {
                "bet_type": "3_balls",
                "p1_name": "Player A",
                "p2_name": "Player D",
                "p1_outcome_text": "win",
                "p2_outcome_text": "loss",
            },
        ],
        conn=tmp_db.get_conn(),
    )
    tmp_db.store_picks(
        [
            _base_pick(
                tournament_id=tid,
                bet_type="3ball",
                market_type="3_balls",
                opponent_key="",
                opponent_display="",
            )
        ]
    )

    result = score_picks_for_tournament(tid)
    assert result["scored"] == 1
    assert result["bet_hits"] == 1

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.hit, po.grading_authority
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert row["hit"] == 1
    assert row["grading_authority"] in {"matchup_outcome", "computed"}


def test_store_matchup_outcomes_idempotent(tmp_db):
    tid = tmp_db.get_or_create_tournament("Idempotent", year=2026, event_id="905")
    rows = [
        {
            "bet_type": "round_matchups",
            "p1_name": "Player A",
            "p2_name": "Player B",
            "p1_outcome_text": "win",
            "p2_outcome_text": "loss",
        }
    ]
    first = store_matchup_outcomes(tid, "905", 2026, rows, conn=tmp_db.get_conn())
    second = store_matchup_outcomes(
        tid,
        "905",
        2026,
        [
            {
                **rows[0],
                "p1_outcome_text": "loss",
                "p2_outcome_text": "win",
            }
        ],
        conn=tmp_db.get_conn(),
    )
    assert first == 1
    assert second == 1

    conn = tmp_db.get_conn()
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM matchup_outcome_results WHERE tournament_id = ?",
        (tid,),
    ).fetchone()["c"]
    latest = conn.execute(
        """
        SELECT p1_outcome_text FROM matchup_outcome_results
        WHERE tournament_id = ? AND market_type = 'round_matchups'
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert count == 1
    assert latest["p1_outcome_text"] == "loss"


def test_lookup_matchup_outcome_prefers_exact_book(tmp_db):
    from src.matchup_outcome_store import lookup_matchup_outcome, store_matchup_outcomes

    tid = tmp_db.get_or_create_tournament("Book Pref Test", year=2026, event_id="906")
    conn = tmp_db.get_conn()
    row_template = {
        "bet_type": "round_matchups",
        "p1_name": "Player A",
        "p2_name": "Player B",
    }
    store_matchup_outcomes(
        tid,
        "906",
        2026,
        [{**row_template, "p1_outcome_text": "win", "p2_outcome_text": "loss"}],
        book="bet365",
        conn=conn,
    )
    store_matchup_outcomes(
        tid,
        "906",
        2026,
        [{**row_template, "p1_outcome_text": "loss", "p2_outcome_text": "win"}],
        book="draftkings",
        conn=conn,
    )

    exact = lookup_matchup_outcome(
        conn, tid, "player_a", "player_b", "round_matchups", "bet365"
    )
    conn.close()
    assert exact is not None
    assert exact["book"] == "bet365"
    assert exact["p1_outcome_text"] == "win"


def test_lookup_matchup_outcome_falls_back_to_any_book(tmp_db):
    from src.matchup_outcome_store import lookup_matchup_outcome, store_matchup_outcomes

    tid = tmp_db.get_or_create_tournament("Book Fallback Test", year=2026, event_id="907")
    conn = tmp_db.get_conn()
    store_matchup_outcomes(
        tid,
        "907",
        2026,
        [
            {
                "bet_type": "round_matchups",
                "p1_name": "Player A",
                "p2_name": "Player B",
                "p1_outcome_text": "win",
                "p2_outcome_text": "loss",
            }
        ],
        book="bet365",
        conn=conn,
    )

    fallback = lookup_matchup_outcome(
        conn, tid, "player_a", "player_b", "round_matchups", "betcris"
    )
    conn.close()
    assert fallback is not None
    assert fallback["book"] == "bet365"
    assert fallback["p1_outcome_text"] == "win"


def test_round_matchup_grades_via_any_book_fallback(tmp_db):
    """Round matchup on betcris should grade when only bet365 settlement row exists."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Cross Book Grade", year=2026, event_id="908")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 30,
                "finish_text": "T30",
                "made_cut": 1,
            },
            {
                "player_key": "player_b",
                "player_display": "Player B",
                "finish_position": 5,
                "finish_text": "T5",
                "made_cut": 1,
            },
        ],
    )
    store_matchup_outcomes(
        tid,
        "908",
        2026,
        [
            {
                "bet_type": "round_matchups",
                "p1_name": "Player A",
                "p2_name": "Player B",
                "p1_outcome_text": "win",
                "p2_outcome_text": "loss",
            }
        ],
        book="bet365",
        conn=tmp_db.get_conn(),
    )
    tmp_db.store_picks(
        [
            _base_pick(
                tournament_id=tid,
                market_type="round_matchups",
                market_book="betcris",
            )
        ]
    )

    result = score_picks_for_tournament(tid)
    assert result["scored"] == 1
    assert result["bet_hits"] == 1
    assert result["voided_count"] == 0
