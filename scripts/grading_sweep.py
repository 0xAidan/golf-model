#!/usr/bin/env python3
"""Run completed-event grading sweep and reconciliation (separate from worker watchdog)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def run_grading_sweep(*, year: int | None = None) -> dict:
    from src.event_pick_freeze import ensure_all_completed_pga_events_graded
    from src.grading_reconciliation import reconcile_grading

    grading_report = ensure_all_completed_pga_events_graded(year=year)
    reconciliation = reconcile_grading(limit_events=10)
    return {
        "ok": bool(grading_report.get("ok")) and reconciliation.get("status") != "discrepancies",
        "grading": grading_report,
        "reconciliation": reconciliation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Completed-event grading sweep")
    parser.add_argument("--year", type=int, default=None, help="Season year to sweep")
    parser.add_argument("--json", action="store_true", help="Emit JSON result on stdout")
    args = parser.parse_args()

    payload = run_grading_sweep(year=args.year)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        reconciliation = payload.get("reconciliation") or {}
        grading = payload.get("grading") or {}
        ungraded_events = reconciliation.get("events_with_ungraded_positive_ev")
        print(
            "grading sweep: "
            f"grading_ok={grading.get('ok')} "
            f"reconciliation={reconciliation.get('status')} "
            f"ungraded_events={ungraded_events}"
        )

    if not payload.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
