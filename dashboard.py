#!/usr/bin/env python3
"""
Dashboard: view cumulative performance, factor analysis, and retune weights.

Usage:
    python dashboard.py                  # Show performance summary
    python dashboard.py --retune         # Suggest and apply new weights
    python dashboard.py --retune --dry   # Suggest but don't apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import db
from src.models.weights import retune, analyze_pick_performance, get_current_weights


def show_summary():
    """Show cumulative pick performance."""
    conn = db.get_conn()

    # Tournaments
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id").fetchall()
    print(f"\n{'='*60}")
    print(f"  GOLF MODEL DASHBOARD")
    print(f"{'='*60}")
    print(f"\n  Tournaments: {len(tournaments)}")
    for t in tournaments:
        result_count = conn.execute(
            "SELECT COUNT(*) as c FROM results WHERE tournament_id = ?", (t["id"],)
        ).fetchone()["c"]
        pick_count = conn.execute(
            "SELECT COUNT(*) as c FROM picks WHERE tournament_id = ?", (t["id"],)
        ).fetchone()["c"]
        print(f"    - {t['name']} ({t['course'] or 'N/A'}): "
              f"{pick_count} picks, {result_count} results")

    # Overall performance
    analysis = analyze_pick_performance()
    print(f"\n  OVERALL PERFORMANCE")
    print(f"  {'─'*40}")
    total = analysis.get("total_picks", 0)
    if total == 0:
        print("  No picks scored yet. Enter results after tournaments.")
        conn.close()
        return

    print(f"  Total picks: {total}")
    print(f"  Hits: {analysis['total_hits']}")
    print(f"  Hit rate: {analysis['hit_rate']:.1%}")

    # By bet type
    print(f"\n  BY BET TYPE:")
    for bt, stats in sorted(analysis.get("by_bet_type", {}).items()):
        print(f"    {bt:<12} {stats['hits']}/{stats['picks']} = {stats['hit_rate']:.1%}")

    # Factor analysis
    fa = analysis.get("factor_analysis", {})
    if fa:
        print(f"\n  FACTOR ANALYSIS (avg score: hits vs misses):")
        print(f"  {'Factor':<15} {'Avg Hit':>10} {'Avg Miss':>10} {'Edge':>10}")
        print(f"  {'─'*47}")
        for factor, stats in sorted(fa.items()):
            edge_str = f"+{stats['edge']:.1f}" if stats['edge'] > 0 else f"{stats['edge']:.1f}"
            print(f"  {factor:<15} {stats['avg_hit']:>10.1f} {stats['avg_miss']:>10.1f} {edge_str:>10}")

    # Current weights
    weights = get_current_weights()
    print(f"\n  CURRENT WEIGHTS:")
    print(f"    Course Fit: {weights.get('course_fit', 0.4):.0%}")
    print(f"    Form:       {weights.get('form', 0.4):.0%}")
    print(f"    Momentum:   {weights.get('momentum', 0.2):.0%}")

    # Weight history
    weight_sets = conn.execute(
        "SELECT * FROM weight_sets ORDER BY id DESC LIMIT 5"
    ).fetchall()
    if weight_sets:
        print(f"\n  WEIGHT HISTORY (last 5):")
        for ws in weight_sets:
            active = " ← ACTIVE" if ws["active"] else ""
            print(f"    {ws['name'] or 'unnamed'} (#{ws['id']}){active}")

    conn.close()


def do_retune(dry_run: bool = True):
    """Run the retune process."""
    print(f"\n{'='*60}")
    print(f"  WEIGHT RETUNING {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}")

    result = retune(dry_run=dry_run)
    analysis = result["analysis"]

    if analysis.get("total_picks", 0) == 0:
        print("\n  No picks with results yet. Nothing to retune.")
        return

    print(f"\n  Based on {analysis['total_picks']} picks ({analysis['total_hits']} hits):")

    print(f"\n  Current → Suggested weights:")
    for k in ["course_fit", "form", "momentum"]:
        curr = result["current_weights"].get(k, 0)
        sugg = result["suggested_weights"].get(k, 0)
        change = result["changes"].get(k, 0)
        arrow = "↑" if change > 0 else "↓" if change < 0 else "="
        print(f"    {k:<12} {curr:.1%} → {sugg:.1%}  ({change:+.1%}) {arrow}")

    if result.get("saved"):
        print(f"\n  ✓ New weights saved and activated.")
    elif not dry_run:
        print(f"\n  {result.get('message', 'Weights not saved.')}")
    else:
        print(f"\n  Dry run — no changes saved. Remove --dry to apply.")


def main():
    parser = argparse.ArgumentParser(description="Golf Model Dashboard")
    parser.add_argument("--retune", action="store_true", help="Run weight retuning")
    parser.add_argument("--dry", action="store_true", help="Dry run (don't save new weights)")
    args = parser.parse_args()

    show_summary()

    if args.retune:
        do_retune(dry_run=args.dry)


if __name__ == "__main__":
    main()
