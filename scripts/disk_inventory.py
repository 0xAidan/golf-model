#!/usr/bin/env python3
"""Print disk usage for repo data/output/backups and SQLite table row counts."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def _fmt_bytes(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GiB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MiB"
    return f"{n / 1024:.1f} KiB"


def main() -> None:
    data_dir = ROOT / "data"
    output_dir = ROOT / "output"
    backups_dir = ROOT / "backups"
    db_path = data_dir / "golf.db"

    print(f"Repo root: {ROOT}")
    for label, p in (
        ("data/", data_dir),
        ("output/", output_dir),
        ("backups/", backups_dir),
    ):
        sz = _dir_size(p)
        print(f"  {label}: {_fmt_bytes(sz)} ({sz} bytes)")

    for name in ("golf.db", "golf.db-wal", "golf.db-shm", "live_refresh_snapshot.json"):
        p = data_dir / name
        if p.exists():
            print(f"  data/{name}: {_fmt_bytes(p.stat().st_size)}")
        else:
            print(f"  data/{name}: (missing)")

    if not db_path.exists():
        print("SQLite: golf.db not found — skipping pragma / counts")
        return

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA page_count").fetchone()
        page_count = int(row[0]) if row else 0
        row = conn.execute("PRAGMA page_size").fetchone()
        page_size = int(row[0]) if row else 0
        approx = page_count * page_size
        print(f"SQLite file golf.db (approx on-disk via pragma): {page_count} pages × {page_size} B = {_fmt_bytes(approx)}")
        for table in ("live_snapshot_history", "market_prediction_rows", "shadow_event_simulations", "metrics", "rounds", "runs"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {int(n):,} rows")
            except sqlite3.Error as exc:
                print(f"  {table}: (error: {exc})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
