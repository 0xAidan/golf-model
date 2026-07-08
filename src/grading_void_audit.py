"""Diagnostics for incorrectly voided matchup picks.

A voided bet means the grading system could not determine a winner, so it
scores the bet as 0 profit. That should only happen when a player withdrew
or otherwise never teed it up. If both named players have a stored
``results`` row for the tournament, they demonstrably competed, so a void
outcome for that pick is a bug, not a legitimate result.

This module finds those cases so they can be re-graded (see
``scripts/regrade_voided_matchups.py``) and re-checked after any grading fix.
"""

from __future__ import annotations

from src import db


def find_incorrectly_voided_matchup_picks(tournament_id: int | None = None) -> list[dict]:
    """Return void matchup-like picks where both players have a results row.

    Only considers +EV picks with an opponent (matchup/3-ball style bets --
    single-player markets like top20 are graded straight from the player's
    own finish and don't hit the round-matchup book-coverage gap this audit
    targets). Never includes ``outcome_locked = 1`` rows since those are
    never eligible for re-grading.
    """
    conn = db.get_conn()
    try:
        params: list = []
        tournament_clause = ""
        if tournament_id is not None:
            tournament_clause = "AND p.tournament_id = ?"
            params.append(tournament_id)
        rows = conn.execute(
            f"""
            SELECT p.id AS pick_id, p.tournament_id, t.name AS tournament_name, t.year,
                   t.event_id, p.player_key, p.player_display, p.opponent_key,
                   p.opponent_display, p.bet_type, p.market_type, p.market_book,
                   po.notes
            FROM picks p
            JOIN pick_outcomes po ON po.pick_id = p.id
            JOIN tournaments t ON t.id = p.tournament_id
            WHERE po.grading_authority = 'void'
              AND COALESCE(po.outcome_locked, 0) = 0
              AND COALESCE(p.ev, 0) > 0
              AND p.opponent_key IS NOT NULL AND p.opponent_key != ''
              {tournament_clause}
            """,
            params,
        ).fetchall()
        if not rows:
            return []

        results_by_tournament: dict[int, set] = {}
        for r in conn.execute("SELECT tournament_id, player_key FROM results").fetchall():
            results_by_tournament.setdefault(r["tournament_id"], set()).add(r["player_key"])

        affected = []
        for row in rows:
            keys = results_by_tournament.get(row["tournament_id"], set())
            if row["player_key"] in keys and row["opponent_key"] in keys:
                affected.append(dict(row))
        return affected
    finally:
        conn.close()


def affected_tournaments(tournament_id: int | None = None) -> list[dict]:
    """Group ``find_incorrectly_voided_matchup_picks`` results by tournament."""
    picks = find_incorrectly_voided_matchup_picks(tournament_id)
    grouped: dict[int, dict] = {}
    for p in picks:
        tid = p["tournament_id"]
        entry = grouped.setdefault(
            tid,
            {
                "tournament_id": tid,
                "tournament_name": p["tournament_name"],
                "year": p["year"],
                "event_id": p["event_id"],
                "void_pick_count": 0,
            },
        )
        entry["void_pick_count"] += 1
    return sorted(grouped.values(), key=lambda x: x["tournament_id"])
