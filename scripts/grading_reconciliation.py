#!/usr/bin/env python3
"""CLI: reconcile displayed +EV picks against graded outcomes and write a report.

Usage:
    python3 scripts/grading_reconciliation.py [--source cockpit|lab_sandbox] [--limit N] [--write]

Writes a markdown report to output/audits/grading_reconciliation_<YYYYMMDD>.md when
--write is passed. Exit code is non-zero when discrepancies are found (so it can gate CI
or a deploy check against the production DB).
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.grading_reconciliation import reconcile_grading, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Grading reconciliation report")
    parser.add_argument("--source", default=None, help="pick source filter (cockpit|lab_sandbox)")
    parser.add_argument("--limit", type=int, default=None, help="max events to inspect")
    parser.add_argument("--write", action="store_true", help="write markdown report under output/audits/")
    args = parser.parse_args()

    report = reconcile_grading(source=args.source, limit_events=args.limit)
    markdown = render_markdown(report)
    print(markdown)

    if args.write:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "audits")
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        out_path = os.path.join(out_dir, f"grading_reconciliation_{stamp}.md")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        print(f"\nWrote {out_path}")

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
