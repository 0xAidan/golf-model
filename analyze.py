#!/usr/bin/env python3
"""
Main entry point: ingest data, run models, output betting card.

Usage:
    # Sync from Data Golf API (no CSVs needed):
    python analyze.py --tournament "AT&T Pebble Beach" --course "Pebble Beach" --sync

    # Backfill historical data first, then sync:
    python analyze.py --tournament "AT&T Pebble Beach" --course "Pebble Beach" --backfill 2024 --sync

    # Traditional CSV mode (still works):
    python analyze.py --tournament "WM Phoenix Open" --course "TPC Scottsdale" --folder data/csvs

    # With manual odds file:
    python analyze.py --tournament "WM Phoenix Open" --course "TPC Scottsdale" --odds data/odds.json

    # Full pipeline with AI brain:
    python analyze.py --tournament "AT&T Pebble Beach" --course "Pebble Beach" --sync --ai
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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
    parser.add_argument("--sync", action="store_true",
                        help="Sync Data Golf predictions + compute rolling stats (default if DATAGOLF_API_KEY set)")
    parser.add_argument("--no-sync", action="store_true", help="Skip Data Golf sync")
    parser.add_argument("--backfill", type=int, nargs="*", default=None,
                        help="Backfill DG round data for given years (e.g. --backfill 2024 2025)")
    parser.add_argument("--tour", default="pga", help="Tour for DG data (default: pga)")
    parser.add_argument("--course-num", type=int, default=None,
                        help="DG course_num for course-specific stats")
    parser.add_argument("--ai", action="store_true",
                        help="Run AI brain pre-tournament analysis and betting decisions")
    parser.add_argument("--service", action="store_true",
                        help="Use the unified GolfModelService pipeline (recommended)")
    args = parser.parse_args()

    # If --service flag, delegate to GolfModelService
    if args.service or (args.sync and not args.folder):
        from src.services.golf_model_service import GolfModelService
        service = GolfModelService(tour=args.tour)
        print(f"Running unified pipeline for {args.tournament}...")
        result = service.run_analysis(
            tournament_name=args.tournament,
            course_name=args.course,
            course_num=args.course_num,
            enable_ai=args.ai,
            enable_backfill=args.backfill is not None,
            backfill_years=args.backfill,
            output_dir=args.output,
        )
        print(f"\nStatus: {result.get('status')}")
        print(f"Field size: {result.get('field_size', 0)}")
        if result.get('card_filepath'):
            print(f"Card: {result['card_filepath']}")
        if result.get('errors'):
            for e in result['errors']:
                print(f"Error: {e}")
        return

    print(f"{'='*60}")
    print(f"  GOLF BETTING MODEL")
    print(f"  Tournament: {args.tournament}")
    print(f"  Course: {args.course or 'Not specified'}")
    print(f"{'='*60}")

    # ── Step 1: Create/get tournament ───────────────────────────
    tournament_id = get_or_create_tournament(args.tournament, args.course)
    print(f"\nTournament ID: {tournament_id}")

    # ── Step 1.5: Backfill DG data if requested ─────────────────
    if args.backfill is not None:
        years = args.backfill if args.backfill else [2024, 2025, 2026]
        print(f"\nBackfilling DG round data for {args.tour.upper()} {years}...")
        from src.datagolf import backfill_rounds
        backfill_rounds(tours=[args.tour], years=years)

    # ── Step 1.6: Sync DG data if requested ─────────────────────
    should_sync = args.sync or (
        not args.no_sync and os.environ.get("DATAGOLF_API_KEY")
    )
    if should_sync:
        print(f"\nSyncing Data Golf data...")
        from src.datagolf import sync_tournament
        from src.rolling_stats import compute_rolling_metrics, get_field_from_metrics
        try:
            sync_result = sync_tournament(tournament_id, tour=args.tour)
            total = sync_result.get("total_metrics", 0)
            print(f"  DG sync: {total} metrics stored")

            # Compute rolling stats
            field = get_field_from_metrics(tournament_id)
            if field:
                print(f"  Computing rolling stats for {len(field)} players...")
                rolling = compute_rolling_metrics(
                    tournament_id, field, course_num=args.course_num
                )
                print(f"  Rolling stats: {rolling.get('total_metrics', 0)} metrics computed")
        except Exception as e:
            print(f"  DG sync error: {e}")
            print(f"  Continuing with CSV data if available...")

    # ── Step 2: Ingest CSVs (optional — fallback or supplement) ──
    csv_folder = os.path.join(os.path.dirname(__file__), args.folder)
    has_csvs = os.path.isdir(csv_folder) and any(
        f.endswith(".csv") for f in os.listdir(csv_folder)
    ) if os.path.isdir(csv_folder) else False

    if has_csvs:
        print(f"\nIngesting CSVs from {args.folder}...")
        summary = ingest_folder(csv_folder, tournament_id)
    elif not should_sync:
        print(f"\nERROR: No data source available.")
        print(f"  Either: set DATAGOLF_API_KEY and use --sync")
        print(f"  Or: drop CSVs in {args.folder}")
        sys.exit(1)
    else:
        print(f"\n  No CSVs found in {args.folder} (using DG data only)")

    # ── Step 3: Check what data we have ─────────────────────────
    players = get_all_players(tournament_id)
    print(f"\n  Players in database: {len(players)}")

    # ── Step 4: Run models ──────────────────────────────────────
    print(f"\nRunning models...")
    weights = get_active_weights()
    print(f"  Weights: course={weights.get('course_fit', 0.4):.0%}, "
          f"form={weights.get('form', 0.4):.0%}, "
          f"momentum={weights.get('momentum', 0.2):.0%}")

    # Check for course profile
    from src.course_profile import load_course_profile, course_to_model_weights
    if args.course:
        profile = load_course_profile(args.course)
        if profile:
            adj = course_to_model_weights(profile)
            ratings = profile.get("skill_ratings", {})
            print(f"  Course profile loaded: {args.course}")
            for k in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
                if k in ratings:
                    print(f"    {k}: {ratings[k]} ({adj.get(f'course_{k}_mult', 1.0)}x weight)")
        else:
            print(f"  No course profile found for '{args.course}'")
            print(f"  (Run: python3 course.py --screenshots data/course_images/ --course \"{args.course}\")")

    composite = compute_composite(tournament_id, weights, course_name=args.course)
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
                bt = "outright" if market == "outrights" else market.replace("top_", "top")
                vb = find_value_bets(composite, best, bet_type=bt,
                                    tournament_id=tournament_id)
                value_bets[bt] = vb
                value_count = sum(1 for v in vb if v.get("is_value"))
                print(f"  {market}: {value_count} value plays found")
        else:
            print("  No odds available (set ODDS_API_KEY or use --odds file)")

    # ── Step 6: AI Brain (optional) ──────────────────────────────
    if args.ai:
        from src.ai_brain import is_ai_available, pre_tournament_analysis, \
            make_betting_decisions, apply_ai_adjustments
        if is_ai_available():
            print(f"\nRunning AI brain...")

            # Load course profile
            course_profile = None
            if args.course:
                profile = load_course_profile(args.course)
                if profile:
                    course_profile = profile

            # Pre-tournament analysis
            print(f"  Pre-tournament analysis...")
            pre_analysis = pre_tournament_analysis(
                tournament_id=tournament_id,
                composite_results=composite,
                course_profile=course_profile,
                tournament_name=args.tournament,
                course_name=args.course or "",
            )
            print(f"    Narrative: {pre_analysis.get('course_narrative', 'N/A')[:100]}...")
            print(f"    Key factors: {', '.join(pre_analysis.get('key_factors', []))}")
            print(f"    Players to watch: {len(pre_analysis.get('players_to_watch', []))}")
            print(f"    Confidence: {pre_analysis.get('confidence', 'N/A')}")

            # Apply AI adjustments to composite
            composite = apply_ai_adjustments(composite, pre_analysis)
            print(f"  Applied AI adjustments to composite scores")

            # Betting decisions (if we have value bets)
            if value_bets:
                print(f"  Making betting decisions...")
                decisions = make_betting_decisions(
                    tournament_id=tournament_id,
                    value_bets_by_type=value_bets,
                    pre_analysis=pre_analysis,
                    composite_results=composite,
                    tournament_name=args.tournament,
                    course_name=args.course or "",
                )
                n_bets = len(decisions.get("decisions", []))
                total_units = decisions.get("total_units", 0)
                print(f"    Recommended bets: {n_bets} ({total_units} units)")
                for d in decisions.get("decisions", [])[:5]:
                    print(f"      {d['player']} {d['bet_type']} @ {d['odds']} "
                          f"({d['confidence']}) — {d['reasoning'][:60]}...")
        else:
            print(f"\n  AI brain not available (set OPENAI_API_KEY)")

    # ── Step 7: Generate card ───────────────────────────────────
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
