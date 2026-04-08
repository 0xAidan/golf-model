#!/usr/bin/env python3
"""
Restore the live model registry to the default strategy that produced
the verified winning matchup record (~59% win rate, +24.7% ROI).

The previous live registry entry was an auto-optimized candidate from
autoresearch (preserved during a research reset on 2026-03-23) with:
  - form weight 0.20 (should be 0.45)
  - composite weights summing to 0.75 (should be 1.0)
  - placement EV threshold 65% (should be 8%)
  - softmax_temp 0.1 (should be 1.0)

This script sets a clean live model matching src/config.py defaults.

Safe to run multiple times (idempotent: marks old rows not-current, inserts new).

Usage:
    python scripts/restore_default_live_strategy.py
    python scripts/restore_default_live_strategy.py --dry-run
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import db
from backtester.strategy import StrategyConfig
from backtester.model_registry import set_live_weekly_model, get_live_weekly_model_record


def main():
    dry_run = "--dry-run" in sys.argv

    db.init_db()

    current = get_live_weekly_model_record("global")
    if current:
        print("Current live model:")
        print(f"  Name: {current.get('strategy_config_json', '')[:120]}...")
        print(f"  Created: {current.get('created_at')}")
        print(f"  Action: {current.get('action')}")
        print()

    strategy = StrategyConfig(
        name="verified_baseline_v4.2",
        description="Default config.py weights matching verified matchup record (39-22-7, +24.7% ROI)",
        w_sub_course_fit=0.45,
        w_sub_form=0.45,
        w_sub_momentum=0.10,
        min_ev=0.08,
        matchup_ev_threshold=0.05,
        kelly_fraction=0.25,
        softmax_temp=1.0,
        max_implied_prob=0.50,
        min_model_prob=0.005,
        platt_a=-0.05,
        platt_b=0.0,
        ai_adj_cap=3.0,
        use_weather=True,
        markets=["win", "top_5", "top_10", "top_20", "matchup"],
    )

    print("New strategy to set:")
    print(f"  Name:        {strategy.name}")
    print(f"  Weights:     course_fit={strategy.w_sub_course_fit}, form={strategy.w_sub_form}, momentum={strategy.w_sub_momentum}")
    print(f"  EV thresh:   placement={strategy.min_ev}, matchup={strategy.matchup_ev_threshold}")
    print(f"  Kelly:       {strategy.kelly_fraction}")
    print(f"  Softmax:     {strategy.softmax_temp}")
    print(f"  AI cap:      {strategy.ai_adj_cap}")
    print()

    if dry_run:
        print("[DRY RUN] No changes made.")
        return

    result = set_live_weekly_model(
        strategy,
        scope="global",
        promoted_by="manual",
        notes="Restored default config.py weights to match verified matchup record. "
              "Previous entry was auto-optimized candidate with form=0.20, min_ev=0.65, weights summing to 0.75.",
        action="restore_verified_baseline",
    )

    print(f"Done. New live model ID: {result['id']}")
    print()

    verify = get_live_weekly_model_record("global")
    if verify:
        s = verify.get("strategy")
        if s:
            print("Verification:")
            print(f"  course_fit={s.w_sub_course_fit}, form={s.w_sub_form}, momentum={s.w_sub_momentum}")
            print(f"  min_ev={s.min_ev}, matchup_ev={s.matchup_ev_threshold}")
            print(f"  kelly={s.kelly_fraction}, softmax={s.softmax_temp}")
            ok = (
                s.w_sub_course_fit == 0.45
                and s.w_sub_form == 0.45
                and s.w_sub_momentum == 0.10
                and s.min_ev == 0.08
            )
            print(f"  Matches config.py defaults: {'YES' if ok else 'NO — check manually'}")


if __name__ == "__main__":
    main()
