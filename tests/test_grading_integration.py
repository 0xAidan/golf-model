"""Integration tests: +EV pick persistence through grading outcomes."""


def test_positive_ev_picks_persist_and_score_to_outcomes(tmp_db):
    """Store only +EV displayed picks, then grade to pick_outcomes."""
    from src.learning import score_picks_for_tournament
    from src.lab_displayed_picks import persist_lab_logged_picks

    tid = tmp_db.get_or_create_tournament("Grading Integration Open", year=2026, event_id="701")
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

    stored = persist_lab_logged_picks(
        {
            "tournament_id": tid,
            "profile_name": "lab_sandbox",
            "composite_results": [],
            "matchups": [
                {
                    "pick_key": "cameron_young",
                    "opponent_key": "rory_mcilroy",
                    "pick": "Cameron Young",
                    "opponent": "Rory McIlroy",
                    "odds": -110,
                    "book": "fanduel",
                    "ev": 0.07,
                    "model_win_prob": 0.56,
                    "implied_prob": 0.52,
                    "tier": "GOOD",
                    "why": "+EV displayed",
                },
            ],
            "matchup_failed_candidates": [
                {
                    "pick_key": "rory_mcilroy",
                    "opponent_key": "cameron_young",
                    "pick": "Rory McIlroy",
                    "opponent": "Cameron Young",
                    "odds": -110,
                    "book": "fanduel",
                    "ev": 0.04,
                    "model_win_prob": 0.48,
                    "implied_prob": 0.52,
                    "tier": "FAILED",
                    "reason_code": "should_not_persist",
                },
            ],
            "value_bets": {
                "top10": [
                    {
                        "player_key": "rory_mcilroy",
                        "player_display": "Rory McIlroy",
                        "best_odds": 500,
                        "best_book": "draftkings",
                        "model_prob": 0.25,
                        "market_prob": 0.17,
                        "ev": -0.03,
                        "confidence": "low",
                    },
                ],
            },
        },
    )
    assert stored == 1

    conn = tmp_db.get_conn()
    pick_count = conn.execute(
        "SELECT COUNT(*) AS c FROM picks WHERE tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert pick_count["c"] == 1

    score_result = score_picks_for_tournament(tid)
    assert score_result["status"] == "ok"
    assert score_result["scored"] == 1
    assert score_result["bet_hits"] == 1
    assert score_result["model_hits"] == 1
    assert score_result["skipped_non_positive_ev"] == 0

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT p.player_key, po.hit, po.model_hit, po.profit
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()

    assert row["player_key"] == "cameron_young"
    assert row["hit"] == 1
    assert row["model_hit"] == 1
    assert row["profit"] > 0
