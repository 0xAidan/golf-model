#!/usr/bin/env python3
"""Index every preserved Markdown forecast into a new, non-grading generation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.prediction_archive import build_archive, build_structured_archive

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--structured", action="store_true", help="Index preserved JSON forecast arrays instead of Markdown")
    args = parser.parse_args()
    report = (build_structured_archive if args.structured else build_archive)(args.corpus, args.output)
    print(json.dumps({k: v for k, v in report.items() if k not in {"files", "events"}}, indent=2))
    if "events" in report:
        print(f"Events with forecast observations: {len(report['events'])}")
