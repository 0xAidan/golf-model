"""Cheap SQLite health probes and corrupt-error classification.

Do not run ``PRAGMA quick_check`` on the live multi-GB file from a timer.
A ``SELECT`` against ``sqlite_master`` is enough to detect the Aug 16
``database disk image is malformed`` failure without hanging the box.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from src.runtime_paths import get_db_path, get_snapshot_path, read_heartbeat

CORRUPT_MARKERS = (
    "malformed",
    "file is not a database",
    "not a database",
    "database disk image is malformed",
)

BUSY_MARKERS = (
    "database is locked",
    "database is busy",
    "locked",
)


class DatabaseCorruptError(sqlite3.DatabaseError):
    """Raised when SQLite reports a malformed / not-a-database file."""


def is_corrupt_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in CORRUPT_MARKERS)


def is_busy_error(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        return any(marker in text for marker in BUSY_MARKERS)
    return False


def classify_sqlite_error(exc: BaseException) -> str:
    if is_corrupt_error(exc):
        return "corrupt"
    if isinstance(exc, TimeoutError) or "timeout" in str(exc).lower():
        return "timeout"
    if is_busy_error(exc):
        return "busy"
    return "error"


def probe_sqlite_file(path: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Smoke-open ``path`` and run ``SELECT COUNT(*) FROM sqlite_master``."""
    result: dict[str, Any] = {
        "ok": False,
        "state": "missing",
        "path": path,
        "error": None,
        "table_count": None,
    }
    try:
        if not os.path.isfile(path):
            result["state"] = "missing"
            result["error"] = "database file not found"
            return result
    except OSError as exc:
        result["state"] = "error"
        result["error"] = str(exc)
        return result

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout_seconds)
        row = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        result["ok"] = True
        result["state"] = "ok"
        result["table_count"] = int(row[0]) if row else 0
        return result
    except Exception as exc:
        result["state"] = classify_sqlite_error(exc)
        result["error"] = str(exc)
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass


def probe_live_database(*, timeout_seconds: float = 5.0) -> dict[str, Any]:
    return probe_sqlite_file(str(get_db_path()), timeout_seconds=timeout_seconds)


def _read_snapshot_event_id() -> str:
    path = get_snapshot_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    live = payload.get("live_tournament") or {}
    upcoming = payload.get("upcoming_tournament") or {}
    context = payload.get("event_context") or {}
    return str(
        live.get("event_id")
        or upcoming.get("event_id")
        or context.get("event_id")
        or ""
    )


def live_db_status_fields(*, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Fields safe to attach to snapshot/ops JSON when SQLite may be dead."""
    probe = probe_live_database(timeout_seconds=timeout_seconds)
    heartbeat = read_heartbeat() or {}
    phase = str(heartbeat.get("phase") or "")
    target_event_id = str(heartbeat.get("target_event_id") or "")
    snapshot_event_id = _read_snapshot_event_id()
    rebuild_state = "ok"
    if phase in {"db_malformed", "rebuilding_current_week", "rebuild_queued", "rebuild_failed"}:
        rebuild_state = "rebuilding"
    elif target_event_id and snapshot_event_id and target_event_id != snapshot_event_id:
        rebuild_state = "rebuilding"
    elif not probe.get("ok"):
        rebuild_state = "unavailable"
    return {
        "db_ok": bool(probe.get("ok")),
        "db_state": probe.get("state"),
        "rebuild_state": rebuild_state,
        "db_error": probe.get("error"),
        "target_event_id": target_event_id or None,
        "snapshot_event_id": snapshot_event_id or None,
    }
