#!/usr/bin/env python3
"""Generate an additive static report from the preserved season export only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.performance_analytics import BOOTSTRAP_REPLICATES, build_performance_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, default=ROOT / "frontend/public/reports/season-2026-decisions.csv")
    parser.add_argument("--season", type=Path, default=ROOT / "frontend/public/reports/season-2026.json")
    parser.add_argument("--output", type=Path, default=ROOT / "frontend/public/reports/performance-2026.json")
    parser.add_argument("--replicates", type=int, default=BOOTSTRAP_REPLICATES)
    args = parser.parse_args()
    if args.replicates < 1:
        parser.error("--replicates must be positive")
    if args.output.resolve() in {args.decisions.resolve(), args.season.resolve()}:
        parser.error("The report output must differ from the preserved inputs")
    source_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (args.decisions, args.season)}
    with args.decisions.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    season = json.loads(args.season.read_text(encoding="utf-8"))
    report = build_performance_report(rows, season, source_hashes=source_hashes, replicates=args.replicates)
    payload = json.dumps(report, allow_nan=False, ensure_ascii=False, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "as_of": report["as_of"], "bytes": len(payload.encode()),
                      "scopes": len(report["scopes"]), "coverage": report["coverage"]}, indent=2))


if __name__ == "__main__":
    main()
