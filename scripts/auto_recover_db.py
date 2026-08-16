#!/usr/bin/env python3
"""Strict auto-restore for a confirmed-corrupt live SQLite file."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.backup import latest_verified_backup, restore_backup  # noqa: E402
from src.current_week_rebuild import rebuild_current_week, write_rebuild_heartbeat  # noqa: E402
from src.db_integrity import probe_live_database  # noqa: E402
from src.runtime_paths import get_db_path  # noqa: E402
from src.telegram_alerts import send_ops_alert  # noqa: E402

_SERVICES = ("golf-dashboard", "golf-live-refresh", "golf-agent")


def _run(cmd: list[str]) -> int:
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def _quarantine_live(db_path: Path) -> str | None:
    if not db_path.is_file():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = db_path.with_name(f"{db_path.name}.malformed_{stamp}.gz")
    with db_path.open("rb") as raw, gzip.open(dest, "wb", compresslevel=1) as gz:
        shutil.copyfileobj(raw, gz)
    try:
        db_path.unlink()
    except OSError:
        pass
    return str(dest)


def recover(*, dry_run: bool = False, skip_rebuild: bool = False) -> dict:
    probe = probe_live_database(timeout_seconds=8.0)
    report: dict = {
        "ok": False,
        "probe": probe,
        "backup": None,
        "quarantine": None,
        "rebuild": None,
    }
    if probe.get("state") != "corrupt":
        report["error"] = (
            f"Refusing recover: probe state is {probe.get('state')!r}, not 'corrupt'"
        )
        return report

    backup = latest_verified_backup()
    report["backup"] = backup
    if not backup:
        report["error"] = "No integrity-ok backup available"
        write_rebuild_heartbeat(phase="db_malformed", last_error=report["error"])
        send_ops_alert(report["error"], severity="critical")
        return report

    if dry_run:
        report["ok"] = True
        report["dry_run"] = True
        return report

    write_rebuild_heartbeat(phase="db_malformed", last_error=str(probe.get("error")))
    send_ops_alert(
        f"Auto-recover starting from {os.path.basename(backup)} "
        f"(live DB {probe.get('state')}: {probe.get('error')})",
        severity="critical",
    )

    for unit in _SERVICES:
        _run(["systemctl", "stop", unit])

    db_path = get_db_path()
    report["quarantine"] = _quarantine_live(db_path)
    restored = restore_backup(backup)
    if not restored:
        report["error"] = f"restore_backup failed for {backup}"
        send_ops_alert(report["error"], severity="critical")
        return report

    smoke = probe_live_database(timeout_seconds=15.0)
    report["restored_probe"] = smoke
    if not smoke.get("ok"):
        report["error"] = f"restored file failed smoke: {smoke.get('error')}"
        send_ops_alert(report["error"], severity="critical")
        return report

    _run(["systemctl", "reset-failed", "golf-dashboard", "golf-live-refresh"])
    _run(["systemctl", "start", "golf-dashboard"])
    _run(["systemctl", "start", "golf-live-refresh"])

    if not skip_rebuild:
        report["rebuild"] = rebuild_current_week()

    report["ok"] = True
    send_ops_alert(
        f"Auto-recover succeeded from {os.path.basename(backup)}. Current week rebuild queued.",
        severity="info",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore live DB after confirmed corruption")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-rebuild", action="store_true")
    args = parser.parse_args()
    report = recover(dry_run=args.dry_run, skip_rebuild=args.skip_rebuild)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"ok={report.get('ok')} error={report.get('error')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
