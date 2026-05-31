#!/usr/bin/env python3
"""Export one tournament's core tables to JSONL for cold archive (gitignored data/exports/)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_TABLES = [
    ("tournaments", "id = ?"),
    ("picks", "tournament_id = ?"),
    ("pick_outcomes", "pick_id IN (SELECT id FROM picks WHERE tournament_id = ?)"),
    ("prediction_log", "tournament_id = ?"),
    ("results", "tournament_id = ?"),
    ("runs", "tournament_id = ?"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export tournament rows to JSONL files.")
    parser.add_argument("--tournament-id", type=int, required=True)
    parser.add_argument(
        "--output-dir",
        default=os.path.join(ROOT, "data", "exports"),
        help="Directory for export files",
    )
    parser.add_argument("--db-path", default="")
    args = parser.parse_args()

    from src import db

    path = args.db_path.strip() or db.DB_PATH
    if not os.path.isfile(path):
        print(f"DB not found: {path}", file=sys.stderr)
        return 2

    out_dir = os.path.join(
        args.output_dir,
        f"tournament_{args.tournament_id}",
    )
    os.makedirs(out_dir, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    manifest: dict[str, int] = {}
    tid = args.tournament_id

    for table, where in _TABLES:
        if "pick_id" in where:
            params = (tid,)
        else:
            params = (tid,)
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {where}",
            params,
        ).fetchall()
        out_path = os.path.join(out_dir, f"{table}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(dict(row)) + "\n")
        manifest[table] = len(rows)

    conn.close()
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {"tournament_id": tid, "db_path": path, "tables": manifest},
            f,
            indent=2,
        )
    print(f"Exported to {out_dir}: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
