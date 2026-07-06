"""Tests for grading reconciliation (defect G-2 / value-bet audit follow-up)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db
from src.grading_reconciliation import reconcile_grading, render_markdown


def _seed_pick(conn, tid, player_key, ev, *, source="cockpit"):
    cur = conn.execute(
        """INSERT INTO picks (tournament_id, model_variant, source, bet_type, player_key,
                              player_display, opponent_key, ev, market_odds, market_book)
           VALUES (?, 'baseline', ?, 'matchup', ?, ?, 'opp', ?, '-110', 'bet365')""",
        (tid, source, player_key, player_key, ev),
    )
    return cur.lastrowid


def test_reconcile_flags_ungraded_positive_ev_after_results(tmp_db):
    conn = db.get_conn()
    tid = db.get_or_create_tournament("Reconcile Event", year=2026)
    # One graded +EV pick, one ungraded +EV pick, one non-positive-EV (never expected graded).
    graded_id = _seed_pick(conn, tid, "graded_player", 0.10)
    _seed_pick(conn, tid, "ungraded_player", 0.08)
    _seed_pick(conn, tid, "negative_ev_player", -0.02)
    # Results exist for the event (it has completed).
    conn.execute(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_position, made_cut) VALUES (?, 'graded_player', 'g', 1, 1)",
        (tid,),
    )
    # Grade only one of the +EV picks.
    conn.execute(
        "INSERT INTO pick_outcomes (pick_id, hit, model_hit, profit) VALUES (?, 1, 1, 0.9)",
        (graded_id,),
    )
    conn.commit()
    conn.close()

    report = reconcile_grading(source="cockpit")
    assert report["status"] == "discrepancies"
    assert report["events_with_ungraded_positive_ev"] == 1
    event = next(e for e in report["events"] if e["tournament_id"] == tid)
    assert event["positive_ev_picks"] == 2  # negative-EV pick excluded
    assert event["graded_positive_ev_picks"] == 1
    assert event["ungraded_positive_ev_picks"] == 1
    assert event["has_discrepancy"] is True
    # Markdown renders without error and reflects the status.
    assert "Status" in render_markdown(report)


def test_reconcile_ok_when_all_positive_ev_graded(tmp_db):
    conn = db.get_conn()
    tid = db.get_or_create_tournament("Clean Event", year=2026)
    pid = _seed_pick(conn, tid, "p1", 0.12)
    conn.execute(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_position, made_cut) VALUES (?, 'p1', 'p', 1, 1)",
        (tid,),
    )
    conn.execute(
        "INSERT INTO pick_outcomes (pick_id, hit, model_hit, profit) VALUES (?, 1, 1, 1.0)",
        (pid,),
    )
    conn.commit()
    conn.close()

    report = reconcile_grading(source="cockpit")
    assert report["status"] == "ok"
    assert report["orphan_outcomes"] == 0


def test_reconcile_counts_void_outcomes_as_graded(tmp_db):
    conn = db.get_conn()
    tid = db.get_or_create_tournament("Void Graded Event", year=2026)
    pick_id = _seed_pick(conn, tid, "void_player", 0.09)
    conn.execute(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_position, made_cut) VALUES (?, 'other', 'o', 1, 1)",
        (tid,),
    )
    conn.execute(
        """INSERT INTO pick_outcomes (pick_id, hit, model_hit, profit, grading_authority, notes)
           VALUES (?, 0, 0, 0, 'void', 'unresolved: player_not_in_results')""",
        (pick_id,),
    )
    conn.commit()
    conn.close()

    report = reconcile_grading(tournament_id=tid, source="cockpit")
    assert report["status"] == "ok"
    event = report["events"][0]
    assert event["positive_ev_picks"] == 1
    assert event["graded_positive_ev_picks"] == 1
    assert event["void_positive_ev_picks"] == 1
    assert event["ungraded_positive_ev_picks"] == 0


def test_reconcile_ignores_events_without_results(tmp_db):
    conn = db.get_conn()
    tid = db.get_or_create_tournament("Upcoming Event", year=2026)
    _seed_pick(conn, tid, "p1", 0.10)  # +EV pick but no results yet
    conn.commit()
    conn.close()

    report = reconcile_grading(source="cockpit")
    # No results => not counted as a discrepancy (legitimately ungraded).
    assert report["status"] == "ok"
