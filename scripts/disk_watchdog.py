#!/usr/bin/env python3
"""Disk free-space watchdog: alert early and auto-remediate when the volume is tight.

Runs every 15 minutes via golf-disk-watchdog.timer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.backup import sweep_orphan_sidecars  # noqa: E402
from src.disk_guard import get_disk_state  # noqa: E402
from src.runtime_paths import get_app_root  # noqa: E402
from src.telegram_alerts import send_ops_alert  # noqa: E402


def evaluate(path: str | None = None) -> dict:
    root = str(path or get_app_root())
    disk = get_disk_state(root)
    free_mb = disk.get("free_mb")
    guard = str(disk.get("guard_state") or "ok")
    state = str(disk.get("state") or "unknown")
    actions: list[str] = []
    alert = False
    severity = "info"

    if guard == "hard" or state == "critical":
        alert = True
        severity = "critical"
        actions.append("hard_floor")
    elif guard == "warn" or state == "warn":
        alert = True
        severity = "warn"
        actions.append("warn_floor")

    return {
        "path": root,
        "disk": disk,
        "alert": alert,
        "severity": severity,
        "actions": actions,
        "free_mb": free_mb,
    }


def _remove_vacuum_into_temp(db_path: str) -> list[str]:
    """Remove abandoned VACUUM INTO temps without a full quick_check (watchdog-safe)."""
    import os

    removed: list[str] = []
    for suffix in (".vacuum_into",):
        path = db_path + suffix
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            continue
    return removed


def remediate(*, aggressive: bool = False) -> dict:
    """Best-effort free-space recovery that never deletes the live database."""
    import os

    from src import db

    result: dict = {"ok": True, "steps": {}}
    try:
        removed = sweep_orphan_sidecars()
        result["steps"]["sidecar_sweep"] = {"removed": removed, "count": len(removed)}
    except Exception as exc:
        result["ok"] = False
        result["steps"]["sidecar_sweep"] = {"error": str(exc)}

    try:
        vacuum_temps = _remove_vacuum_into_temp(db.DB_PATH)
        result["steps"]["vacuum_into_temps"] = {
            "removed": vacuum_temps,
            "count": len(vacuum_temps),
        }
    except Exception as exc:
        result["ok"] = False
        result["steps"]["vacuum_into_temps"] = {"error": str(exc)}

    if aggressive:
        try:
            from src.ops_jobs import run_storage_cleanup

            # Skip vacuum on the watchdog path — vacuum needs exclusive headroom and
            # can take >10 minutes on a 13GB DB. Retention/prune only.
            cleanup = run_storage_cleanup(vacuum=False)
            result["steps"]["cleanup"] = cleanup
            if not cleanup.get("ok"):
                result["ok"] = False
        except Exception as exc:
            result["ok"] = False
            result["steps"]["cleanup"] = {"error": str(exc)}

    # Touch mtime so operators can see the watchdog ran.
    try:
        marker = os.path.join(str(get_app_root()), "data", "disk_watchdog_last_run")
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write(str(result.get("ok")))
    except OSError:
        pass

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Disk free-space watchdog")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--remediate",
        action="store_true",
        help="Sweep orphan sidecars / stale reclaim copies when below warn floor",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Also run retention cleanup (no vacuum) when below warn floor",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        default=True,
        help="Send Telegram ops alert when below warn/hard (default on)",
    )
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Disable Telegram alerts",
    )
    args = parser.parse_args()

    payload = evaluate()
    if payload.get("alert") and (args.remediate or args.aggressive):
        payload["remediation"] = remediate(aggressive=bool(args.aggressive))
        # Re-evaluate after remediation so the alert reflects the new free space.
        payload["disk_after"] = get_disk_state(payload["path"])
        payload["free_mb_after"] = payload["disk_after"].get("free_mb")

    should_alert = payload.get("alert") and not args.no_alert and args.alert
    if should_alert:
        free = payload.get("free_mb")
        warn = (payload.get("disk") or {}).get("warn_mb")
        hard = (payload.get("disk") or {}).get("hard_mb")
        after = payload.get("free_mb_after")
        msg = (
            f"Disk {payload.get('severity')}: {free} MiB free "
            f"(warn<{warn}, hard<{hard})"
        )
        if after is not None:
            msg += f"; after remediation {after} MiB free"
        send_ops_alert(msg, severity=str(payload.get("severity") or "warn"))

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        disk = payload.get("disk") or {}
        print(
            f"disk state={disk.get('state')} guard={disk.get('guard_state')} "
            f"free_mb={disk.get('free_mb')}"
        )
        if payload.get("remediation"):
            print(f"remediation ok={payload['remediation'].get('ok')}")

    if payload.get("severity") == "critical":
        return 2
    if payload.get("alert"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
