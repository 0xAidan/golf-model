"""Read-only SQLite integrity probe and confirmed-corrupt auto-restore."""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.atomic_io import atomic_write_json
from src.runtime_paths import get_data_dir

logger = logging.getLogger("golf.db_integrity")

STATE_FILENAME = "db_integrity_state.json"
AUTO_RESTORE_ENV = "AUTO_RESTORE_ON_CORRUPT"

# Only these SQLite messages authorize an automatic restore.
_RESTORE_CLASSIFICATIONS = frozenset({"malformed", "not_a_database"})


def integrity_state_path() -> Path:
    return get_data_dir() / STATE_FILENAME


def read_integrity_state() -> dict[str, Any]:
    path = integrity_state_path()
    if not path.is_file():
        return {}
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_integrity_state(payload: dict[str, Any]) -> None:
    get_data_dir().mkdir(parents=True, exist_ok=True)
    atomic_write_json(integrity_state_path(), payload)


def classify_sqlite_error(message: str) -> str:
    text = (message or "").lower()
    if "malformed" in text or "disk image is malformed" in text:
        return "malformed"
    if "not a database" in text or "file is not a database" in text:
        return "not_a_database"
    if "locked" in text or "busy" in text:
        return "locked"
    if "disk" in text and ("full" in text or "space" in text):
        return "disk_full"
    return "other"


def probe_sqlite_file(db_path: str) -> dict[str, Any]:
    """Read-only integrity probe. Never mutates the file."""
    result: dict[str, Any] = {
        "ok": False,
        "path": db_path,
        "classification": "missing",
        "quick_check": None,
        "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if not os.path.isfile(db_path):
        result["error"] = "database file not found"
        return result
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            check = str(row[0]) if row else "unknown"
        finally:
            conn.close()
    except sqlite3.Error as exc:
        result["error"] = str(exc)
        result["classification"] = classify_sqlite_error(str(exc))
        return result
    result["quick_check"] = check
    if check == "ok":
        result["ok"] = True
        result["classification"] = "ok"
        return result
    result["classification"] = classify_sqlite_error(check)
    if result["classification"] == "other" and "malformed" in check.lower():
        result["classification"] = "malformed"
    result["error"] = check
    return result


def auto_restore_enabled() -> bool:
    raw = (os.environ.get(AUTO_RESTORE_ENV) or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def latest_good_backup() -> str | None:
    from src.backup import list_backups, read_integrity_sidecar, verify_backup_integrity

    for entry in list_backups():
        path = entry.get("path")
        if not path:
            continue
        sidecar = read_integrity_sidecar(path)
        if sidecar and sidecar.get("ok"):
            return str(path)
        verified = verify_backup_integrity(path)
        if verified.get("ok"):
            return str(path)
    return None


def maybe_auto_restore(db_path: str) -> dict[str, Any]:
    """Restore only when SQLite itself says the file is corrupt.

    Never restores on lock, disk-full, or a slow/unknown error.
    """
    probe = probe_sqlite_file(db_path)
    report: dict[str, Any] = {
        "probed": True,
        "probe": probe,
        "restored": False,
        "backup_path": None,
        "skipped": False,
        "skip_reason": None,
    }
    if probe.get("ok"):
        write_integrity_state(
            {
                "ok": True,
                "classification": "ok",
                "checked_at": probe.get("checked_at"),
                "restore_in_progress": False,
            }
        )
        from src.db import reset_db_availability

        reset_db_availability()
        return report

    classification = str(probe.get("classification") or "other")
    if classification not in _RESTORE_CLASSIFICATIONS:
        report["skipped"] = True
        report["skip_reason"] = f"classification={classification}"
        write_integrity_state(
            {
                "ok": False,
                "classification": classification,
                "reason": probe.get("error"),
                "checked_at": probe.get("checked_at"),
                "restore_in_progress": False,
            }
        )
        return report

    if not auto_restore_enabled():
        report["skipped"] = True
        report["skip_reason"] = "auto_restore_disabled"
        write_integrity_state(
            {
                "ok": False,
                "classification": classification,
                "reason": probe.get("error"),
                "checked_at": probe.get("checked_at"),
                "restore_in_progress": False,
            }
        )
        return report

    backup_path = latest_good_backup()
    if not backup_path:
        report["skipped"] = True
        report["skip_reason"] = "no_good_backup"
        write_integrity_state(
            {
                "ok": False,
                "classification": classification,
                "reason": "no backup with a passing integrity sidecar",
                "checked_at": probe.get("checked_at"),
                "restore_in_progress": False,
            }
        )
        return report

    from src.backup import restore_backup
    from src.db import mark_db_unavailable, reset_db_availability
    from src.ops_alerts import send_ops_alert

    write_integrity_state(
        {
            "ok": False,
            "classification": classification,
            "reason": probe.get("error"),
            "checked_at": probe.get("checked_at"),
            "restore_in_progress": True,
            "backup_path": backup_path,
        }
    )
    mark_db_unavailable(str(probe.get("error") or classification))
    send_ops_alert(
        "Golf Model database is corrupt",
        f"SQLite said {classification}. Restoring {os.path.basename(backup_path)}.",
    )
    try:
        restored = restore_backup(backup_path)
    except Exception as exc:
        logger.exception("auto-restore failed")
        write_integrity_state(
            {
                "ok": False,
                "classification": classification,
                "reason": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "restore_in_progress": False,
            }
        )
        send_ops_alert("Golf Model restore failed", str(exc))
        report["error"] = str(exc)
        return report

    report["restored"] = bool(restored)
    report["backup_path"] = backup_path
    if restored:
        reset_db_availability()
        write_integrity_state(
            {
                "ok": True,
                "classification": "restored",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "restore_in_progress": False,
                "backup_path": backup_path,
            }
        )
        send_ops_alert(
            "Golf Model database restored",
            f"Restored from {os.path.basename(backup_path)}. Boards will rebuild from Data Golf.",
        )
    return report
