#!/usr/bin/env python3
"""Verify and backfill gradeable pick inventory for a live or completed event."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.event_pick_freeze import ensure_event_grading_readiness  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill picks + pick_ledger so an event is ready to grade when it ends",
    )
    parser.add_argument("--event-id", required=True, help="Data Golf event id (e.g. 26 for U.S. Open)")
    parser.add_argument("--year", type=int, required=True, help="Season year")
    parser.add_argument("--event-name", default=None, help="Optional tournament label")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    report = ensure_event_grading_readiness(
        str(args.event_id).strip(),
        year=int(args.year),
        event_name=args.event_name,
    )
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(
            f"Event {report.get('event_id')} ({report.get('event_name') or 'unnamed'}): "
            f"{report.get('status')}"
        )
        print(f"  +EV picks: {report.get('positive_ev_picks')}")
        print(f"  Ledger rows: {report.get('ledger_rows')}")
        print(f"  Ungraded +EV: {report.get('ungraded_positive_ev')}")
        print(f"  Grading ready: {report.get('grading_ready')}")
    return 0 if report.get("grading_ready") or report.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
