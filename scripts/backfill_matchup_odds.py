#!/usr/bin/env python3
"""
Backfill Historical Matchup Odds

Fetches historical matchup odds from DG API for all PGA events (2019-2026)
and stores them in the historical_matchup_odds table for backtester replay.

Usage:
    python scripts/backfill_matchup_odds.py
    python scripts/backfill_matchup_odds.py --book bet365
    python scripts/backfill_matchup_odds.py --year 2024  # single year only
"""

import os
import sys
import time
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import db
from src.datagolf import _call_api

logger = logging.getLogger("backfill_matchup_odds")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

RATE_LIMIT_SECONDS = 1.5


def fetch_event_list(tour: str = "pga") -> list[dict]:
    """Fetch all historical events from DG."""
    raw = _call_api("historical-odds/event-list", {"tour": tour})
    if not raw:
        return []
    return raw if isinstance(raw, list) else raw.get("events", [])


def fetch_matchup_odds_for_event(
    event_id: str, year: int, book: str = "bet365", tour: str = "pga"
) -> list[dict]:
    """Fetch historical matchup odds for a single event."""
    try:
        raw = _call_api("historical-odds/matchups", {
            "tour": tour,
            "event_id": event_id,
            "year": year,
            "book": book,
            "odds_format": "american",
        }, cache_ttl_seconds=0)
        if not raw:
            return []
        return raw if isinstance(raw, list) else raw.get("odds", [])
    except Exception as e:
        logger.warning("Failed to fetch matchups for %s/%d: %s", event_id, year, e)
        return []


def store_matchup_batch(matchups: list[dict], event_id: str, year: int, book: str) -> int:
    """Store a batch of matchup odds into historical_matchup_odds."""
    if not matchups:
        return 0

    conn = db.get_conn()
    inserted = 0
    for m in matchups:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO historical_matchup_odds
                   (event_id, year, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
                    book, p1_open, p1_close, p2_open, p2_close,
                    p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text,
                    tie_rule, open_time, close_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, year,
                    m.get("bet_type", ""),
                    m.get("p1_dg_id", 0),
                    m.get("p1_name", ""),
                    m.get("p2_dg_id", 0),
                    m.get("p2_name", ""),
                    book,
                    str(m.get("p1_open", "")) if m.get("p1_open") is not None else None,
                    str(m.get("p1_close", "")) if m.get("p1_close") is not None else None,
                    str(m.get("p2_open", "")) if m.get("p2_open") is not None else None,
                    str(m.get("p2_close", "")) if m.get("p2_close") is not None else None,
                    m.get("p1_outcome"),
                    m.get("p2_outcome"),
                    m.get("p1_outcome_text"),
                    m.get("p2_outcome_text"),
                    m.get("tie_rule"),
                    m.get("open_time"),
                    m.get("close_time"),
                ),
            )
            inserted += 1
        except Exception as e:
            logger.debug("Insert error for matchup in %s/%d: %s", event_id, year, e)

    conn.commit()
    conn.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Backfill historical matchup odds from DG")
    parser.add_argument("--book", default="bet365", help="Sportsbook (default: bet365)")
    parser.add_argument("--tour", default="pga", help="Tour (default: pga)")
    parser.add_argument("--year", type=int, help="Only fetch a specific year")
    args = parser.parse_args()

    db.ensure_initialized()

    print("=" * 50)
    print("  Historical Matchup Odds Backfill")
    print("=" * 50)

    print(f"\n  Fetching event list from DG...")
    events = fetch_event_list(args.tour)
    if not events:
        print("  ERROR: No events returned from DG API")
        sys.exit(1)

    if args.year:
        events = [e for e in events if e.get("calendar_year") == args.year or e.get("year") == args.year]

    print(f"  Found {len(events)} events to process")
    print(f"  Book: {args.book}")
    print(f"  Estimated time: ~{len(events) * RATE_LIMIT_SECONDS / 60:.1f} minutes")
    print()

    total_inserted = 0
    total_matchups = 0
    errors = 0

    for i, event in enumerate(events):
        event_id = str(event.get("event_id", event.get("dg_id", "")))
        year = event.get("calendar_year", event.get("year", 0))
        event_name = event.get("event_name", event_id)

        if not event_id or not year:
            continue

        matchups = fetch_matchup_odds_for_event(event_id, year, args.book, args.tour)
        if matchups:
            inserted = store_matchup_batch(matchups, event_id, year, args.book)
            total_matchups += len(matchups)
            total_inserted += inserted
            print(f"  [{i+1}/{len(events)}] {event_name} ({year}): {len(matchups)} matchups, {inserted} new")
        else:
            print(f"  [{i+1}/{len(events)}] {event_name} ({year}): no matchup data")

        if i < len(events) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    print()
    print("=" * 50)
    print(f"  Backfill complete")
    print(f"  Events processed: {len(events)}")
    print(f"  Total matchups fetched: {total_matchups}")
    print(f"  New rows inserted: {total_inserted}")
    print("=" * 50)


if __name__ == "__main__":
    main()
