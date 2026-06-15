#!/usr/bin/env python3
"""Backfill and grade all completed PGA events with ungraded +EV inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.event_pick_freeze import ensure_all_completed_pga_events_graded  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure completed events are captured and graded")
    parser.add_argument("--year", type=int, default=None, help="Season year (default: current)")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    report = ensure_all_completed_pga_events_graded(year=args.year)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"Year {report['year']}: processed {report['events_processed']} events")
        for row in report.get("results") or []:
            print(
                f"  event {row.get('event_id')}: {row.get('status')} "
                f"({row.get('reason', '')})"
            )
        if not report.get("ok"):
            return 1
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
