"""Regression test: missing results must void, not silently skip, +EV picks."""

from src import db
from src.event_pick_freeze import ensure_event_grading_readiness
from src.grading_reconciliation import reconcile_grading
from src.learning import score_picks_for_tournament
from src.services.golf_model_service import GolfModelService


def test_missing_results_create_void_outcome_and_clear_reconciliation(tmp_db):
    event_id = "906"
    year = 2026
    tid = db.get_or_create_tournament(
        "Silent Ungraded Prevention Open",
        year=year,
        event_id=event_id,
    )
    service = GolfModelService(model_variant="baseline")

    service._store_displayed_picks(
        tid=tid,
        value_bets={
            "top20": [
                {
                    "player_key": "missing_player",
                    "player_display": "Missing Player",
                    "best_odds": 300,
                    "best_book": "draftkings",
                    "model_prob": 0.31,
                    "market_prob": 0.25,
                    "ev": 0.06,
                    "confidence": "medium",
                }
            ]
        },
        matchup_bets=[],
        matchup_failed_candidates=[],
        composite=[
            {
                "player_key": "missing_player",
                "player_display": "Missing Player",
                "composite": 77.0,
                "course_fit": 0.5,
                "form": 0.4,
                "momentum": 0.2,
            }
        ],
    )

    readiness = ensure_event_grading_readiness(
        event_id,
        year=year,
        event_name="Silent Ungraded Prevention Open",
    )
    assert readiness["status"] == "ready"
    assert readiness["positive_ev_picks"] == 1
    assert readiness["ledger_rows"] == 1

    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "other_player",
                "player_display": "Other Player",
                "finish_position": 10,
                "finish_text": "T10",
                "made_cut": 1,
            }
        ],
    )

    score_result = score_picks_for_tournament(tid)

    assert score_result["status"] == "ok"
    assert score_result["voided"] == 1
    assert score_result["resolution_methods"]["unresolved"] == 1

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.hit, po.model_hit, po.actual_finish, po.profit, po.notes, po.grading_authority
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()

    assert row["hit"] == 0
    assert row["model_hit"] == 0
    assert row["actual_finish"] == "VOID"
    assert row["profit"] == 0
    assert row["grading_authority"] == "void"
    assert "unresolved: player_not_in_results" in row["notes"]

    reconciliation = reconcile_grading(source="cockpit")
    assert reconciliation["status"] == "ok"
    assert reconciliation["events_with_ungraded_positive_ev"] == 0
