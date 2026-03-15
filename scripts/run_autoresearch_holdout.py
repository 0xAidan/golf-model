#!/usr/bin/env python3
"""Run moderate holdout validation for autoresearch pilot winners."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtester.autoresearch_config import (  # noqa: E402
    load_pilot_contract,
    load_strategy_overrides,
    strategy_hash,
)
from backtester.checkpoint_replay import resolve_recent_signature_event  # noqa: E402
from backtester.model_registry import get_live_weekly_model, get_research_champion  # noqa: E402
from backtester.strategy import SimulationResult, StrategyConfig, replay_event  # noqa: E402
from backtester.weighted_walkforward import compute_blended_score, evaluate_guardrails  # noqa: E402
from src import db  # noqa: E402
from src.db import ensure_initialized  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _select_holdout_events(count: int) -> list[dict[str, Any]]:
    pilot = resolve_recent_signature_event()
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT event_id, year, event_name, start_date
        FROM historical_event_info
        WHERE event_id IS NOT NULL
          AND start_date IS NOT NULL
          AND NOT (event_id = ? AND year = ?)
        ORDER BY start_date DESC, year DESC
        LIMIT 20
        """,
        (pilot.event_id, pilot.year),
    ).fetchall()
    conn.close()
    selected = []
    for row in rows:
        if len(selected) >= count:
            break
        selected.append(
            {
                "event_id": str(row["event_id"]),
                "year": int(row["year"]),
                "event_name": row["event_name"],
                "as_of_date": row["start_date"],
            }
        )
    return selected


def _event_metrics(event: dict[str, Any], strategy) -> dict[str, Any]:
    bets = replay_event(
        event_id=event["event_id"],
        year=event["year"],
        strategy=strategy,
        odds_source="open",
        as_of_date=event["as_of_date"],
    )
    sim = SimulationResult(strategy=strategy, events_simulated=1, bet_details=bets)
    sim.compute_metrics()
    return {
        "roi_pct": sim.roi_pct,
        "clv_avg": sim.clv_avg,
        "calibration_error": sim.calibration_error,
        "total_bets": sim.total_bets,
        "max_drawdown_pct": max(0.0, -sim.roi_pct),
    }


def _avg(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0
    return round(sum(float(item.get(key, 0.0)) for item in items) / len(items), 4)


def run_holdout(strategy_overrides_path: Path | None = None, holdout_count: int = 3) -> dict[str, Any]:
    ensure_initialized()
    contract = load_pilot_contract()
    if holdout_count < 3 or holdout_count > 5:
        raise ValueError("holdout_count must be in [3, 5]")

    baseline = get_research_champion("global") or get_live_weekly_model("global")
    overrides = load_strategy_overrides(strategy_overrides_path)
    baseline_values = dict(getattr(baseline, "__dict__", {}))
    candidate = StrategyConfig(**{**baseline_values, **overrides})

    events = _select_holdout_events(holdout_count)
    if len(events) < holdout_count:
        raise ValueError(f"Not enough holdout events available: requested {holdout_count}, got {len(events)}")

    candidate_rows = []
    baseline_rows = []
    for event in events:
        candidate_rows.append({**event, **_event_metrics(event, candidate)})
        baseline_rows.append({**event, **_event_metrics(event, baseline)})

    candidate_summary = {
        "events_evaluated": len(candidate_rows),
        "weighted_roi_pct": _avg(candidate_rows, "roi_pct"),
        "weighted_clv_avg": _avg(candidate_rows, "clv_avg"),
        "weighted_calibration_error": _avg(candidate_rows, "calibration_error"),
        "max_drawdown_pct": max((float(r.get("max_drawdown_pct", 0.0)) for r in candidate_rows), default=0.0),
        "total_bets": sum(int(r.get("total_bets", 0)) for r in candidate_rows),
    }
    baseline_summary = {
        "events_evaluated": len(baseline_rows),
        "weighted_roi_pct": _avg(baseline_rows, "roi_pct"),
        "weighted_clv_avg": _avg(baseline_rows, "clv_avg"),
        "weighted_calibration_error": _avg(baseline_rows, "calibration_error"),
        "max_drawdown_pct": max((float(r.get("max_drawdown_pct", 0.0)) for r in baseline_rows), default=0.0),
        "total_bets": sum(int(r.get("total_bets", 0)) for r in baseline_rows),
    }
    guardrails = evaluate_guardrails(candidate_summary, baseline_summary)
    candidate_score = compute_blended_score(candidate_summary, guardrails)
    baseline_score = compute_blended_score(baseline_summary, {"passed": True})
    delta = round(candidate_score - baseline_score, 4)
    verdict = "pass" if guardrails.get("passed", False) and delta > 0 else "fail"

    return {
        "holdout_verdict": verdict,
        "holdout_metric_delta": delta,
        "holdout_guardrails": "pass" if guardrails.get("passed", False) else "fail",
        "guardrail_results": guardrails,
        "candidate_summary": candidate_summary,
        "baseline_summary": baseline_summary,
        "candidate_strategy_hash": strategy_hash(overrides),
        "baseline_strategy_hash": strategy_hash(baseline.__dict__),
        "pilot_contract_version": contract["pilot_contract_version"],
        "events": events,
        "created_at": _now_iso(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run moderate holdout validation gate")
    parser.add_argument("--strategy-config", type=Path, default=None)
    parser.add_argument("--holdout-count", type=int, default=3)
    args = parser.parse_args()

    verdict = run_holdout(args.strategy_config, args.holdout_count)
    out_dir = ROOT / "output" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"holdout_verdict_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_path": str(out_path), **verdict}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

