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
from collections import defaultdict

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
    event_id: str,
    year: int,
    book: str = "bet365",
    tour: str = "pga",
) -> tuple[list[dict], str | None]:
    """Fetch historical matchup odds for a single event.

    Returns a tuple of (rows, error_message). Empty rows with no error means
    the endpoint returned successfully but has no matchup records.
    """
    try:
        raw = _call_api("historical-odds/matchups", {
            "tour": tour,
            "event_id": event_id,
            "year": year,
            "book": book,
            "odds_format": "american",
        }, cache_ttl_seconds=0)
        if not raw:
            return [], None
        if isinstance(raw, list):
            # Current DG payload shape is [rows, metadata].
            if raw and isinstance(raw[0], list):
                return [r for r in raw[0] if isinstance(r, dict)], None
            return [r for r in raw if isinstance(r, dict)], None
        if isinstance(raw, dict):
            rows = raw.get("odds") or raw.get("rows") or []
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)], None
        return [], None
    except Exception as e:
        return [], str(e)


def fetch_with_retries(
    event_id: str,
    year: int,
    *,
    book: str,
    tour: str,
    max_retries: int,
    retry_delay_seconds: float,
) -> tuple[list[dict], str | None, int]:
    """Fetch matchup rows with bounded retries for transient API failures."""
    attempts = 0
    while attempts <= max_retries:
        attempts += 1
        rows, error = fetch_matchup_odds_for_event(event_id, year, book=book, tour=tour)
        if error is None:
            return rows, None, attempts
        if attempts <= max_retries:
            logger.warning(
                "Retrying %s/%d after error (attempt %d/%d): %s",
                event_id,
                year,
                attempts,
                max_retries + 1,
                error,
            )
            time.sleep(retry_delay_seconds)
    return [], error, attempts


def store_matchup_batch(matchups: list[dict], event_id: str, year: int, book: str) -> int:
    """Store a batch of matchup odds into historical_matchup_odds."""
    if not matchups:
        return 0

    conn = db.get_conn()
    inserted = 0
    for m in matchups:
        p1_name = m.get("p1_name") or m.get("p1_player_name")
        p2_name = m.get("p2_name") or m.get("p2_player_name")
        p1_id = m.get("p1_dg_id")
        p2_id = m.get("p2_dg_id")
        if not p1_name or not p2_name or p1_id is None or p2_id is None:
            continue
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO historical_matchup_odds
                   (event_id, year, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
                    book, p1_open, p1_close, p2_open, p2_close,
                    p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text,
                    tie_rule, open_time, close_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, year,
                    m.get("bet_type", ""),
                    p1_id,
                    p1_name,
                    p2_id,
                    p2_name,
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
            if cursor.rowcount and cursor.rowcount > 0:
                inserted += int(cursor.rowcount)
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
    parser.add_argument("--start-year", type=int, default=2019, help="Start year for range filter (default: 2019)")
    parser.add_argument("--end-year", type=int, default=2026, help="End year for range filter (default: 2026)")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries per failed event fetch (default: 2)")
    parser.add_argument("--retry-delay-seconds", type=float, default=2.0, help="Delay between retries (default: 2.0)")
    args = parser.parse_args()

    db.ensure_initialized()

    print("=" * 50)
    print("  Historical Matchup Odds Backfill")
    print("=" * 50)

    print("\n  Fetching event list from DG...")
    events = fetch_event_list(args.tour)
    if not events:
        print("  ERROR: No events returned from DG API")
        sys.exit(1)

    if args.year:
        events = [e for e in events if e.get("calendar_year") == args.year or e.get("year") == args.year]
    else:
        events = [
            e for e in events
            if args.start_year <= int(e.get("calendar_year", e.get("year", 0)) or 0) <= args.end_year
        ]

    print(f"  Found {len(events)} events to process")
    print(f"  Book: {args.book}")
    if args.year:
        print(f"  Year: {args.year}")
    else:
        print(f"  Year range: {args.start_year}-{args.end_year}")
    print(f"  Retries per event: {args.max_retries}")
    print(f"  Estimated time: ~{len(events) * RATE_LIMIT_SECONDS / 60:.1f} minutes")
    print()

    total_inserted = 0
    total_matchups = 0
    failure_counts_by_reason: dict[str, int] = defaultdict(int)
    failed_events: list[dict] = []
    retry_attempt_events = 0

    for i, event in enumerate(events):
        event_id = str(event.get("event_id", event.get("dg_id", "")))
        year = event.get("calendar_year", event.get("year", 0))
        event_name = event.get("event_name", event_id)

        if not event_id or not year:
            continue

        matchups, fetch_error, attempts = fetch_with_retries(
            event_id,
            year,
            book=args.book,
            tour=args.tour,
            max_retries=max(0, int(args.max_retries)),
            retry_delay_seconds=max(0.0, float(args.retry_delay_seconds)),
        )
        if attempts > 1:
            retry_attempt_events += 1

        if fetch_error:
            failure_counts_by_reason[fetch_error] += 1
            failed_events.append(
                {
                    "event_id": event_id,
                    "event_name": event_name,
                    "year": year,
                    "reason": fetch_error,
                    "attempts": attempts,
                }
            )
            print(
                f"  [{i+1}/{len(events)}] {event_name} ({year}): FAILED after {attempts} attempts ({fetch_error})"
            )
        elif matchups:
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
    print("  Backfill complete")
    print(f"  Events processed: {len(events)}")
    print(f"  Total matchups fetched: {total_matchups}")
    print(f"  New rows inserted: {total_inserted}")
    print(f"  Events requiring retries: {retry_attempt_events}")
    print(f"  Failed events: {len(failed_events)}")
    if failed_events:
        print("  Failure reasons:")
        for reason, count in sorted(failure_counts_by_reason.items(), key=lambda x: x[1], reverse=True):
            print(f"    - {count}x {reason}")
        print("  Failed event list:")
        for failed in failed_events:
            print(
                f"    - {failed['event_name']} ({failed['event_id']}/{failed['year']}): "
                f"{failed['reason']} [attempts={failed['attempts']}]"
            )
    print("=" * 50)


if __name__ == "__main__":
    main()
