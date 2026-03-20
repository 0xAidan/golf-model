#!/usr/bin/env python3
"""Run multi-objective Optuna study over StrategyConfig (canonical walk-forward benchmark)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from backtester.experiments import get_active_strategy
    from backtester.model_registry import get_live_weekly_model, get_research_champion
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import run_mo_study, study_summary
    from src.db import ensure_initialized

    parser = argparse.ArgumentParser(description="Multi-objective autoresearch (Optuna + walk-forward)")
    parser.add_argument("--n-trials", type=int, default=10, help="Number of Optuna trials")
    parser.add_argument("--years", type=str, default="2024,2025", help="Comma-separated benchmark years")
    parser.add_argument("--study-name", type=str, default="golf_mo_default", help="Optuna study name (persisted)")
    parser.add_argument("--scope", type=str, default="global", help="Model registry scope for baseline")
    parser.add_argument("--n-jobs", type=int, default=1, help="Parallel trials (default 1 for SQLite safety)")
    args = parser.parse_args()

    ensure_initialized()
    years = [int(x.strip()) for x in args.years.split(",") if x.strip()]
    baseline = get_research_champion(args.scope) or get_live_weekly_model(args.scope) or get_active_strategy(args.scope)
    spec = WalkForwardBenchmarkSpec(years=years, min_train_events=2, test_window_size=1)
    study = run_mo_study(
        n_trials=args.n_trials,
        baseline=baseline,
        benchmark_spec=spec,
        study_name=args.study_name,
        n_jobs=args.n_jobs,
    )
    print(json.dumps(study_summary(study), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
