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
    from src.history_preservation import prediction_history_preservation_enabled, preservation_skip

    if prediction_history_preservation_enabled():
        return preservation_skip(
            dry_run=dry_run, retain_days=retain_days,
            prune_preview=preservation_skip() if dry_run else None,
            research_rotation=preservation_skip(),
        )

    from src import db
    from src.cold_archive import (
        export_tick_tables_before_cutoff, snapshot_history_cutoff_utc,
        verified_archive_exists_for_cutoff,
    )
    from src.runtime_paths import get_runtime_identity

    identity = get_runtime_identity()
    db_path = identity.get("db_path") or str(ROOT / "data" / "golf.db")
    if Path(db_path).resolve() != Path(db.DB_PATH).resolve():
        return {"ok": False, "skipped": True, "dry_run": dry_run,
                "reason": "runtime/archive database differs from pruning database"}
    exports_dir = (os.environ.get("SNAPSHOT_ARCHIVE_EXPORTS_DIR") or "").strip() or None
    try:
        days = int(retain_days if retain_days is not None else os.environ.get("SNAPSHOT_HISTORY_RETAIN_DAYS", ""))
    except (ValueError, TypeError):
        return {"ok": False, "skipped": True, "dry_run": dry_run,
                "reason": "SNAPSHOT_HISTORY_RETAIN_DAYS not set or invalid"}
    if days <= 0:
        return {"ok": False, "skipped": True, "dry_run": dry_run, "reason": "retain_days must be positive"}
    cutoff = snapshot_history_cutoff_utc(days)
    report: dict = {
        "ok": True, "dry_run": dry_run, "retain_days": days,
        "cutoff_utc": cutoff, "db_path": db_path,
    }
    if dry_run:
        report["prune_preview"] = db.prune_snapshot_history_tables(
            retain_days=days, dry_run=True, cutoff_utc=cutoff,
        )
        report["archive_exists"] = report["prune_preview"].get("archive_verified", False)
        # Do not invoke output rotation even in preview: older implementations
        # created archive directories before their dry-run branch.
        report["research_rotation"] = {
            "ok": True, "skipped": True, "dry_run": True, "reason": "read-only preview; no rotation",
        }
        report["ok"] = bool(report["prune_preview"].get("ok", False))
        return report

    report["export"] = export_tick_tables_before_cutoff(
        db_path=db_path, cutoff_utc=cutoff, output_dir=exports_dir, retain_days=days,
    )
    if not verified_archive_exists_for_cutoff(cutoff, exports_dir=exports_dir, db_path=db_path):
        return {**report, "ok": False, "reason": "archive verification failed after export"}
    # Pass the identical cutoff; verification is repeated under the delete lock.
    prune_result = db.prune_snapshot_history_tables(retain_days=days, cutoff_utc=cutoff)
    report["prune"] = prune_result
    report["ok"] = bool(prune_result.get("ok", False))
    if prune_result.get("skipped"):
        report["skipped"] = True
        return report
    if vacuum:
        report["reclaim"] = db.reclaim_database_disk()
    from src.output_manager import rotate_research_artifacts

    report["research_rotation"] = rotate_research_artifacts(dry_run=False)
    if not report["research_rotation"].get("ok", True):
        report["ok"] = False
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
