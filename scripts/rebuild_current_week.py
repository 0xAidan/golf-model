#!/usr/bin/env python3
"""Queue live-refresh + completed-event grading after a restore."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.current_week_rebuild import rebuild_current_week  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild current week after restore")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = rebuild_current_week(year=args.year)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"ok={report.get('ok')} errors={report.get('errors')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
