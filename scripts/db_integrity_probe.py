#!/usr/bin/env python3
"""15-minute SQLite integrity probe. Auto-restores only on confirmed corruption."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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

from src.backup import _current_db_path  # noqa: E402
from src.db_integrity import maybe_auto_restore  # noqa: E402


def _restart_live_refresh() -> None:
    if os.environ.get("SKIP_SERVICE_RESTART", "").strip() in {"1", "true", "yes"}:
        return
    subprocess.run(
        ["systemctl", "restart", "golf-live-refresh"],
        check=False,
        timeout=60,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe golf.db and restore only if malformed")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--db", default=None, help="Override DB path")
    args = parser.parse_args()

    db_path = args.db or _current_db_path()
    report = maybe_auto_restore(db_path)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        probe = report.get("probe") or {}
        print(
            f"classification={probe.get('classification')} "
            f"restored={report.get('restored')} "
            f"skipped={report.get('skipped')} "
            f"reason={report.get('skip_reason')}"
        )
    if report.get("restored"):
        _restart_live_refresh()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
