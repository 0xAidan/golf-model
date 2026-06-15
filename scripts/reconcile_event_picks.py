#!/usr/bin/env python3
"""Reconcile Past replay inventory vs graded official record per event."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import db
from src.grading_record import build_record_summary, dedupe_record_picks, format_graded_pick_rows, pick_lane_sql
from src.official_pick_record import dedupe_inventory_rows, filter_positive_ev
from src.market_row_backfill import _row_to_pick


def _past_replay_positive_matchups(event_id: str, source: str = "dashboard") -> list[dict]:
    rows = db.get_completed_market_prediction_rows_for_event(event_id, source=source)
    matchups = [row for row in rows if str(row.get("market_family") or "").lower() == "matchup"]
    deduped = dedupe_inventory_rows(matchups, lane=source)
    return filter_positive_ev(deduped)


def _graded_picks(conn, tournament_id: int, lane: str) -> list[dict]:
    lane_sql = pick_lane_sql(lane)
    rows = conn.execute(
        f"""
        SELECT
            p.id, p.model_variant, p.source, p.bet_type, p.market_type,
            p.player_key, p.player_display, p.opponent_key, p.opponent_display,
            p.market_odds, p.market_book, p.model_prob, p.ev,
            po.hit AS hit, po.hit AS bet_hit, po.profit, po.stake, po.odds_decimal
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE p.tournament_id = ? {lane_sql}
        """,
        (tournament_id,),
    ).fetchall()
    return format_graded_pick_rows([dict(row) for row in rows])


def reconcile_event(conn, *, event_id: str, year: int, name: str) -> dict:
    tournament = conn.execute(
        "SELECT id FROM tournaments WHERE event_id = ? AND year = ? LIMIT 1",
        (event_id, year),
    ).fetchone()
    tournament_id = int(tournament["id"]) if tournament else None

    past_rows = _past_replay_positive_matchups(event_id, "dashboard")
    backfill_rows = db.get_completed_market_prediction_rows_for_event(event_id, source="dashboard")
    pick_rows = [
        _row_to_pick(row, tournament_id=tournament_id or 0, source="cockpit", default_model_variant="baseline")
        for row in backfill_rows
        if row.get("player_key") or row.get("player_display")
    ]
    backfill_positive = filter_positive_ev(pick_rows)
    graded = _graded_picks(conn, tournament_id, "cockpit") if tournament_id else []
    deduped_graded = dedupe_record_picks(graded)
    summary = build_record_summary(graded)

    return {
        "event_id": event_id,
        "name": name,
        "tournament_id": tournament_id,
        "past_replay_positive_matchups": len(past_rows),
        "backfill_positive_candidates": len(backfill_positive),
        "graded_rows": len(graded),
        "deduped_graded_count": summary["combined"]["picks"],
        "gap_past_vs_graded": len(past_rows) - summary["combined"]["picks"],
        "ok": len(past_rows) == summary["combined"]["picks"] or tournament_id is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile pick counts per event")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--event-id", action="append", dest="event_ids")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    db.ensure_initialized()
    conn = db.get_conn()
    if args.all:
        rows = conn.execute(
            """
            SELECT DISTINCT event_id, event_name
            FROM rounds
            WHERE year = ? AND event_id IS NOT NULL AND TRIM(event_id) != ''
            ORDER BY event_name
            """,
            (args.year,),
        ).fetchall()
    else:
        event_ids = args.event_ids or ["32"]
        placeholders = ",".join("?" for _ in event_ids)
        rows = conn.execute(
            f"""
            SELECT DISTINCT event_id, event_name
            FROM rounds
            WHERE year = ? AND event_id IN ({placeholders})
            """,
            (args.year, *event_ids),
        ).fetchall()

    report = [reconcile_event(conn, event_id=str(row["event_id"]), year=args.year, name=str(row["event_name"])) for row in rows]
    conn.close()
    print(json.dumps(report, indent=2))
    failures = [row for row in report if not row["ok"] and row["tournament_id"]]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
