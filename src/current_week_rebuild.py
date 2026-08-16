"""Rebuild current-week boards after a database restore.

A restored backup can be days old. Live boards come back from Data Golf via
the live-refresh worker; completed-event grading is swept so Results is not
stuck on the backup's last graded week.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.atomic_io import atomic_write_json
from src.datagolf import get_current_event_info
from src.runtime_paths import get_heartbeat_path, get_runtime_identity

logger = logging.getLogger("golf.current_week_rebuild")


def write_rebuild_heartbeat(
    *,
    phase: str,
    last_error: str | None = None,
    target_event_id: str | None = None,
    target_event_name: str | None = None,
) -> None:
    payload = {
        **get_runtime_identity(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "running": False,
        "phase": phase,
        "refresh_state": "rebuilding" if phase != "ok" else "idle",
        "last_error": last_error,
        "target_event_id": target_event_id,
        "target_event_name": target_event_name,
    }
    try:
        atomic_write_json(get_heartbeat_path(), payload)
    except OSError as exc:
        logger.warning("Failed to write rebuild heartbeat: %s", exc)


def queue_live_refresh(*, requested_by: str = "auto_recover") -> dict[str, Any]:
    from backtester.dashboard_runtime import request_manual_refresh

    return request_manual_refresh(requested_by=requested_by)


def grade_completed_events(*, year: int | None = None) -> dict[str, Any]:
    from src.event_pick_freeze import ensure_all_completed_pga_events_graded

    return ensure_all_completed_pga_events_graded(year=year)


def current_event_target() -> dict[str, Any]:
    """Record Data Golf's current event so the UI can stay in 'rebuilding' until it matches."""
    info = get_current_event_info("pga") or {}
    event_id = str(info.get("event_id") or "")
    if not event_id:
        return {"ok": False, "skipped": True, "reason": "no current event from Data Golf"}
    return {
        "ok": True,
        "event_id": event_id,
        "event_name": info.get("event_name") or info.get("name"),
        "course": info.get("course") or info.get("course_name"),
    }


def rebuild_current_week(*, year: int | None = None) -> dict[str, Any]:
    """Queue a live-refresh tick and grade completed events. Best-effort."""
    report: dict[str, Any] = {
        "ok": True,
        "queued_refresh": None,
        "current_event": None,
        "grading": None,
        "errors": [],
    }
    target = {}
    try:
        target = current_event_target()
        report["current_event"] = target
    except Exception as exc:
        report["errors"].append(f"current_event_target: {exc}")
        logger.warning("Failed to resolve current Data Golf event after restore: %s", exc)

    write_rebuild_heartbeat(
        phase="rebuilding_current_week",
        target_event_id=str(target.get("event_id") or "") or None,
        target_event_name=str(target.get("event_name") or "") or None,
    )

    try:
        report["queued_refresh"] = queue_live_refresh()
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"queue_live_refresh: {exc}")
        logger.warning("Failed to queue live refresh after restore: %s", exc)

    try:
        report["grading"] = grade_completed_events(year=year)
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"grade_completed_events: {exc}")
        logger.warning("Failed to grade completed events after restore: %s", exc)

    if report["ok"]:
        write_rebuild_heartbeat(
            phase="rebuild_queued",
            target_event_id=str(target.get("event_id") or "") or None,
            target_event_name=str(target.get("event_name") or "") or None,
        )
    else:
        write_rebuild_heartbeat(
            phase="rebuild_failed",
            last_error="; ".join(report["errors"]),
            target_event_id=str(target.get("event_id") or "") or None,
            target_event_name=str(target.get("event_name") or "") or None,
        )
    return report
