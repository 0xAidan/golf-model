#!/usr/bin/env python3
"""Benchmark fast-tier vs plain evaluation; commit results as evidence.

Writes JSON under docs/research/benchmarks/ (committed) since output/research/
is gitignored. Per PROGRAM.md: if a fast-tier experiment exceeds the 10-minute
target, this script reports measured cost so windows get trimmed deliberately.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtester.fast_tier import (
    FastTierWindow,
    compute_precomputed_baseline_results,
    select_research_windows,
)
from backtester.research_lab.fingerprint import evaluator_identity
from backtester.strategy import SimulationResult, StrategyConfig, replay_event
from backtester.weighted_walkforward import _default_replay_runner

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "docs" / "research" / "benchmarks"
TARGET_EXPERIMENT_SECONDS = 600.0  # <=10 min per experiment (PROGRAM.md budget)


def _time_plain_experiment(events: list[dict], candidate: StrategyConfig, baseline: StrategyConfig) -> dict:
    t0 = time.perf_counter()
    candidate_rows = []
    baseline_rows = []
    for split_events in [events]:
        for event in split_events:
            candidate_rows.append({**event, **_default_replay_runner(event, candidate)})
            baseline_rows.append({**event, **_default_replay_runner(event, baseline)})
    elapsed = time.perf_counter() - t0
    return {"seconds": round(elapsed, 3), "events": len(events)}


def _time_fast_experiment(events: list[dict], candidate: StrategyConfig, baseline: StrategyConfig) -> dict:
    t0 = time.perf_counter()
    with FastTierWindow(events):
        prefetch_done = time.perf_counter()
        candidate_rows = []
        for event in events:
            candidate_rows.append({**event, **_default_replay_runner(event, candidate)})
        replay_seconds = time.perf_counter() - prefetch_done
    elapsed = time.perf_counter() - t0
    return {
        "seconds": round(elapsed, 3),
        "prefetch_seconds": round(prefetch_done - t0, 3),
        "replay_seconds": round(replay_seconds, 3),
        "events": len(events),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark autoresearch tiers")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    from src.db import ensure_initialized

    ensure_initialized()

    windows = select_research_windows()
    search_events = windows["search"]
    if not search_events:
        print(json.dumps({"error": "no PIT-ready events available for benchmark"}, indent=2))
        return 1

    candidate = StrategyConfig(name="benchmark_candidate", min_ev=0.06)
    baseline = StrategyConfig(name="benchmark_baseline")

    plain_runs = []
    for _ in range(max(1, args.repeat)):
        plain_runs.append(_time_plain_experiment(search_events, candidate, baseline))
    fast_runs = []
    for _ in range(max(1, args.repeat)):
        fast_runs.append(_time_fast_experiment(search_events, candidate, baseline))

    plain_median = statistics.median(r["seconds"] for r in plain_runs)
    fast_median = statistics.median(r["seconds"] for r in fast_runs)

    result = {
        "date": date.today().isoformat(),
        "window": {
            "search_events": len(search_events),
            "event_ids": [f"{e['event_id']}/{e['year']}" for e in search_events],
        },
        "plain_experiment": {
            "runs": plain_runs,
            "median_seconds": round(plain_median, 3),
        },
        "fast_experiment": {
            "runs": fast_runs,
            "median_seconds": round(fast_median, 3),
        },
        "speedup_x": round(plain_median / fast_median, 3) if fast_median else None,
        "trials_per_60min_at_fast_tier": int((3600 / fast_median) * len(search_events) // len(search_events)) if fast_median else None,
        "within_budget_target": bool(fast_median <= TARGET_EXPERIMENT_SECONDS),
        "budget_target_seconds": TARGET_EXPERIMENT_SECONDS,
        **evaluator_identity(),
    }
    # trials estimate: how many full-window experiments fit in the Standard budget
    result["experiments_per_standard_night"] = int(3600 // fast_median) if fast_median else 0

    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"tier_benchmark_{date.today().isoformat()}_{int(time.time())}.json"
    out_path = BENCHMARK_DIR / out_name
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["within_budget_target"]:
        print(
            f"WARNING: fast tier exceeds {TARGET_EXPERIMENT_SECONDS}s target — "
            "propose window trims per PROGRAM.md rather than silently slowing down.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
