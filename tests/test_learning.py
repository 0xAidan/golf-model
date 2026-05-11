"""Regression tests for post-tournament learning/scoring."""

import pytest


def test_score_picks_for_tournament_scores_sqlite_row_matchup(tmp_db):
    """Scoring should handle sqlite3.Row picks without dict-only helpers."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament(
        "Truist Championship",
        year=2025,
        event_id="480",
    )
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "cameron_young",
                "player_display": "Cameron Young",
                "finish_position": 1,
                "finish_text": "1",
                "made_cut": 1,
            },
            {
                "player_key": "rory_mcilroy",
                "player_display": "Rory McIlroy",
                "finish_position": 7,
                "finish_text": "T7",
                "made_cut": 1,
            },
        ],
    )
    tmp_db.store_picks(
        [
            {
                "tournament_id": tid,
                "model_variant": "baseline",
                "source": "cockpit",
                "bet_type": "matchup",
                "player_key": "cameron_young",
                "player_display": "Cameron Young",
                "opponent_key": "rory_mcilroy",
                "opponent_display": "Rory McIlroy",
                "composite_score": None,
                "course_fit_score": None,
                "form_score": None,
                "momentum_score": None,
                "model_prob": 0.56,
                "market_odds": "-110",
                "market_book": "fanduel",
                "market_implied_prob": 0.5238,
                "ev": 0.07,
                "confidence": "medium",
                "reasoning": "test",
            }
        ]
    )

    result = score_picks_for_tournament(tid)

    assert result["status"] == "ok"
    assert result["scored"] == 1
    assert result["bet_hits"] == 1
    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.hit, po.model_hit, po.actual_finish, po.profit
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert row["hit"] == 1
    assert row["model_hit"] == 1
    assert row["actual_finish"] == "1 vs T7"
    assert row["profit"] == pytest.approx(0.9090909090909091)
