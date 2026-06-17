"""Canadian Open reconciliation fixture — round vs 72-hole must not collapse."""

from __future__ import annotations

import sqlite3

from src.grading_record import build_record_summary, dedupe_record_picks, format_graded_pick_rows
from src.official_pick_record import dedupe_inventory_rows, filter_positive_ev


def _seed_canadian_open(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'RBC Canadian Open', 2026, '32')",
    )
    picks = [
        (1, "baseline", "cockpit", "matchup", "round_matchups", "p1", "Player One", "o1", "Opp One", "-110", "fd", 0.55, 0.05),
        (2, "baseline", "cockpit", "matchup", "tournament_matchups", "p1", "Player One", "o1", "Opp One", "-105", "fd", 0.54, 0.04),
        (3, "baseline", "cockpit", "matchup", "round_matchups", "p2", "Player Two", "o2", "Opp Two", "+120", "dk", 0.48, 0.03),
    ]
    for row in picks:
        conn.execute(
            """
            INSERT INTO picks
            (id, tournament_id, model_variant, source, bet_type, market_type,
             player_key, player_display, opponent_key, opponent_display,
             market_odds, market_book, model_prob, ev)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.execute(
            """
            INSERT INTO pick_outcomes (pick_id, hit, profit, odds_decimal, stake, entered_at)
            VALUES (?, 1, 0.9, 1.9, 1.0, '2026-06-10 12:00:00')
            """,
            (row[0],),
        )
    conn.commit()
    return 1


def test_round_and_tournament_matchups_stay_separate_in_graded_record(monkeypatch, tmp_path):
    from src import db as db_module

    db_path = tmp_path / "canadian.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _seed_canadian_open(conn)
    rows = conn.execute(
        """
        SELECT p.id, p.model_variant, p.source, p.bet_type, p.market_type,
               p.player_key, p.player_display, p.opponent_key, p.opponent_display,
               p.market_odds, p.market_book, p.model_prob, p.ev,
               po.hit AS hit, po.hit AS bet_hit, po.profit, po.stake, po.odds_decimal
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE p.tournament_id = 1
        """,
    ).fetchall()
    conn.close()

    graded = format_graded_pick_rows([dict(row) for row in rows])
    deduped = dedupe_record_picks(graded)
    summary = build_record_summary(graded)
    assert summary["combined"]["picks"] == 3
    assert len(deduped) == 3


def test_inventory_dedupe_keeps_both_market_types():
    rows = [
        {
            "market_family": "matchup",
            "market_type": "round_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "book": "fd",
            "odds": "-110",
            "ev": 0.05,
        },
        {
            "market_family": "matchup",
            "market_type": "tournament_matchups",
            "player_key": "a",
            "opponent_key": "b",
            "book": "fd",
            "odds": "-105",
            "ev": 0.04,
        },
    ]
    deduped = dedupe_inventory_rows(rows, lane="dashboard")
    positive = filter_positive_ev(deduped)
    assert len(positive) == 2
