#!/usr/bin/env python3
"""Match local player_keys to PGA Tour IDs and store them for cached headshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from src import db  # noqa: E402
from src.player_photos import seed_photo_ids  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed player_photo_ids from the PGA directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    db.ensure_initialized()
    if db.is_db_unavailable():
        print("database unavailable", file=sys.stderr)
        return 2
    conn = db.get_conn()
    try:
        summary = seed_photo_ids(conn)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(summary))
    else:
        print(
            f"directory={summary['directory']} known={summary['known_players']} "
            f"matched={summary['matched']} overrides={summary['overrides']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
