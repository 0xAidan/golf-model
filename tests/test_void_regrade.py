"""Tests for the incorrectly-voided-matchup fix.

Covers:
  - MATCHUP_OUTCOME_BOOKS now covers the full DG book list, not just 5.
  - A round-matchup pick voided because settlement data wasn't fetched from
    the right book gets recovered once that data arrives -- both via a plain
    re-score (no force_audit) and via an explicit force_audit regrade.
  - Legitimately-void picks (a player really didn't play) are left alone.
  - `outcome_locked = 1` picks are never touched.
  - force_audit regrades don't spam grading_audit_log for picks whose
    outcome didn't actually change.
  - The void-audit finder correctly identifies affected tournaments/picks.
"""

from __future__ import annotations

from src.matchup_outcome_store import store_matchup_outcomes


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
        "market_book": "pinnacle",
        "market_implied_prob": 0.52,
        "ev": 0.06,
        "confidence": "medium",
        "reasoning": "test",
    }
    row.update(overrides)
    return row


def test_fetch_matchup_outcomes_handles_no_data_string_response(monkeypatch):
    """Books that never posted a line for the event return `odds` as a plain
    message string, not a list -- this must be treated as "no rows", not
    crash while iterating characters of the string as if they were pick
    dicts (found while running the real backfill against production data)."""
    from scripts.grade_tournament import fetch_matchup_outcomes

    monkeypatch.setattr(
        "scripts.grade_tournament._call_api",
        lambda *args, **kwargs: {
            "book": "circa",
            "event_id": "30",
            "event_name": "John Deere Classic",
            "odds": "we did not track any matchup or 3-ball bets from circa at the John Deere Classic",
            "season": 2026,
            "year": 2026,
        },
    )
    assert fetch_matchup_outcomes("30", 2026, book="circa") == []


def test_fetch_matchup_outcomes_handles_normal_list_response(monkeypatch):
    from scripts.grade_tournament import fetch_matchup_outcomes

    monkeypatch.setattr(
        "scripts.grade_tournament._call_api",
        lambda *args, **kwargs: {
            "book": "pinnacle",
            "odds": [
                {
                    "bet_type": "R3 Match-Up",
                    "p1_player_name": "Lipsky, David",
                    "p2_player_name": "Kohles, Ben",
                    "p1_outcome_text": "loss",
                    "p2_outcome_text": "win",
                }
            ],
        },
    )
    rows = fetch_matchup_outcomes("30", 2026, book="pinnacle")
    assert len(rows) == 1
    assert rows[0]["p2_player_name"] == "Kohles, Ben"


def test_fetch_matchup_outcomes_handles_rows_metadata_list_shape(monkeypatch):
    """Some DG endpoints wrap rows as [rows, metadata] instead of a dict."""
    from scripts.grade_tournament import fetch_matchup_outcomes

    monkeypatch.setattr(
        "scripts.grade_tournament._call_api",
        lambda *args, **kwargs: [
            [{"p1_name": "Player A", "p2_name": "Player B", "p1_outcome_text": "win", "p2_outcome_text": "loss"}],
            {"book": "bet365"},
        ],
    )
    rows = fetch_matchup_outcomes("30", 2026, book="bet365")
    assert len(rows) == 1
    assert rows[0]["p1_name"] == "Player A"


def test_matchup_outcome_books_covers_full_book_list():
    from scripts.grade_tournament import MATCHUP_OUTCOME_BOOKS
    from src.datagolf import BOOK_NAMES

    # Previously hardcoded to only 5 mainstream US books, which caused
    # legitimately-played matchups priced on offshore/secondary books to be
    # voided because grading never fetched settlement data for them.
    for book in ("pinnacle", "betcris", "unibet", "bovada", "betonline"):
        assert book in MATCHUP_OUTCOME_BOOKS
    assert set(MATCHUP_OUTCOME_BOOKS) == set(BOOK_NAMES.keys())


def _setup_round_matchup_tournament(tmp_db, event_id: str):
    tid = tmp_db.get_or_create_tournament(
        "Void Regrade Test", year=2026, event_id=event_id
    )
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
    tmp_db.store_picks(
        [
            _base_pick(
                tournament_id=tid,
                market_type="round_matchups",
                market_book="pinnacle",
            )
        ]
    )
    return tid


def test_void_recovers_on_plain_rescore_once_data_arrives(tmp_db):
    """Void round-matchup picks are not locked -- a normal re-score (no
    force_audit) should pick up newly-arrived settlement data on its own,
    because grade_tournament.py fetches matchup outcomes before every
    scoring pass, including automated/unattended runs."""
    from src.learning import score_picks_for_tournament

    tid = _setup_round_matchup_tournament(tmp_db, "950")

    first = score_picks_for_tournament(tid)
    assert first["voided_count"] == 1
    assert first["scored"] == 0

    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT grading_authority FROM pick_outcomes po JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (tid,),
    ).fetchone()
    assert row["grading_authority"] == "void"
    conn.close()

    # Simulate the missing book's settlement data arriving on a later grading pass.
    store_matchup_outcomes(
        tid,
        "950",
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
        book="pinnacle",
        conn=tmp_db.get_conn(),
    )

    second = score_picks_for_tournament(tid)
    assert second["voided_count"] == 0
    assert second["scored"] == 1
    assert second["bet_hits"] == 1

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT po.hit, po.profit, po.grading_authority, po.notes
        FROM pick_outcomes po JOIN picks p ON p.id = po.pick_id
        WHERE p.tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    audit_rows = conn.execute(
        "SELECT action, reason FROM grading_audit_log WHERE tournament_id = ?",
        (tid,),
    ).fetchall()
    conn.close()

    assert row["hit"] == 1
    assert row["grading_authority"] == "matchup_outcome"
    assert "DG matchup" in (row["notes"] or "")
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == "regrade"
    assert audit_rows[0]["reason"] == "void_recovered"


def test_void_recovers_via_force_audit_regrade(tmp_db):
    """The backfill path (force_audit=True with a specific reason) should
    also recover a void pick once broader book coverage finds the outcome,
    and record that reason in the audit trail."""
    from src.learning import score_picks_for_tournament

    tid = _setup_round_matchup_tournament(tmp_db, "951")
    score_picks_for_tournament(tid)

    store_matchup_outcomes(
        tid,
        "951",
        2026,
        [
            {
                "bet_type": "round_matchups",
                "p1_name": "Player A",
                "p2_name": "Player B",
                "p1_outcome_text": "loss",
                "p2_outcome_text": "win",
            }
        ],
        book="betcris",
        conn=tmp_db.get_conn(),
    )

    result = score_picks_for_tournament(
        tid, force_audit=True, audit_reason="void_book_coverage_backfill_2026_07"
    )
    assert result["voided_count"] == 0

    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT hit, grading_authority FROM pick_outcomes po JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (tid,),
    ).fetchone()
    audit_rows = conn.execute(
        "SELECT action, reason FROM grading_audit_log WHERE tournament_id = ? ORDER BY id",
        (tid,),
    ).fetchall()
    conn.close()

    assert row["hit"] == 0  # Player A lost this one
    assert row["grading_authority"] == "matchup_outcome"
    assert any(
        r["action"] == "regrade" and r["reason"] == "void_book_coverage_backfill_2026_07"
        for r in audit_rows
    )


def test_legitimate_void_untouched_by_force_audit_regrade(tmp_db):
    """A pick where the opponent genuinely never played must stay void, with
    no audit log noise, even when force_audit is used to sweep a whole
    tournament for recoverable picks."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Legit Void Test", year=2026, event_id="952")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 10,
                "finish_text": "T10",
                "made_cut": 1,
            },
            # player_b (the opponent) never played -- no results row, no
            # stored matchup outcome anywhere. This is a real void.
        ],
    )
    tmp_db.store_picks(
        [
            _base_pick(tournament_id=tid, market_type="tournament_matchups")
        ]
    )

    first = score_picks_for_tournament(tid)
    assert first["voided_count"] == 1

    # voided_count reflects picks newly voided *in this call*, not the total
    # currently void -- a no-op re-void (still can't resolve it) reports 0
    # here, which is what makes it possible to tell "nothing changed" apart
    # from "this pick just became void". The DB assertions below are what
    # actually matters: the pick is still void and no audit spam was written.
    second = score_picks_for_tournament(
        tid, force_audit=True, audit_reason="void_book_coverage_backfill_2026_07"
    )
    assert second["voided_count"] == 0

    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT grading_authority FROM pick_outcomes po JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (tid,),
    ).fetchone()
    audit_rows = conn.execute(
        "SELECT id FROM grading_audit_log WHERE tournament_id = ?", (tid,)
    ).fetchall()
    conn.close()

    assert row["grading_authority"] == "void"
    assert len(audit_rows) == 0


def test_force_audit_skips_noop_writes_for_already_correct_picks(tmp_db):
    """force_audit should not spam grading_audit_log for picks that were
    already graded correctly -- otherwise a whole-season backfill run would
    write a no-op audit entry for every previously-correct pick too."""
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Noop Regrade Test", year=2026, event_id="953")
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
                "finish_position": 20,
                "finish_text": "T20",
                "made_cut": 1,
            },
        ],
    )
    tmp_db.store_picks(
        [_base_pick(tournament_id=tid, market_type="tournament_matchups")]
    )

    first = score_picks_for_tournament(tid)
    assert first["scored"] == 1
    assert first["bet_hits"] == 1

    second = score_picks_for_tournament(
        tid, force_audit=True, audit_reason="void_book_coverage_backfill_2026_07"
    )
    assert second["scored"] == 1
    assert second["bet_hits"] == 1

    conn = tmp_db.get_conn()
    audit_rows = conn.execute(
        "SELECT id FROM grading_audit_log WHERE tournament_id = ?", (tid,)
    ).fetchall()
    conn.close()
    assert len(audit_rows) == 0


def test_outcome_locked_pick_never_modified_by_regrade(tmp_db):
    """Locked outcomes (Tier A / authoritative) must never be changed by the
    void-recovery path, even when broader matchup data becomes available."""
    from src.learning import score_picks_for_tournament

    tid = _setup_round_matchup_tournament(tmp_db, "954")
    score_picks_for_tournament(tid)  # first pass -> void

    conn = tmp_db.get_conn()
    conn.execute(
        "UPDATE pick_outcomes SET outcome_locked = 1 WHERE pick_id IN (SELECT id FROM picks WHERE tournament_id = ?)",
        (tid,),
    )
    conn.commit()
    conn.close()

    store_matchup_outcomes(
        tid,
        "954",
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
        book="pinnacle",
        conn=tmp_db.get_conn(),
    )

    # Plain re-score without force_audit must respect the lock.
    result = score_picks_for_tournament(tid)
    assert result["skipped_locked"] == 1

    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT grading_authority, outcome_locked FROM pick_outcomes po JOIN picks p ON p.id = po.pick_id WHERE p.tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert row["grading_authority"] == "void"
    assert row["outcome_locked"] == 1


def test_find_incorrectly_voided_matchup_picks(tmp_db):
    from src.grading_void_audit import affected_tournaments, find_incorrectly_voided_matchup_picks
    from src.learning import score_picks_for_tournament

    tid = _setup_round_matchup_tournament(tmp_db, "955")
    score_picks_for_tournament(tid)  # both players have results, pick voids -> a bug

    found = find_incorrectly_voided_matchup_picks(tid)
    assert len(found) == 1
    assert found[0]["player_key"] == "player_a"
    assert found[0]["opponent_key"] == "player_b"

    grouped = affected_tournaments(tid)
    assert len(grouped) == 1
    assert grouped[0]["tournament_id"] == tid
    assert grouped[0]["void_pick_count"] == 1

    # Once recovered, it should drop out of the finder.
    store_matchup_outcomes(
        tid,
        "955",
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
        book="pinnacle",
        conn=tmp_db.get_conn(),
    )
    score_picks_for_tournament(tid)
    assert find_incorrectly_voided_matchup_picks(tid) == []


def test_find_incorrectly_voided_matchup_picks_ignores_legit_void(tmp_db):
    """A genuinely-withdrawn opponent (no results row at all) must never be
    flagged by the finder, since only one player competed."""
    from src.grading_void_audit import find_incorrectly_voided_matchup_picks
    from src.learning import score_picks_for_tournament

    tid = tmp_db.get_or_create_tournament("Legit Void Finder Test", year=2026, event_id="956")
    tmp_db.store_results(
        tid,
        [
            {
                "player_key": "player_a",
                "player_display": "Player A",
                "finish_position": 10,
                "finish_text": "T10",
                "made_cut": 1,
            },
        ],
    )
    tmp_db.store_picks(
        [_base_pick(tournament_id=tid, market_type="tournament_matchups")]
    )
    score_picks_for_tournament(tid)

    assert find_incorrectly_voided_matchup_picks(tid) == []
