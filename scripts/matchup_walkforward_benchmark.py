#!/usr/bin/env python3
"""Generate frozen matchup walk-forward baseline metrics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester.strategy import StrategyConfig, replay_event
from backtester.weighted_walkforward import load_historical_events
from src import config, db


def _baseline_strategy() -> StrategyConfig:
    return StrategyConfig(
        name="matchup_baseline_e0",
        min_ev=config.DEFAULT_EV_THRESHOLD,
        matchup_ev_threshold=config.MATCHUP_EV_THRESHOLD,
        platt_a=config.MATCHUP_PLATT_A,
        platt_b=config.MATCHUP_PLATT_B,
        markets=["matchup"],
    )


def _event_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit_rate_pct": 0.0, "roi_pct": 0.0, "brier": None}
    wins = sum(1 for r in rows if r.get("won"))
    # Replay uses fixed stake per bet. Normalize to flat 1u for comparability.
    pnl = sum(
        (r.get("payout", 0.0) - r.get("wager", 0.0)) / max(r.get("wager", 1.0), 1e-9)
        for r in rows
    )
    brier = mean(
        (float(r.get("model_prob", 0.0)) - (1.0 if r.get("won") else 0.0)) ** 2
        for r in rows
    )
    return {
        "n": n,
        "hit_rate_pct": round(100.0 * wins / n, 2),
        "roi_pct": round(100.0 * pnl / n, 2),
        "brier": round(brier, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Matchup replay baseline benchmark")
    parser.add_argument("--db-path", default="/opt/golf-model/data/golf.db")
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--out-dir", default="output/audits")
    args = parser.parse_args()

    db.DB_PATH = args.db_path
    years = list(range(args.start_year, args.end_year + 1))
    events = load_historical_events(years=years)
    strategy = _baseline_strategy()

    event_summaries: list[dict] = []
    aggregate_rows: list[dict] = []

    for event in events:
        bets = replay_event(event["event_id"], event["year"], strategy)
        matchup_rows = [
            row
            for row in bets
            if row.get("market") == "matchup" and float(row.get("ev", 0.0) or 0.0) > 0.0
        ]
        if not matchup_rows:
            continue
        metrics = _event_metrics(matchup_rows)
        event_summaries.append(
            {
                "event_id": event["event_id"],
                "event_name": event.get("event_name"),
                "year": event["year"],
                **metrics,
            }
        )
        aggregate_rows.extend(matchup_rows)

    overall = _event_metrics(aggregate_rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": args.db_path,
        "years": years,
        "strategy": strategy.to_json(),
        "overall": overall,
        "events_with_matchup_rows": len(event_summaries),
        "events": event_summaries,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = out_dir / f"matchup_baseline_{stamp}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        "overall "
        f"n={overall['n']} hit_rate={overall['hit_rate_pct']} "
        f"roi={overall['roi_pct']} brier={overall['brier']}"
    )


if __name__ == "__main__":
    main()
