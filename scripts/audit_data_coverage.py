#!/usr/bin/env python3
"""Read-only audit: 2026 coverage, storage breakdown, output/ vs DB gaps."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _write_markdown(report: dict, path: str) -> None:
    lines = [
        "# Data health audit",
        "",
        f"Generated: {report.get('generated_at', '')}",
        "",
        f"**Status:** {report.get('status', 'unknown').upper()}",
        "",
        report.get("summary", ""),
        "",
        "## File sizes",
        "",
    ]
    for k, v in (report.get("file_sizes_human") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Top tables (dbstat)", ""])
    for row in report.get("table_byte_stats") or []:
        lines.append(
            f"- {row['table']}: {row['mb']} MB ({row['pct_of_top']}% of top sample)"
        )
    lines.extend(["", f"## Monthly coverage ({report.get('monthly_coverage', {})})", ""])
    lines.append("| Month | Tournaments | Runs | Picks | Outcomes | prediction_log | market_rows |")
    lines.append("|-------|-------------|------|-------|----------|----------------|-------------|")
    for mo, counts in sorted((report.get("monthly_coverage") or {}).items()):
        lines.append(
            f"| {mo} | {counts.get('tournaments', 0)} | {counts.get('runs', 0)} | "
            f"{counts.get('picks', 0)} | {counts.get('pick_outcomes', 0)} | "
            f"{counts.get('prediction_log', 0)} | {counts.get('market_prediction_rows', 0)} |"
        )
    gaps = report.get("gaps") or []
    if gaps:
        lines.extend(["", "## Gaps", ""])
        for g in gaps:
            lines.append(f"- **{g['type']}**: {g['detail']}")
    warns = report.get("storage_warnings") or []
    if warns:
        lines.extend(["", "## Storage warnings", ""])
        for w in warns:
            lines.append(f"- {w}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit golf.db coverage and storage.")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--db-path", default="", help="Override DB path (default: src.db.DB_PATH)")
    parser.add_argument("--output", default="", help="Write JSON report to this path")
    parser.add_argument("--markdown", default="", help="Write markdown summary alongside JSON")
    parser.add_argument(
        "--with-dbstat",
        action="store_true",
        help="Force per-table page stats (slow on large DBs).",
    )
    args = parser.parse_args()

    db_path = args.db_path.strip() or None
    if db_path:
        os.environ.setdefault("GOLF_DB_PATH", db_path)

    from src.data_health import build_data_health_report

    report = build_data_health_report(db_path=db_path, year=args.year)
    print(json.dumps(report, indent=2))

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote {args.output}", file=sys.stderr)
        md_path = args.markdown or (args.output.rsplit(".", 1)[0] + ".md")
        _write_markdown(report, md_path)

    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
