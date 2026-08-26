#!/usr/bin/env python3
"""Daily storage self-heal: sweep leftovers, prune generated ticks, retain, reclaim."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run automatic storage cleanup.")
    parser.add_argument("--no-vacuum", action="store_true", help="Skip full VACUUM / reclaim")
    parser.add_argument("--retain-days", type=int, default=None, help="Override SNAPSHOT_HISTORY_RETAIN_DAYS")
    args = parser.parse_args()

    from src.ops_jobs import run_storage_cleanup

    report = run_storage_cleanup(vacuum=not args.no_vacuum, retain_days=args.retain_days)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
