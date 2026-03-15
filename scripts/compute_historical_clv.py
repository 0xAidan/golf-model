#!/usr/bin/env python3
"""
Compute Historical CLV

Analyzes open vs close lines from historical_matchup_odds and historical_odds
to compute CLV (Closing Line Value) for hypothetical bets our model would have made.

Usage:
    python scripts/compute_historical_clv.py
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import db

logger = logging.getLogger("historical_clv")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _american_to_implied(price) -> float:
    """Convert American odds to implied probability."""
    try:
        price = int(float(price))
    except (ValueError, TypeError):
        return 0.0
    if price > 0:
        return 100.0 / (price + 100.0)
    elif price < 0:
        return abs(price) / (abs(price) + 100.0)
    return 0.5


def compute_matchup_clv():
    """Compute CLV from historical matchup odds (open vs close)."""
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT event_id, year, bet_type,
               p1_name, p2_name,
               p1_open, p1_close, p2_open, p2_close,
               p1_outcome_text, p2_outcome_text
        FROM historical_matchup_odds
        WHERE p1_open IS NOT NULL AND p1_close IS NOT NULL
          AND p2_open IS NOT NULL AND p2_close IS NOT NULL
    """).fetchall()
    conn.close()

    total = 0
    positive_clv = 0
    negative_clv = 0
    clv_values = []

    for row in rows:
        p1_open_impl = _american_to_implied(row[5])
        p1_close_impl = _american_to_implied(row[6])
        p2_open_impl = _american_to_implied(row[7])
        p2_close_impl = _american_to_implied(row[8])

        if p1_open_impl <= 0 or p1_close_impl <= 0:
            continue
        if p2_open_impl <= 0 or p2_close_impl <= 0:
            continue

        for open_impl, close_impl in [(p1_open_impl, p1_close_impl), (p2_open_impl, p2_close_impl)]:
            clv = (open_impl - close_impl) * 100.0
            clv_values.append(clv)
            total += 1
            if clv > 0:
                positive_clv += 1
            else:
                negative_clv += 1

    if not clv_values:
        print("  No matchup CLV data available")
        return

    avg_clv = sum(clv_values) / len(clv_values)
    print(f"  Matchup CLV Analysis:")
    print(f"    Total lines analyzed: {total}")
    print(f"    Average CLV: {avg_clv:+.2f}%")
    print(f"    Positive CLV: {positive_clv} ({positive_clv/total*100:.1f}%)")
    print(f"    Negative CLV: {negative_clv} ({negative_clv/total*100:.1f}%)")


def compute_placement_clv():
    """Compute CLV from historical outright odds (open vs close)."""
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT event_id, year, player_name, market,
               open_line, close_line
        FROM historical_odds
        WHERE open_line IS NOT NULL AND close_line IS NOT NULL
    """).fetchall()
    conn.close()

    total = 0
    clv_values = []
    by_market = {}

    for row in rows:
        market = row[3]
        open_impl = _american_to_implied(row[4])
        close_impl = _american_to_implied(row[5])

        if open_impl <= 0 or close_impl <= 0:
            continue

        clv = (open_impl - close_impl) * 100.0
        clv_values.append(clv)
        total += 1

        if market not in by_market:
            by_market[market] = []
        by_market[market].append(clv)

    if not clv_values:
        print("  No placement CLV data available")
        return

    avg_clv = sum(clv_values) / len(clv_values)
    print(f"  Placement CLV Analysis:")
    print(f"    Total lines analyzed: {total}")
    print(f"    Average CLV: {avg_clv:+.2f}%")

    for market, values in sorted(by_market.items()):
        if values:
            avg = sum(values) / len(values)
            print(f"    {market}: avg CLV {avg:+.2f}% ({len(values)} lines)")


def main():
    db.ensure_initialized()

    print("=" * 50)
    print("  Historical CLV Computation")
    print("=" * 50)
    print()

    compute_matchup_clv()
    print()
    compute_placement_clv()

    print()
    print("=" * 50)


if __name__ == "__main__":
    main()
