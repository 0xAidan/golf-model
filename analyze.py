#!/usr/bin/env python3
"""
Main entry point: ingest CSVs, run models, output betting card.

Usage:
    python analyze.py --tournament "WM Phoenix Open" --course "TPC Scottsdale"

    # With a specific CSV folder:
    python analyze.py --tournament "WM Phoenix Open" --course "TPC Scottsdale" --folder data/csvs

    # With manual odds file:
    python analyze.py --tournament "WM Phoenix Open" --course "TPC Scottsdale" --odds data/odds.json
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.csv_parser import ingest_folder
from src.db import get_or_create_tournament, get_active_weights, get_all_players
from src.models.composite import compute_composite
from src.odds import fetch_odds_api, load_manual_odds, get_best_odds
from src.value import find_value_bets
from src.card import generate_card
from src.player_normalizer import normalize_name


def main():
    parser = argparse.ArgumentParser(description="Golf Betting Model — Analyze & Generate Card")
    parser.add_argument("--tournament", "-t", required=True, help="Tournament name (e.g. 'WM Phoenix Open')")
    parser.add_argument("--course", "-c", default=None, help="Course name (e.g. 'TPC Scottsdale')")
    parser.add_argument("--folder", "-f", default="data/csvs", help="Folder with Betsperts CSV files")
    parser.add_argument("--odds", "-o", default=None, help="Path to manual odds JSON file")
    parser.add_argument("--no-odds", action="store_true", help="Skip odds fetching")
    parser.add_argument("--output", default="output", help="Output directory for betting card")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  GOLF BETTING MODEL")
    print(f"  Tournament: {args.tournament}")
    print(f"  Course: {args.course or 'Not specified'}")
    print(f"{'='*60}")

    # ── Step 1: Create/get tournament ───────────────────────────
    tournament_id = get_or_create_tournament(args.tournament, args.course)
    print(f"\nTournament ID: {tournament_id}")

    # ── Step 2: Ingest CSVs ─────────────────────────────────────
    csv_folder = os.path.join(os.path.dirname(__file__), args.folder)
    if not os.path.isdir(csv_folder):
        print(f"\nERROR: CSV folder not found: {csv_folder}")
        print(f"Create the folder and drop your Betsperts CSVs in it.")
        sys.exit(1)

    summary = ingest_folder(csv_folder, tournament_id)
    if not summary:
        print("\nNo CSVs found. Exiting.")
        sys.exit(1)

    # ── Step 3: Check what data we have ─────────────────────────
    players = get_all_players(tournament_id)
    print(f"\n  Players in database: {len(players)}")

    # ── Step 4: Run models ──────────────────────────────────────
    print(f"\nRunning models...")
    weights = get_active_weights()
    print(f"  Weights: course={weights.get('course_fit', 0.4):.0%}, "
          f"form={weights.get('form', 0.4):.0%}, "
          f"momentum={weights.get('momentum', 0.2):.0%}")

    composite = compute_composite(tournament_id, weights)
    print(f"  Scored {len(composite)} players")

    if not composite:
        print("\nNo players scored. Check your CSV data.")
        sys.exit(1)

    # Print top 10
    print(f"\n  TOP 10 BY COMPOSITE:")
    for r in composite[:10]:
        trend = {"hot": "↑↑", "warming": "↑", "cooling": "↓", "cold": "↓↓"}.get(
            r.get("momentum_direction", ""), "—"
        )
        print(f"    #{r['rank']:>2} {r['player_display']:<25} "
              f"comp={r['composite']:.1f}  "
              f"course={r['course_fit']:.1f}  "
              f"form={r['form']:.1f}  "
              f"mom={r['momentum']:.1f} {trend}")

    # ── Step 5: Fetch odds ──────────────────────────────────────
    value_bets = {}
    if not args.no_odds:
        print(f"\nFetching odds...")
        all_odds = []

        # Try API
        for market in ["outrights", "top_5", "top_10", "top_20"]:
            api_odds = fetch_odds_api(market)
            if api_odds:
                all_odds.extend(api_odds)
                print(f"  {market}: {len(api_odds)} odds from API")

        # Try manual odds file
        if args.odds:
            manual = load_manual_odds(args.odds)
            if manual:
                all_odds.extend(manual)
                print(f"  Manual: {len(manual)} odds from {args.odds}")

        if all_odds:
            # Group odds by market
            odds_by_market = {}
            for o in all_odds:
                m = o["market"]
                if m not in odds_by_market:
                    odds_by_market[m] = []
                odds_by_market[m].append(o)

            # Find value for each market
            for market, market_odds in odds_by_market.items():
                best = get_best_odds(market_odds)
                vb = find_value_bets(composite, best, bet_type=market.replace("top_", "top"))
                value_bets[market.replace("top_", "top")] = vb
                value_count = sum(1 for v in vb if v.get("is_value"))
                print(f"  {market}: {value_count} value plays found")
        else:
            print("  No odds available (set ODDS_API_KEY or use --odds file)")

    # ── Step 6: Generate card ───────────────────────────────────
    print(f"\nGenerating betting card...")
    filepath = generate_card(
        args.tournament,
        args.course or "Unknown",
        composite,
        value_bets,
        output_dir=args.output,
    )
    print(f"\n  Card saved to: {filepath}")
    print(f"\n{'='*60}")
    print(f"  DONE. Open {filepath} to see your picks.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
