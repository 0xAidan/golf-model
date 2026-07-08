#!/usr/bin/env python3
"""
Regrade Incorrectly Voided Matchup Picks

A voided bet means the system couldn't determine a winner, so it scores the
bet as 0 profit. That should only happen when a player withdrew or didn't
play. This script finds matchup picks that were voided even though both
named players have a stored `results` row for that tournament (proof they
both competed), re-fetches Data Golf matchup settlement data across the full
book list (the root cause: grading previously only queried 5 mainstream
books, missing pairings that only offshore/secondary books like pinnacle,
betcris, unibet, bovada, or betonline posted lines for), and re-runs grading
so these picks resolve to win/loss/push instead of staying void.

Never touches `outcome_locked = 1` picks or picks that are still
legitimately void (a player genuinely didn't play). Every changed pick is
written to `grading_audit_log` (action='regrade') so re-graded picks stay
distinguishable from picks that were correct on the first pass.

Usage:
    python scripts/regrade_voided_matchups.py --dry-run
    python scripts/regrade_voided_matchups.py
    python scripts/regrade_voided_matchups.py --tournament-id 26
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src import db
from src.grading_void_audit import affected_tournaments, find_incorrectly_voided_matchup_picks
from src.matchup_outcome_store import store_matchup_outcomes
from scripts.grade_tournament import MATCHUP_OUTCOME_BOOKS, fetch_matchup_outcomes

logger = logging.getLogger("regrade_voided_matchups")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

REGRADE_REASON = "void_book_coverage_backfill_2026_07"


def regrade_tournament(tournament_id: int, event_id: str, year: int, *, dry_run: bool) -> dict:
    """Fetch broader matchup settlement coverage and re-grade one tournament."""
    from src.learning import score_picks_for_tournament

    before = find_incorrectly_voided_matchup_picks(tournament_id)

    if dry_run:
        return {
            "tournament_id": tournament_id,
            "event_id": event_id,
            "year": year,
            "dry_run": True,
            "incorrectly_voided_before": len(before),
        }

    fetched = 0
    stored = 0
    books_with_data = []
    for book in MATCHUP_OUTCOME_BOOKS:
        rows = fetch_matchup_outcomes(event_id, year, book=book)
        if not rows:
            continue
        books_with_data.append(book)
        fetched += len(rows)
        stored += store_matchup_outcomes(tournament_id, event_id, year, rows, book=book)

    score_result = score_picks_for_tournament(
        tournament_id,
        force_audit=True,
        audit_reason=REGRADE_REASON,
    )

    after = find_incorrectly_voided_matchup_picks(tournament_id)

    return {
        "tournament_id": tournament_id,
        "event_id": event_id,
        "year": year,
        "dry_run": False,
        "matchup_outcomes_fetched": fetched,
        "matchup_outcomes_stored": stored,
        "books_with_data": books_with_data,
        "incorrectly_voided_before": len(before),
        "incorrectly_voided_after": len(after),
        "recovered": len(before) - len(after),
        "still_void_pick_ids": [p["pick_id"] for p in after],
        "scoring_summary": {
            "scored": score_result.get("scored"),
            "voided": score_result.get("voided"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-grade matchup picks incorrectly voided despite both players competing",
    )
    parser.add_argument("--tournament-id", type=int, help="Only process this tournament")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report affected tournaments/picks without fetching or writing anything",
    )
    args = parser.parse_args()

    db.ensure_initialized()

    targets = affected_tournaments(args.tournament_id)
    if not targets:
        print(
            "No incorrectly voided matchup picks found "
            "(no void pick has both players present in results)."
        )
        return

    print("=" * 60)
    print(f"  Found {len(targets)} tournament(s) with incorrectly voided matchup picks")
    print("=" * 60)
    for t in targets:
        print(f"  - {t['tournament_name']} ({t['year']}): {t['void_pick_count']} voided pick(s)")
    print()

    reports = []
    for t in targets:
        print(f"Processing {t['tournament_name']} ({t['year']})...")
        report = regrade_tournament(
            t["tournament_id"],
            t["event_id"],
            t["year"],
            dry_run=args.dry_run,
        )
        reports.append(report)
        if args.dry_run:
            print(f"  Would attempt regrade of {report['incorrectly_voided_before']} pick(s) (dry run)")
        else:
            print(
                f"  Fetched {report['matchup_outcomes_fetched']} matchup outcome row(s) "
                f"from {len(report['books_with_data'])} book(s) "
                f"({report['matchup_outcomes_stored']} new), "
                f"recovered {report['recovered']}/{report['incorrectly_voided_before']} "
                "incorrectly voided pick(s)"
            )
            if report["incorrectly_voided_after"] > 0:
                print(
                    f"  WARNING: {report['incorrectly_voided_after']} pick(s) still incorrectly "
                    "voided (no settlement data found for that pairing in any book)"
                )

    os.makedirs("output/audits", exist_ok=True)
    out_path = os.path.join(
        "output", "audits", f"void_regrade_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(out_path, "w") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "reports": reports}, f, indent=2)
    print()
    print(f"Report written to {out_path}")

    if not args.dry_run:
        remaining = find_incorrectly_voided_matchup_picks(args.tournament_id)
        if remaining:
            print(
                f"WARNING: {len(remaining)} pick(s) remain incorrectly voided after regrade."
            )
            sys.exit(1)
        print("Verified: zero picks remain voided where both players have results.")


if __name__ == "__main__":
    main()
