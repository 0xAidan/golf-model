#!/usr/bin/env python3
"""Weekly refresh: Data Golf backfill + research backtest ledger + PIT rebuild.

Idempotent wrapper around the resume-safe tooling, designed for the weekly deep
cycle (see workers/autoresearch_orchestrator.py, PR6). Safe to run manually.

Usage:
    python3 scripts/run_weekly_research_refresh.py               # full sequence
    python3 scripts/run_weekly_research_refresh.py --skip-backfill
    python3 scripts/run_weekly_research_refresh.py --ledger-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HEARTBEAT_PATH = Path("data") / "research_refresh_heartbeat.json"


def _write_heartbeat(stage: str, status: str, detail: dict) -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        **detail,
    }
    tmp = HEARTBEAT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(HEARTBEAT_PATH)


def run_sequence(*, skip_backfill: bool = False, ledger_only: bool = False) -> int:
    from src.db import ensure_initialized

    ensure_initialized()

    if not ledger_only and not skip_backfill:
        t0 = time.perf_counter()
        _write_heartbeat("dg_backfill", "running", {})
        try:
            from backtester.backfill import run_full_backfill

            run_full_backfill()
            _write_heartbeat(
                "dg_backfill", "ok", {"seconds": round(time.perf_counter() - t0, 1)}
            )
        except Exception as exc:
            _write_heartbeat("dg_backfill", "error", {"error": str(exc)})
            raise

    t0 = time.perf_counter()
    _write_heartbeat("backtest_ledger", "running", {})
    from backtester.backtest_ledger import build_research_backtest_lines, coverage_summary

    stats = build_research_backtest_lines()
    coverage = coverage_summary()
    _write_heartbeat(
        "backtest_ledger",
        "ok",
        {
            "seconds": round(time.perf_counter() - t0, 1),
            "inserted_or_refreshed": stats.rows_refreshed,
            "events": stats.events_seen,
            "outcomes_set": stats.outcomes_set,
        },
    )
    print(json.dumps({"ledger_stats": vars(stats), "coverage": coverage}, indent=2, default=str))

    if ledger_only:
        return 0

    t0 = time.perf_counter()
    _write_heartbeat("pit_rebuild", "running", {})
    try:
        from backtester.pit_stats import build_all_pit_stats

        build_all_pit_stats()
        _write_heartbeat(
            "pit_rebuild", "ok", {"seconds": round(time.perf_counter() - t0, 1)}
        )
    except Exception as exc:
        _write_heartbeat("pit_rebuild", "error", {"error": str(exc)})
        raise

    print("Weekly research refresh complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly research data refresh")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--ledger-only", action="store_true")
    args = parser.parse_args()
    return run_sequence(skip_backfill=args.skip_backfill, ledger_only=args.ledger_only)


if __name__ == "__main__":
    raise SystemExit(main())
