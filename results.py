#!/usr/bin/env python3
"""
Results Entry: log tournament outcomes and score picks.

Usage:
    # Interactive entry:
    python results.py --tournament "WM Phoenix Open"

    # From a file (CSV with columns: player, finish):
    python results.py --tournament "WM Phoenix Open" --file results.csv
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import db
from src.player_normalizer import normalize_name, display_name


def parse_finish(text: str) -> tuple:
    """
    Parse a finish position like 'T14', '1', 'CUT', 'W/D'.
    Returns (position_int_or_None, text, made_cut_bool)
    """
    text = text.strip().upper()
    if text in ("CUT", "MC"):
        return (None, "CUT", 0)
    if text in ("W/D", "WD", "WTD"):
        return (None, "W/D", 0)
    if text in ("DQ", "DSQ"):
        return (None, "DQ", 0)

    # Handle T14, T3, etc.
    num_text = text.replace("T", "").strip()
    try:
        pos = int(num_text)
        return (pos, text, 1)
    except ValueError:
        return (None, text, 1)


def enter_results_interactive(tournament_id: int):
    """Prompt for results interactively."""
    print("\nEnter results (type 'done' when finished).")
    print("Format: Player Name, Finish (e.g. 'Scottie Scheffler, 1' or 'Tom Kim, CUT')\n")

    results_list = []
    while True:
        line = input("  > ").strip()
        if line.lower() in ("done", "quit", "exit", ""):
            if not line:
                continue
            break

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            print("    Format: Player Name, Finish")
            continue

        name = parts[0]
        finish_text = parts[1]
        pos, text, made_cut = parse_finish(finish_text)

        pkey = normalize_name(name)
        pdisp = display_name(name)

        results_list.append({
            "player_key": pkey,
            "player_display": pdisp,
            "finish_position": pos,
            "finish_text": text,
            "made_cut": made_cut,
        })
        print(f"    ✓ {pdisp}: {text}")

    return results_list


def load_results_from_file(filepath: str) -> list[dict]:
    """Load results from a CSV file."""
    results_list = []
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("player") or row.get("Player") or row.get("name") or ""
            finish = row.get("finish") or row.get("Finish") or row.get("position") or ""
            if not name or not finish:
                continue

            pos, text, made_cut = parse_finish(finish)
            pkey = normalize_name(name)
            pdisp = display_name(name)

            results_list.append({
                "player_key": pkey,
                "player_display": pdisp,
                "finish_position": pos,
                "finish_text": text,
                "made_cut": made_cut,
            })
    return results_list


def score_picks(tournament_id: int):
    """
    Compare logged picks against results to determine hits/misses.
    """
    conn = db.get_conn()

    # Get picks for this tournament
    picks = conn.execute(
        "SELECT * FROM picks WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()

    # Get results for this tournament
    results = conn.execute(
        "SELECT * FROM results WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()

    if not picks:
        print("\n  No picks logged for this tournament.")
        conn.close()
        return
    if not results:
        print("\n  No results entered yet.")
        conn.close()
        return

    # Build results lookup
    result_map = {}
    for r in results:
        result_map[r["player_key"]] = dict(r)

    # Score each pick
    scored = 0
    hits = 0
    for pick in picks:
        pk = pick["player_key"]
        bt = pick["bet_type"]
        r = result_map.get(pk)

        if not r:
            continue

        finish = r.get("finish_position")
        made_cut = r.get("made_cut", 0)
        hit = 0

        if bt == "outright":
            hit = 1 if finish == 1 else 0
        elif bt == "top5":
            hit = 1 if finish is not None and finish <= 5 else 0
        elif bt == "top10":
            hit = 1 if finish is not None and finish <= 10 else 0
        elif bt == "top20":
            hit = 1 if finish is not None and finish <= 20 else 0
        elif bt == "make_cut":
            hit = 1 if made_cut else 0
        elif bt == "matchup":
            # For matchups, check if pick beat opponent
            opp_key = pick["opponent_key"]
            opp_result = result_map.get(opp_key)
            if opp_result and finish is not None:
                opp_finish = opp_result.get("finish_position")
                if opp_finish is None:  # opponent missed cut
                    hit = 1
                elif finish < opp_finish:
                    hit = 1

        # Store outcome
        conn.execute(
            """INSERT INTO pick_outcomes (pick_id, hit, actual_finish)
               VALUES (?, ?, ?)""",
            (pick["id"], hit, r.get("finish_text")),
        )
        scored += 1
        hits += hit

    conn.commit()
    conn.close()

    print(f"\n  Scored {scored} picks: {hits} hits, {scored - hits} misses")
    if scored > 0:
        print(f"  Hit rate: {hits/scored:.1%}")


def main():
    parser = argparse.ArgumentParser(description="Enter tournament results and score picks")
    parser.add_argument("--tournament", "-t", required=True, help="Tournament name")
    parser.add_argument("--file", "-f", default=None, help="CSV file with results (player, finish)")
    parser.add_argument("--score-only", action="store_true", help="Only score picks (don't enter new results)")
    args = parser.parse_args()

    # Get tournament
    conn = db.get_conn()
    row = conn.execute(
        "SELECT id FROM tournaments WHERE name = ?", (args.tournament,)
    ).fetchone()
    conn.close()

    if not row:
        print(f"Tournament '{args.tournament}' not found. Run analyze.py first.")
        sys.exit(1)

    tournament_id = row["id"]
    print(f"\nTournament: {args.tournament} (ID: {tournament_id})")

    if not args.score_only:
        # Enter results
        if args.file:
            results_list = load_results_from_file(args.file)
            print(f"  Loaded {len(results_list)} results from {args.file}")
        else:
            results_list = enter_results_interactive(tournament_id)

        if results_list:
            db.store_results(tournament_id, results_list)
            print(f"\n  Stored {len(results_list)} results.")

    # Score picks
    score_picks(tournament_id)

    print("\nDone. Run 'python dashboard.py' to see cumulative performance.")


if __name__ == "__main__":
    main()
