#!/usr/bin/env python3
"""Prune old live snapshot / market prediction rows from SQLite.

Reads ``SNAPSHOT_HISTORY_RETAIN_DAYS`` from the environment (integer days).
When unset or non-positive, exits without deleting anything.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    raw = os.environ.get("SNAPSHOT_HISTORY_RETAIN_DAYS", "").strip()
    if not raw:
        print("SNAPSHOT_HISTORY_RETAIN_DAYS not set or empty; skipping prune (no DELETE).")
        return 0
    try:
        days = int(raw)
    except ValueError:
        print(f"Invalid SNAPSHOT_HISTORY_RETAIN_DAYS={raw!r}; expected integer.")
        return 2
    if days <= 0:
        print(f"SNAPSHOT_HISTORY_RETAIN_DAYS={days} is not positive; skipping prune (no DELETE).")
        return 0
    from src import db

    db.ensure_initialized()
    counts = db.prune_snapshot_history_tables(days)
    print(f"Pruned snapshot tables (retain_days={days}): {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
