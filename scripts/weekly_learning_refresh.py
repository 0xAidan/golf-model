#!/usr/bin/env python3
"""Idempotent research-only weekly training after the ordinary DataGolf data refresh.

Use with the existing weekly ingestion timer, or run manually. Reads the configured
database in SQLite query-only mode, appends artifacts and never promotes a model.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.train_learning_challenger import main as train_main
from src.db import DB_PATH


def main(argv=None, *, root=None, db_path=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    db_path = db_path or DB_PATH
    snapshot = Path(db_path).parent / "live_refresh_snapshot.json"
    snapshot_args = ["--snapshot", str(snapshot)] if snapshot.is_file() else []
    seed = root / "data/research/verified-learning-corpus-v2-identity-repair.jsonl.gz"
    if not seed.is_file() and "--seed-cache" not in argv:
        print(json.dumps({"state": "missing_verified_history_seed", "required_path": str(seed),
                          "message": "Weekly v2 refresh refused; restore the verified seed corpus before running."}))
        return 2
    protocol_args = ["--protocol", "recovered-v2"]
    if seed.is_file():
        protocol_args += ["--seed-cache", str(seed)]
    return train_main([
        "--source", db_path,
        # The legacy output-content API can read anything under output/.
        # Training inputs and source references belong in the private data tree.
        "--output", str(root / "data" / "research" / "learning-runs"),
        "--public-report", str(root / "frontend" / "public" / "reports" / "learning-latest.json"),
        *snapshot_args,
        *protocol_args,
        *argv,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
