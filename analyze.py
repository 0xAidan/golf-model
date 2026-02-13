#!/usr/bin/env python3
"""CLI entry point for the golf betting model pipeline."""

import argparse
import logging
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(message)s")

from src.services.golf_model_service import AnalysisConfig, GolfModelService


def _add_bool_pair(parser: argparse.ArgumentParser, name: str, help_enable: str, help_disable: str):
    parser.add_argument(f"--{name}", dest=name, action="store_true", help=help_enable)
    parser.add_argument(f"--no-{name}", dest=name, action="store_false", help=help_disable)
    parser.set_defaults(**{name: None})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Golf Betting Model — unified CLI")
    parser.add_argument("--tournament", "-t", required=True, help="Tournament name")
    parser.add_argument("--course", "-c", default=None, help="Course name")
    parser.add_argument("--folder", "-f", default=None, help="CSV folder (defaults to profiles.yaml or data/csvs)")
    parser.add_argument("--odds", "-o", dest="odds_path", default=None, help="Manual odds JSON file")
    parser.add_argument("--output", default=None, help="Output directory for betting card")
    parser.add_argument("--profile", default=None, help="Profile name from profiles.yaml")
    parser.add_argument("--tour", default=None, help="Tour for Data Golf (default: pga)")
    parser.add_argument("--course-num", type=int, default=None, help="DG course_num for course-specific stats")
    parser.add_argument("--backfill", type=int, nargs="*", default=None,
                        help="Backfill Data Golf rounds for these years before syncing")

    _add_bool_pair(parser, "sync", "Force Data Golf sync", "Skip Data Golf sync (even if key set)")
    _add_bool_pair(parser, "ai", "Run AI brain", "Skip AI brain even if profile enables it")

    parser.add_argument("--no-odds", dest="no_odds", action="store_true", help="Skip odds fetching")
    parser.add_argument("--with-odds", dest="no_odds", action="store_false", help="Force odds fetching even if profile skips")
    parser.set_defaults(no_odds=None)

    return parser.parse_args()


def format_top_players(composite: List[dict], limit: int = 10) -> str:
    lines = []
    for row in composite[:limit]:
        trend = {
            "hot": "↑↑",
            "warming": "↑",
            "cooling": "↓",
            "cold": "↓↓",
        }.get(row.get("momentum_direction"), "—")
        lines.append(
            f"#{row['rank']:>2} {row['player_display']:<25} "
            f"comp={row['composite']:.1f} course={row['course_fit']:.1f} "
            f"form={row['form']:.1f} mom={row['momentum']:.1f} {trend}"
        )
    return "\n".join(lines)


def main():
    args = parse_args()

    config = AnalysisConfig(
        tournament=args.tournament,
        course=args.course or None,
        folder=args.folder,
        odds_path=args.odds_path,
        no_odds=args.no_odds,
        output_dir=args.output,
        sync=args.sync,
        backfill_years=args.backfill,
        tour=args.tour,
        course_num=args.course_num,
        ai=args.ai,
        profile=args.profile,
    )

    service = GolfModelService()
    result = service.run_analysis(config)

    print("=" * 60)
    print(f"GOLF BETTING MODEL — {args.tournament}")
    if args.course:
        print(f"Course: {args.course}")
    print(f"Run ID: {result.run_id}")
    print("=" * 60)

    if result.sync_summary:
        sync = result.sync_summary
        print("DG Sync: {} metrics (hash={})".format(sync.get("total_metrics", 0), sync.get("payload_hash")))
        if sync.get("errors"):
            print("  Errors: ", "; ".join(sync["errors"]))

    print(f"Players scored: {len(result.composite)}")
    print("\nTOP 10 BY COMPOSITE:")
    print(format_top_players(result.composite))

    value_count = sum(len(v) for v in result.value_bets.values())
    print(f"\nValue bets flagged: {value_count}")
    for bet_type, bets in result.value_bets.items():
        flagged = [b for b in bets if b.get("is_value")]
        if not flagged:
            continue
        print(f"  {bet_type}: {len(flagged)} picks")

    print(f"\nCard saved to: {result.card_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
