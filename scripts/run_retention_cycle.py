#!/usr/bin/env python3
"""Archive tick tables, verify manifest, then prune snapshot history (D1 retention cycle)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_retention_cycle(
    *,
    retain_days: int | None = None,
    dry_run: bool = False,
    vacuum: bool = False,
) -> dict:
    from src import db
    from src.cold_archive import (
        export_tick_tables_before_cutoff,
        snapshot_history_cutoff_utc,
        verified_archive_exists_for_cutoff,
    )
    from src.runtime_paths import get_runtime_identity

    identity = get_runtime_identity()
    db_path = identity.get("db_path") or str(ROOT / "data" / "golf.db")
    exports_dir = (os.environ.get("SNAPSHOT_ARCHIVE_EXPORTS_DIR") or "").strip() or None

    days = retain_days
    if days is None:
        raw = (os.environ.get("SNAPSHOT_HISTORY_RETAIN_DAYS") or "").strip()
        if not raw:
            return {
                "ok": False,
                "skipped": True,
                "reason": "SNAPSHOT_HISTORY_RETAIN_DAYS not set",
            }
        days = int(raw)

    cutoff = snapshot_history_cutoff_utc(int(days))
    report: dict = {
        "ok": True,
        "dry_run": dry_run,
        "retain_days": int(days),
        "cutoff_utc": cutoff,
        "db_path": db_path,
    }

    if dry_run:
        report["archive_exists"] = verified_archive_exists_for_cutoff(cutoff, exports_dir=exports_dir)
        prune_preview = db.prune_snapshot_history_tables(retain_days=int(days), require_archive=True)
        report["prune_preview"] = prune_preview
        return report

    export_result = export_tick_tables_before_cutoff(
        db_path=db_path,
        cutoff_utc=cutoff,
        output_dir=exports_dir,
        retain_days=int(days),
    )
    export_dir = Path(export_result["export_dir"])
    report["export"] = export_result

    if not verified_archive_exists_for_cutoff(cutoff, exports_dir=exports_dir):
        report["ok"] = False
        report["reason"] = "archive verification failed after export"
        return report

    prune_result = db.prune_snapshot_history_tables(retain_days=int(days), require_archive=True)
    report["prune"] = prune_result

    if vacuum and not prune_result.get("skipped"):
        report["reclaim"] = db.reclaim_database_disk()

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Cold-archive tick tables then prune snapshot history.")
    parser.add_argument("--retain-days", type=int, default=None, help="Override SNAPSHOT_HISTORY_RETAIN_DAYS")
    parser.add_argument("--dry-run", action="store_true", help="Report gate state without export/delete")
    parser.add_argument("--vacuum", action="store_true", help="Reclaim disk after successful prune")
    args = parser.parse_args()

    out = run_retention_cycle(
        retain_days=args.retain_days,
        dry_run=args.dry_run,
        vacuum=args.vacuum,
    )
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0 if out.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
