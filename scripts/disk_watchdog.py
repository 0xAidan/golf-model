#!/usr/bin/env python3
"""Report free disk space and the biggest golf-model consumers.

Read-only: this script never deletes, moves or compacts anything. It exits 2
when free space is under the hard floor (so the systemd unit shows as failed),
0 otherwise. ``--remediate`` and ``--aggressive`` are accepted for
compatibility with the old unit file and do nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.disk_guard import get_disk_state  # noqa: E402
from src.runtime_paths import get_app_root, get_data_dir, get_db_path  # noqa: E402


def _file_mb(path: Path) -> float | None:
    try:
        return round(path.stat().st_size / (1024 * 1024), 1)
    except OSError:
        return None


def _tree_mb(path: Path) -> float | None:
    if not path.is_dir():
        return None
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _exc: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return round(total / (1024 * 1024), 1)


def build_report() -> dict:
    data_dir = get_data_dir()
    db_path = get_db_path()
    app_root = get_app_root()
    state = get_disk_state(str(data_dir))
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "disk": state,
        "consumers_mb": {
            "database": _file_mb(db_path),
            "database_wal": _file_mb(Path(str(db_path) + "-wal")),
            "backups": _tree_mb(app_root / "backups"),
            "raw_dg_capture": _tree_mb(data_dir / "raw_dg"),
            "exports": _tree_mb(data_dir / "exports"),
            "output": _tree_mb(app_root / "output"),
        },
        "remediation": "none (read-only watchdog)",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--remediate", action="store_true", help="ignored; kept for the old unit file")
    parser.add_argument("--aggressive", action="store_true", help="ignored; kept for the old unit file")
    args = parser.parse_args(argv)

    report = build_report()
    disk = report["disk"]
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"free={disk.get('free_mb')} MB state={disk.get('state')} "
              f"(warn<{disk.get('warn_mb')} hard<{disk.get('hard_mb')})")
        for name, size in report["consumers_mb"].items():
            print(f"  {name}: {size} MB")
    return 2 if disk.get("guard_state") == "hard" else 0


if __name__ == "__main__":
    raise SystemExit(main())
