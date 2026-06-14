#!/usr/bin/env python3
"""Export tournament or tick-table rows to JSONL for cold archive (gitignored data/exports/)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

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


def _export_tournament(conn: sqlite3.Connection, tid: int, out_dir: str, db_path: str) -> int:
    manifest: dict[str, int] = {}
    for table, where in _TABLES:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {where}",
            (tid,),
        ).fetchall()
        out_path = os.path.join(out_dir, f"{table}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(dict(row)) + "\n")
        manifest[table] = len(rows)

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "archive_type": "tournament",
                "tournament_id": tid,
                "db_path": db_path,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tables": manifest,
            },
            f,
            indent=2,
        )
    print(f"Exported tournament {tid} to {out_dir}: {manifest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Export rows to JSONL cold archives.")
    parser.add_argument("--tournament-id", type=int, help="Export one tournament's core tables")
    parser.add_argument(
        "--tick-before-days",
        type=int,
        help="Export prunable tick rows older than N days (live_snapshot_history, market_prediction_rows)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(ROOT, "data", "exports"),
        help="Directory for export files",
    )
    parser.add_argument("--db-path", default="")
    args = parser.parse_args()

    from src import db
    from src.cold_archive import export_tick_tables_before_cutoff

    path = args.db_path.strip() or db.DB_PATH
    if not os.path.isfile(path):
        print(f"DB not found: {path}", file=sys.stderr)
        return 2

    if args.tick_before_days is not None:
        days = int(args.tick_before_days)
        from src.cold_archive import export_tick_tables_before_cutoff, snapshot_history_cutoff_utc

        cutoff = snapshot_history_cutoff_utc(days)
        result = export_tick_tables_before_cutoff(
            db_path=path,
            cutoff_utc=cutoff,
            output_dir=args.output_dir,
            retain_days=days,
        )
        print(result)
        return 0

    if args.tournament_id is None:
        parser.error("Provide --tournament-id or --tick-before-days")
        return 2

    out_dir = os.path.join(args.output_dir, f"tournament_{args.tournament_id}")
    os.makedirs(out_dir, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return _export_tournament(conn, args.tournament_id, out_dir, path)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
