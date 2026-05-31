#!/usr/bin/env python3
"""Compare stored picks / prediction_log for a tournament (read-only regression aid)."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff stored picks vs prediction_log for a tournament.")
    parser.add_argument("--tournament-id", type=int, required=True)
    parser.add_argument("--db-path", default="", help="Optional DB path override")
    parser.add_argument("--output", default="", help="Write markdown report path")
    args = parser.parse_args()

    if args.db_path:
        os.environ["GOLF_MODEL_DB_PATH"] = args.db_path

    from src import db

    if args.db_path:
        db.DB_PATH = args.db_path
    db.ensure_initialized()

    conn = db.get_conn()
    t = conn.execute(
        "SELECT id, name, year, date FROM tournaments WHERE id = ?",
        (args.tournament_id,),
    ).fetchone()
    if not t:
        print(f"Tournament id={args.tournament_id} not found", file=sys.stderr)
        return 2

    picks = conn.execute(
        """
        SELECT bet_type, player_key, opponent_key, model_prob, ev, market_odds, source
        FROM picks WHERE tournament_id = ?
        ORDER BY bet_type, player_key
        """,
        (args.tournament_id,),
    ).fetchall()
    preds = conn.execute(
        """
        SELECT bet_type, player_key, model_prob, market_implied_prob, odds_timing
        FROM prediction_log WHERE tournament_id = ?
        ORDER BY bet_type, player_key
        """,
        (args.tournament_id,),
    ).fetchall()
    conn.close()

    lines = [
        f"# Replay report: {t['name']} ({t['year']})",
        "",
        f"Tournament id: {args.tournament_id}",
        "",
        f"## Picks ({len(picks)})",
        "",
    ]
    for row in picks:
        lines.append(
            f"- {row['bet_type']} {row['player_key']} vs {row['opponent_key'] or '-'} "
            f"model_prob={row['model_prob']} ev={row['ev']} source={row['source']}"
        )
    lines.extend(["", f"## prediction_log ({len(preds)})", ""])
    for row in preds:
        lines.append(
            f"- {row['bet_type']} {row['player_key']} model_prob={row['model_prob']} "
            f"timing={row['odds_timing']}"
        )

    mismatches = []
    if len(picks) == 0:
        mismatches.append("No picks rows — grading track record incomplete.")
    if len(preds) == 0 and len(picks) > 0:
        mismatches.append("Picks exist but prediction_log empty (run quality gate or logging skip).")

    if mismatches:
        lines.extend(["", "## Issues", ""])
        for m in mismatches:
            lines.append(f"- {m}")

    report = "\n".join(lines) + "\n"
    print(report)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
