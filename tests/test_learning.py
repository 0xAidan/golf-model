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


def test_score_picks_falls_back_to_rounds_when_results_missing(tmp_db):
    """Scoring should derive final results from rounds when results table is empty."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament(
        "Charles Schwab Challenge",
        year=2026,
        event_id="502",
    )
    tmp_db.store_picks(
        [
            {
                "tournament_id": tid,
                "model_variant": "baseline",
                "source": "cockpit",
                "bet_type": "top10",
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "opponent_key": None,
                "opponent_display": None,
                "composite_score": None,
                "course_fit_score": None,
                "form_score": None,
                "momentum_score": None,
                "model_prob": 0.31,
                "market_odds": "+110",
                "market_book": "bet365",
                "market_implied_prob": 0.4762,
                "ev": 0.11,
                "confidence": "medium",
                "reasoning": "test rounds fallback",
            }
        ]
    )

    conn = tmp_db.get_conn()
    conn.execute(
        """
        INSERT INTO rounds (
            dg_id, player_name, player_key, tour, season, year, event_id, event_name,
            event_completed, round_num, fin_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            999001,
            "Scottie Scheffler",
            "scottie_scheffler",
            "pga",
            2026,
            2026,
            "502",
            "Charles Schwab Challenge",
            "2026-05-31",
            4,
            "T7",
        ),
    )
    conn.commit()
    conn.close()

    result = score_picks_for_tournament(tid)
    assert result["status"] == "ok"
    assert result["result_source"] == "rounds"
    assert result["scored"] == 1
    assert result["bet_hits"] == 1

    conn = tmp_db.get_conn()
    stored = conn.execute(
        "SELECT COUNT(*) AS c FROM results WHERE tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert stored["c"] == 1


def test_score_picks_resolves_via_normalized_display_name(tmp_db):
    """Scoring should recover when the stored key is wrong but the display name is right."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Resolver Open", year=2026, event_id="701")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "jj_spaun",
                "player_display": "J.J. Spaun",
                "finish_position": 12,
                "finish_text": "T12",
                "made_cut": 1,
            }
        ],
    )
    tmp_db.store_picks(
        [
            {
                "tournament_id": tid,
                "model_variant": "baseline",
                "source": "cockpit",
                "bet_type": "top20",
                "player_key": "jj_spaun_wrong",
                "player_display": "J.J. Spaun",
                "opponent_key": None,
                "opponent_display": None,
                "composite_score": None,
                "course_fit_score": None,
                "form_score": None,
                "momentum_score": None,
                "model_prob": 0.25,
                "market_odds": "+160",
                "market_book": "bet365",
                "market_implied_prob": 0.3846,
                "ev": 0.08,
                "confidence": "medium",
                "reasoning": "display-name resolver test",
            }
        ]
    )

    result = score_picks_for_tournament(tid)

    assert result["status"] == "ok"
    assert result["scored"] == 1
    assert result["bet_hits"] == 1
    assert result["resolution_methods"]["normalize_name"] == 1


def test_score_picks_resolves_via_dg_id_alias(tmp_db):
    """Scoring should bridge old and new player keys through a shared dg_id."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Alias Classic", year=2026, event_id="702")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "rasmus_neergaardpetersen",
                "player_display": "Rasmus Neergaard-Petersen",
                "finish_position": 18,
                "finish_text": "T18",
                "made_cut": 1,
            }
        ],
    )
    tmp_db.store_picks(
        [
            {
                "tournament_id": tid,
                "model_variant": "baseline",
                "source": "cockpit",
                "bet_type": "top20",
                "player_key": "rasmus_neergaard_petersen",
                "player_display": "Rasmus Neergaard Petersen",
                "opponent_key": None,
                "opponent_display": None,
                "composite_score": None,
                "course_fit_score": None,
                "form_score": None,
                "momentum_score": None,
                "model_prob": 0.18,
                "market_odds": "+210",
                "market_book": "bet365",
                "market_implied_prob": 0.3226,
                "ev": 0.07,
                "confidence": "medium",
                "reasoning": "dg-id resolver test",
            }
        ]
    )

    conn = tmp_db.get_conn()
    conn.execute(
        """
        INSERT INTO rounds (
            dg_id, player_name, player_key, tour, season, year, event_id, event_name,
            event_completed, round_num, fin_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            424242,
            "Neergaard-Petersen, Rasmus",
            "rasmus_neergaardpetersen",
            "pga",
            2026,
            2026,
            "702",
            "Alias Classic",
            "2026-06-01",
            4,
            "T18",
        ),
    )
    conn.execute(
        """
        INSERT INTO rounds (
            dg_id, player_name, player_key, tour, season, year, event_id, event_name,
            event_completed, round_num, fin_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            424242,
            "Rasmus Neergaard Petersen",
            "rasmus_neergaard_petersen",
            "pga",
            2025,
            2025,
            "555",
            "Earlier Event",
            "2025-08-01",
            4,
            "T22",
        ),
    )
    conn.commit()
    conn.close()

    result = score_picks_for_tournament(tid)

    assert result["status"] == "ok"
    assert result["scored"] == 1
    assert result["bet_hits"] == 1
    assert result["resolution_methods"]["dg_id"] == 1


def test_store_results_upserts_existing_rows(tmp_db):
    """Final grading should overwrite stale result rows for completed events."""
    tid = tmp_db.get_or_create_tournament(
        "Travelers Championship",
        year=2025,
        event_id="492",
    )
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "tom_kim",
                "player_display": "Tom Kim",
                "finish_position": 35,
                "finish_text": "T35",
                "made_cut": 1,
            }
        ],
    )
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "tom_kim",
                "player_display": "Tom Kim",
                "finish_position": 8,
                "finish_text": "T8",
                "made_cut": 1,
            }
        ],
    )

    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT finish_position, finish_text FROM results WHERE tournament_id = ? AND player_key = ?",
        (tid, "tom_kim"),
    ).fetchone()
    conn.close()

    assert row["finish_position"] == 8
    assert row["finish_text"] == "T8"


def test_score_skips_non_positive_ev_picks(tmp_db):
    """Only +EV picks are scored; zero/negative/missing EV are skipped."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("EV Filter Open", year=2026, event_id="601")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "winner",
                "player_display": "Winner",
                "finish_position": 1,
                "finish_text": "1",
                "made_cut": 1,
            },
            {
                "player_key": "also_ran",
                "player_display": "Also Ran",
                "finish_position": 20,
                "finish_text": "T20",
                "made_cut": 1,
            },
        ],
    )
    tmp_db.store_picks(
        [
            _pick_row(tid, "winner", "also_ran", ev=0.05),
            _pick_row(tid, "also_ran", "winner", ev=0.0),
            _pick_row(tid, "player_neg", "also_ran", ev=-0.02),
            _pick_row(tid, "player_none", "also_ran", ev=None),
        ]
    )

    result = score_picks_for_tournament(tid)

    assert result["status"] == "ok"
    assert result["skipped_non_positive_ev"] == 3
    assert result["scored"] == 1

    conn = tmp_db.get_conn()
    outcome_count = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()
    assert outcome_count["c"] == 1


def _pick_row(
    tournament_id: int,
    player_key: str,
    opponent_key: str,
    *,
    ev: float | None,
) -> dict:
    return {
        "tournament_id": tournament_id,
        "model_variant": "baseline",
        "source": "cockpit",
        "bet_type": "matchup",
        "player_key": player_key,
        "player_display": player_key.replace("_", " ").title(),
        "opponent_key": opponent_key,
        "opponent_display": opponent_key.replace("_", " ").title(),
        "composite_score": None,
        "course_fit_score": None,
        "form_score": None,
        "momentum_score": None,
        "model_prob": 0.55,
        "market_odds": "-110",
        "market_book": "fanduel",
        "market_implied_prob": 0.52,
        "ev": ev,
        "confidence": "medium",
        "reasoning": "test",
    }


def test_update_prediction_outcomes_skips_unresolved_players(tmp_db):
    """Do not stamp missing-result predictions as forced losses."""
    from src.learning import update_prediction_outcomes

    tid = tmp_db.get_or_create_tournament(
        "Valspar Championship",
        year=2025,
        event_id="500",
    )
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "ludvig_aberg",
                "player_display": "Ludvig Aberg",
                "finish_position": 2,
                "finish_text": "2",
                "made_cut": 1,
            }
        ],
    )
    tmp_db.log_predictions(
        [
            {
                "tournament_id": tid,
                "player_key": "ludvig_aberg",
                "bet_type": "top10",
                "model_prob": 0.25,
                "dg_prob": 0.22,
                "market_implied_prob": 0.2,
                "actual_outcome": None,
                "odds_decimal": 3.0,
                "profit": None,
                "odds_timing": "pre_tournament",
            },
            {
                "tournament_id": tid,
                "player_key": "ghost_player",
                "bet_type": "top10",
                "model_prob": 0.1,
                "dg_prob": 0.08,
                "market_implied_prob": 0.07,
                "actual_outcome": None,
                "odds_decimal": 5.0,
                "profit": None,
                "odds_timing": "pre_tournament",
            },
        ]
    )

    updated = update_prediction_outcomes(tid)
    assert updated == 1

    conn = tmp_db.get_conn()
    rows = conn.execute(
        "SELECT player_key, actual_outcome FROM prediction_log WHERE tournament_id = ? ORDER BY player_key",
        (tid,),
    ).fetchall()
    conn.close()
    by_key = {row["player_key"]: row["actual_outcome"] for row in rows}

    assert by_key["ghost_player"] is None
    assert by_key["ludvig_aberg"] == 1
