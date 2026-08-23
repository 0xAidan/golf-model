#!/usr/bin/env python3
"""Open the sealed holdout — operator command only.

Evaluates the current champion candidate against the sealed holdout events and
appends results permanently to output/research/ledger.jsonl (source: agent,
verdict fields prefixed holdout_). This is the quarterly, explicit-command
check; it is never part of nightly cycles.

Usage:
    python3 scripts/run_autoresearch_sealed_holdout.py            # dry summary
    python3 scripts/run_autoresearch_sealed_holdout.py --write    # append to ledger
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtester.model_registry import get_research_champion, get_live_weekly_model
from backtester.research_lab.ledger import append_ledger_row, _git_head
from backtester.research_lab.canonical import (
    CHECKPOINT_SCRIPT_EVALUATOR_VERSION,
    EVAL_CONTRACT_VERSION_WALK_FORWARD,
)
from backtester.sealed_holdout import load_sealed_holdout, SealedHoldoutError
from backtester.strategy import SimulationResult, StrategyConfig, replay_event


def evaluate_sealed_holdout() -> dict:
    """Replay champion + baseline on each sealed event; return a verdict payload."""
    from src.db import ensure_initialized

    ensure_initialized()
    doc = load_sealed_holdout()
    strategy = get_research_champion("global") or get_live_weekly_model("global") or StrategyConfig()

    event_results = []
    t0 = time.perf_counter()
    for event in doc["events"]:
        bets = replay_event(str(event["event_id"]), int(event["year"]), strategy)
        result = SimulationResult(strategy=strategy, events_simulated=1, bet_details=bets)
        result.compute_metrics()
        event_results.append(
            {
                "event_id": event["event_id"],
                "year": event["year"],
                "event_name": event.get("event_name"),
                "total_bets": result.total_bets,
                "wins": result.wins,
                "roi_pct": result.roi_pct,
                "clv_avg": result.clv_avg,
                "calibration_error": result.calibration_error,
            }
        )
    duration_ms = int((time.perf_counter() - t0) * 1000)

    total_bets = sum(r["total_bets"] for r in event_results)
    total_wins = sum(r["wins"] for r in event_results)
    payload = {
        "sealed_holdout_version": doc["sealed_holdout_version"],
        "strategy_hash": strategy.to_json(),
        "events": event_results,
        "total_bets": total_bets,
        "hit_rate": round(total_wins / total_bets, 4) if total_bets else None,
        "duration_ms": duration_ms,
    }
    # ROI aggregate: simple mean of per-event ROI weighted by nothing (flat reporting).
    rois = [r["roi_pct"] for r in event_results if r["total_bets"] > 0]
    payload["mean_roi_pct"] = round(sum(rois) / len(rois), 4) if rois else 0.0
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Open the sealed autoresearch holdout")
    parser.add_argument("--write", action="store_true", help="Append results to the ledger permanently")
    args = parser.parse_args()

    try:
        payload = evaluate_sealed_holdout()
    except SealedHoldoutError as exc:
        print(f"autoresearch_error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))

    if args.write:
        append_ledger_row(
            {
                "source": "agent",
                "kind": "sealed_holdout",
                "git_commit": _git_head(),
                "evaluator_version": CHECKPOINT_SCRIPT_EVALUATOR_VERSION,
                "walk_forward_eval_contract_version": EVAL_CONTRACT_VERSION_WALK_FORWARD,
                "holdout_verdict_payload": payload,
                "total_bets": payload["total_bets"],
                "mean_roi_pct": payload["mean_roi_pct"],
                "duration_ms": payload["duration_ms"],
            }
        )
        print("Sealed-holdout row appended to ledger permanently.")
    else:
        print("Dry run only; pass --write to append to the ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
