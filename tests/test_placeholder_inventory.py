"""Reject fixture picks and close leftover +EV rows that cannot be graded."""

from __future__ import annotations

from src import db
from src.cached_health import refresh_ops_grading_cache
from src.event_pick_freeze import ensure_all_completed_pga_events_graded, freeze_completed_event_picks
from src.grading_reconciliation import reconcile_grading
from src.learning import score_picks_for_tournament
from src.official_pick_record import is_rejected_inventory_row


def test_rejects_placeholder_and_odds_less_matchups():
    assert is_rejected_inventory_row(
        {
            "player_key": "player_a",
            "player_display": "Player A",
            "opponent_key": "player_b",
            "opponent_display": "Player B",
            "bet_type": "matchup",
            "ev": 0.1,
            "market_odds": None,
        }
    )
    assert is_rejected_inventory_row(
        {
            "player_key": "current_player",
            "player_display": "Current Player",
            "opponent_display": "Opp Current",
            "bet_type": "matchup",
            "ev": 0.04,
            "market_odds": "-110",
        }
    )
    assert is_rejected_inventory_row(
        {
            "player_key": "scottie_scheffler",
            "player_display": "Scottie Scheffler",
            "opponent_key": "rory_mcilroy",
            "bet_type": "matchup",
            "market_type": "tournament_matchups",
            "ev": 0.08,
            "market_odds": "",
        }
    )
    assert not is_rejected_inventory_row(
        {
            "player_key": "player_a",
            "player_display": "Player A",
            "opponent_key": "player_b",
            "opponent_display": "Player B",
            "bet_type": "matchup",
            "ev": 0.1,
            "market_odds": "-110",
        }
    )


def test_store_picks_rejects_placeholder_inventory(tmp_db):
    tid = db.get_or_create_tournament("Houston Open", year=2026, event_id="20")
    db.store_picks(
        [
            {
                "tournament_id": tid,
                "bet_type": "matchup",
                "market_type": "tournament_matchups",
                "player_key": "player_a",
                "player_display": "Player A",
                "opponent_key": "player_b",
                "opponent_display": "Player B",
                "ev": 0.1,
                "market_odds": None,
                "market_book": "bet365",
                "source": "cockpit",
            },
            {
                "tournament_id": tid,
                "bet_type": "matchup",
                "player_key": "current_player",
                "player_display": "Current Player",
                "opponent_display": "Opp Current",
                "ev": 0.04,
                "market_odds": "-110",
                "source": "cockpit",
            },
            {
                "tournament_id": tid,
                "bet_type": "matchup",
                "player_key": "wyndham_clark",
                "player_display": "Wyndham Clark",
                "opponent_key": "rasmus_hojgaard",
                "opponent_display": "Rasmus Hojgaard",
                "ev": 0.2,
                "market_odds": "-110",
                "market_book": "bet365",
                "source": "cockpit",
            },
        ]
    )
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT player_key FROM picks WHERE tournament_id = ? ORDER BY player_key",
            (tid,),
        ).fetchall()
    finally:
        conn.close()
    assert [row["player_key"] for row in rows] == ["wyndham_clark"]


def test_freeze_grades_existing_picks_without_ledger(tmp_db, monkeypatch):
    event_id = "20"
    year = 2026
    tid = db.get_or_create_tournament("Texas Children's Houston Open", year=year, event_id=event_id)
    db.store_picks(
        [
            {
                "tournament_id": tid,
                "bet_type": "matchup",
                "player_key": "wyndham_clark",
                "player_display": "Wyndham Clark",
                "opponent_key": "rasmus_hojgaard",
                "opponent_display": "Rasmus Hojgaard",
                "ev": 0.2,
                "market_odds": "-110",
                "source": "cockpit",
            }
        ]
    )
    db.store_results(
        tid,
        [
            {
                "player_key": "wyndham_clark",
                "player_display": "Wyndham Clark",
                "finish_position": 40,
                "finish_text": "CUT",
                "made_cut": 0,
            },
            {
                "player_key": "rasmus_hojgaard",
                "player_display": "Rasmus Hojgaard",
                "finish_position": 28,
                "finish_text": "T28",
                "made_cut": 1,
            },
        ],
    )

    monkeypatch.setattr("src.event_pick_freeze._inventory_exists", lambda _event_id: (0, 0))
    called = {}

    def _fake_grade(*_args, **kwargs):
        called["kwargs"] = kwargs
        return {"status": "complete"}

    monkeypatch.setattr("scripts.grade_tournament.grade_tournament", _fake_grade)

    report = freeze_completed_event_picks(event_id, year=year, event_name="Texas Children's Houston Open")

    assert report["status"] == "complete"
    assert called["kwargs"]["unscored_only"] is True


def test_score_voids_leftover_placeholder_and_clears_gap(tmp_db):
    event_id = "20"
    year = 2026
    tid = db.get_or_create_tournament("Texas Children's Houston Open", year=year, event_id=event_id)
    conn = db.get_conn()
    conn.execute(
        """INSERT INTO picks (tournament_id, model_variant, source, bet_type, market_type,
                              player_key, player_display, opponent_key, opponent_display, ev, market_book)
           VALUES (?, 'v5', 'cockpit', 'matchup', 'tournament_matchups',
                   'player_a', 'Player A', 'player_b', 'Player B', 0.1, 'bet365')""",
        (tid,),
    )
    conn.execute(
        """INSERT INTO picks (tournament_id, model_variant, source, bet_type, market_type,
                              player_key, player_display, opponent_key, opponent_display, ev, market_odds, market_book)
           VALUES (?, 'baseline', 'cockpit', 'matchup', 'tournament_matchups',
                   'wyndham_clark', 'Wyndham Clark', 'rasmus_hojgaard', 'Rasmus Hojgaard',
                   0.2, '-110', 'bet365')""",
        (tid,),
    )
    conn.commit()
    conn.close()
    db.store_results(
        tid,
        [
            {
                "player_key": "wyndham_clark",
                "player_display": "Wyndham Clark",
                "finish_position": 40,
                "finish_text": "CUT",
                "made_cut": 0,
            },
            {
                "player_key": "rasmus_hojgaard",
                "player_display": "Rasmus Hojgaard",
                "finish_position": 28,
                "finish_text": "T28",
                "made_cut": 1,
            },
        ],
    )

    before = reconcile_grading(tournament_id=tid)
    assert before["events_with_ungraded_positive_ev"] == 1

    scored = score_picks_for_tournament(tid)
    assert scored["status"] == "ok"
    assert scored["voided"] >= 1

    after = reconcile_grading(tournament_id=tid)
    assert after["events_with_ungraded_positive_ev"] == 0
    assert after["status"] == "ok"


def test_score_voids_when_outcome_is_none(tmp_db, monkeypatch):
    tid = db.get_or_create_tournament("Outcome None Open", year=2026, event_id="77")
    db.store_results(
        tid,
        [
            {
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "finish_position": 1,
                "finish_text": "1",
                "made_cut": 1,
            }
        ],
    )
    db.store_picks(
        [
            {
                "tournament_id": tid,
                "bet_type": "top10",
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "ev": 0.05,
                "market_odds": "+400",
                "source": "cockpit",
            }
        ]
    )
    monkeypatch.setattr("src.learning.determine_outcome", lambda *_args, **_kwargs: None)

    scored = score_picks_for_tournament(tid)
    assert scored["voided"] == 1
    conn = db.get_conn()
    try:
        row = conn.execute(
            """
            SELECT po.grading_authority, po.notes
            FROM pick_outcomes po
            JOIN picks p ON p.id = po.pick_id
            WHERE p.tournament_id = ?
            """,
            (tid,),
        ).fetchone()
    finally:
        conn.close()
    assert row["grading_authority"] == "void"
    assert "outcome_unresolved" in str(row["notes"])


def test_ops_grading_cache_names_leftover_event(tmp_db, monkeypatch):
    tid = db.get_or_create_tournament("Texas Children's Houston Open", year=2026, event_id="20")
    conn = db.get_conn()
    conn.execute(
        """INSERT INTO picks (tournament_id, model_variant, source, bet_type, player_key,
                              player_display, opponent_key, ev)
           VALUES (?, 'baseline', 'cockpit', 'matchup', 'leftover_player', 'Leftover', 'opp', 0.09)""",
        (tid,),
    )
    conn.execute(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_position, made_cut) VALUES (?, 'other', 'o', 1, 1)",
        (tid,),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("src.cached_health.write_cached_ops_grading_health", lambda report: report)
    report = refresh_ops_grading_cache()
    grading = report["grading"]
    assert grading["events_with_ungraded_positive_ev"] == 1
    assert grading["leftover_event_name"] == "Texas Children's Houston Open"
    assert grading["leftover_event_id"] == "20"
    assert grading["leftover_event_year"] == 2026
    assert grading["leftover_tournament_id"] == tid


def test_sweep_treats_no_inventory_with_ungraded_as_failure(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "src.event_pick_freeze._completed_events_for_sweep",
        lambda conn, year: [{"event_id": "20", "year": year, "event_name": "Houston Open"}],
    )
    monkeypatch.setattr(
        "src.event_pick_freeze.freeze_completed_event_picks",
        lambda *_args, **_kwargs: {
            "status": "skipped",
            "reason": "no_inventory",
            "ungraded_positive_ev": 1,
        },
    )
    report = ensure_all_completed_pga_events_graded(year=2026)
    assert report["ok"] is False
    assert report["events_processed"] == 1
