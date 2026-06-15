"""Locked authoritative outcomes must survive re-scoring."""

from __future__ import annotations

from src import db
from src.learning import score_picks_for_tournament
from src.pick_ledger import compute_pick_key, insert_authoritative_pick_outcome


def test_locked_outcome_not_rescored(tmp_db, sample_tournament):
    _, tid = sample_tournament
    conn = db.get_conn()
    conn.execute("UPDATE tournaments SET event_id = '14' WHERE id = ?", (tid,))
    conn.execute(
        """
        INSERT INTO results (tournament_id, player_key, player_display, finish_position, finish_text, made_cut)
        VALUES (?, 'shane_lowry', 'Shane Lowry', 1, '1', 1),
               (?, 'sam_burns', 'Sam Burns', 20, 'T20', 1)
        """,
        (tid, tid),
    )
    conn.commit()
    conn.close()

    pick_key = compute_pick_key(
        event_id="14",
        lane="cockpit",
        section="upcoming",
        phase="pre_tournament",
        bet_type="matchup",
        player_key="shane_lowry",
        opponent_key="sam_burns",
        book="",
        odds="+103",
        snapshot_id="trackRecord_json",
    )
    pick_row = {
        "tournament_id": tid,
        "model_variant": "baseline",
        "source": "cockpit",
        "bet_type": "matchup",
        "player_key": "shane_lowry",
        "player_display": "Shane Lowry",
        "opponent_key": "sam_burns",
        "opponent_display": "Sam Burns",
        "market_odds": "+103",
        "market_book": "",
        "ev": 0.05,
        "reasoning": "locked",
    }
    ledger_row = {
        "pick_key": pick_key,
        "event_id": "14",
        "tournament_id": tid,
        "year": 2026,
        "phase": "pre_tournament",
        "section": "upcoming",
        "lane": "cockpit",
        "lifecycle": "recovered",
        "bet_type": "matchup",
        "market_family": "matchup",
        "market_type": "matchup",
        "player_key": "shane_lowry",
        "player_display": "Shane Lowry",
        "opponent_key": "sam_burns",
        "opponent_display": "Sam Burns",
        "book": "",
        "odds": "+103",
        "ev": 0.05,
        "is_value": 1,
        "model_variant": "baseline",
        "snapshot_id": "trackRecord_json",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_origin": "restore",
        "payload_json": "{}",
    }
    insert_authoritative_pick_outcome(
        tournament_id=tid,
        pick_row=pick_row,
        ledger_row=ledger_row,
        result="win",
        profit=1.03,
        grading_authority="trackRecord_json",
    )

    score_picks_for_tournament(tid)
    conn = db.get_conn()
    row = conn.execute(
        "SELECT profit, outcome_locked FROM pick_outcomes po "
        "JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert float(row["profit"]) == 1.03
    assert int(row["outcome_locked"]) == 1
