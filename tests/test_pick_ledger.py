"""Tests for pick ledger write path and dedup."""

from __future__ import annotations

from src import db
from src.pick_ledger import (
    compute_pick_key,
    insert_authoritative_pick_outcome,
    persist_pick_ledger_from_market_rows,
    persist_pick_ledger_rows,
    result_to_hit,
)


def test_compute_pick_key_stable():
    a = compute_pick_key(
        event_id="14",
        lane="cockpit",
        section="upcoming",
        phase="pre_tournament",
        bet_type="matchup",
        player_key="shane_lowry",
        opponent_key="sam_burns",
        book="bet365",
        odds="+103",
        snapshot_id="snap1",
    )
    b = compute_pick_key(
        event_id="14",
        lane="cockpit",
        section="upcoming",
        phase="pre_tournament",
        bet_type="matchup",
        player_key="shane_lowry",
        opponent_key="sam_burns",
        book="bet365",
        odds="+103",
        snapshot_id="snap1",
    )
    assert a == b
    assert a != compute_pick_key(
        event_id="14",
        lane="cockpit",
        section="upcoming",
        phase="pre_tournament",
        bet_type="matchup",
        player_key="shane_lowry",
        opponent_key="sam_burns",
        book="bet365",
        odds="+175",
        snapshot_id="snap1",
    )


def test_persist_pick_ledger_dedup(tmp_db, sample_tournament):
    _, tid = sample_tournament
    row = {
        "pick_key": compute_pick_key(
            event_id="99",
            lane="cockpit",
            section="upcoming",
            phase="pre_tournament",
            bet_type="matchup",
            player_key="player_a",
            opponent_key="player_b",
            book="draftkings",
            odds="+110",
            snapshot_id="s1",
        ),
        "event_id": "99",
        "event_name": "Test Open",
        "tournament_id": tid,
        "year": 2026,
        "phase": "pre_tournament",
        "section": "upcoming",
        "lane": "cockpit",
        "lifecycle": "generated",
        "bet_type": "matchup",
        "market_family": "matchup",
        "market_type": "matchup",
        "player_key": "player_a",
        "player_display": "Player A",
        "opponent_key": "player_b",
        "opponent_display": "Player B",
        "book": "draftkings",
        "odds": "+110",
        "model_prob": 0.55,
        "implied_prob": 0.48,
        "ev": 0.07,
        "is_value": 1,
        "model_variant": "baseline",
        "model_config_hash": None,
        "snapshot_id": "s1",
        "generated_at": "2026-06-01T12:00:00+00:00",
        "source_origin": "live_refresh",
        "payload_json": "{}",
    }
    n1 = persist_pick_ledger_rows([row])
    n2 = persist_pick_ledger_rows([row])
    assert n1 == 1
    assert n2 == 0


def test_result_to_hit_mapping():
    assert result_to_hit("win") == (1, 1)
    assert result_to_hit("loss") == (0, 0)
    assert result_to_hit("push") == (0, 0)


def test_authoritative_outcome_locked(tmp_db, sample_tournament):
    db_mod, tid = sample_tournament
    conn = db.get_conn()
    conn.execute(
        "UPDATE tournaments SET event_id = '14', year = 2026 WHERE id = ?",
        (tid,),
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
        "ev": 0.01,
        "reasoning": "test",
    }
    ledger_row = {
        "pick_key": pick_key,
        "event_id": "14",
        "event_name": "Test",
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
        "model_prob": None,
        "implied_prob": None,
        "ev": 0.01,
        "is_value": 1,
        "model_variant": "baseline",
        "model_config_hash": None,
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
    conn = db.get_conn()
    row = conn.execute(
        "SELECT outcome_locked, profit, grading_authority FROM pick_outcomes po "
        "JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert int(row["outcome_locked"]) == 1
    assert float(row["profit"]) == 1.03
    assert row["grading_authority"] == "trackRecord_json"


def test_generated_market_rows_store_slim_payload_json(tmp_db, sample_tournament):
    _, tid = sample_tournament
    market_rows = [{
        "snapshot_id": "snap-generated",
        "generated_at": "2026-06-01T12:00:00+00:00",
        "section": "upcoming",
        "event_id": "99",
        "event_name": "Test Open",
        "market_family": "matchup",
        "market_type": "tournament_matchups",
        "player_key": "player_a",
        "player_display": "Player A",
        "opponent_key": "player_b",
        "opponent_display": "Player B",
        "book": "draftkings",
        "odds": "+110",
        "model_prob": 0.55,
        "implied_prob": 0.48,
        "ev": 0.07,
        "is_value": 1,
        "payload_json": '{"full": true, "book": "draftkings"}',
    }]

    inserted = persist_pick_ledger_from_market_rows(
        market_rows,
        lifecycle="generated",
        tournament_id=tid,
        year=2026,
    )

    assert inserted == 1
    conn = db.get_conn()
    row = conn.execute(
        "SELECT lifecycle, payload_json FROM pick_ledger WHERE snapshot_id = ?",
        ("snap-generated",),
    ).fetchone()
    conn.close()
    assert row["lifecycle"] == "generated"
    assert row["payload_json"] == "{}"


def test_canonical_market_rows_keep_full_payload_json(tmp_db, sample_tournament):
    _, tid = sample_tournament
    market_rows = [{
        "snapshot_id": "snap-canonical",
        "generated_at": "2026-06-01T12:00:00+00:00",
        "section": "upcoming",
        "event_id": "99",
        "event_name": "Test Open",
        "market_family": "matchup",
        "market_type": "tournament_matchups",
        "player_key": "player_a",
        "player_display": "Player A",
        "opponent_key": "player_b",
        "opponent_display": "Player B",
        "book": "draftkings",
        "odds": "+110",
        "model_prob": 0.55,
        "implied_prob": 0.48,
        "ev": 0.07,
        "is_value": 1,
        "payload_json": '{"full": true, "book": "draftkings"}',
    }]

    inserted = persist_pick_ledger_from_market_rows(
        market_rows,
        lifecycle="canonical",
        tournament_id=tid,
        year=2026,
    )

    assert inserted == 1
    conn = db.get_conn()
    row = conn.execute(
        "SELECT lifecycle, payload_json FROM pick_ledger WHERE snapshot_id = ?",
        ("snap-canonical",),
    ).fetchone()
    conn.close()
    assert row["lifecycle"] == "canonical"
    assert row["payload_json"] == '{"full": true, "book": "draftkings"}'
