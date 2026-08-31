"""Ops health API route (extracted from app.py — engine-scale Wave 4 decomposition).

Behavior-preserving extraction: response shape is byte-identical to the inline route.
First step of the incremental app.py -> src/routes/ decomposition (H).
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src import cached_health

router = APIRouter(tags=["ops"])

_HEARTBEAT_STALE_SECONDS = 900
_ops_grading_refresh_in_flight = False


class WorkerRestartRequest(BaseModel):
    requested_by: str = Field(default="api")


def _snapshot_stale_after_seconds() -> int:
    from src.autoresearch_settings import get_settings
    from src.live_refresh_policy import resolve_cadence

    settings = get_settings().get("live_refresh") or {}
    cadence = resolve_cadence(settings)
    return max(900, int(cadence.recompute_seconds) + 120)


@router.get("/api/version")
async def get_version():
    """Minimal liveness endpoint with no database or refresh dependencies."""
    return {"ok": True, "service": "golf-model"}


def _schedule_ops_grading_refresh() -> bool:
    global _ops_grading_refresh_in_flight
    if _ops_grading_refresh_in_flight:
        return False
    _ops_grading_refresh_in_flight = True

    task = asyncio.create_task(asyncio.to_thread(cached_health.refresh_ops_grading_cache))

    def _clear_refresh(_task: asyncio.Task) -> None:
        global _ops_grading_refresh_in_flight
        _ops_grading_refresh_in_flight = False

    task.add_done_callback(_clear_refresh)
    return True


@router.get("/api/ops/health")
async def get_ops_health():
    """Production identity, worker heartbeat, and split-brain diagnostics (non-secret)."""
    from src.db import ensure_initialized
    from src.disk_guard import get_disk_state
    from src.runtime_paths import detect_split_brain, get_app_root, get_runtime_identity, read_heartbeat
    from src.worker_restart import read_worker_restart_request
    from backtester.dashboard_runtime import get_live_refresh_status, read_snapshot
    from src.runtime_health import recent_strategy_config_errors

    ensure_initialized()
    from src.db import db_health_payload
    from src.db_integrity import read_integrity_state

    db_health = db_health_payload()
    integrity_state = read_integrity_state()
    identity = get_runtime_identity()
    heartbeat = read_heartbeat()
    split = detect_split_brain(heartbeat=heartbeat)
    snapshot = read_snapshot()
    status = get_live_refresh_status()
    generated_at = snapshot.get("generated_at") if isinstance(snapshot, dict) else None
    strategy_config_errors = recent_strategy_config_errors()
    snapshot_age_seconds = status.get("snapshot_age_seconds")
    stale_after_seconds = _snapshot_stale_after_seconds()
    heartbeat_age_seconds = split.get("heartbeat_age_seconds")
    heartbeat_running = bool((heartbeat or {}).get("running"))
    disk = get_disk_state(str(get_app_root()))
    worker_restart_request = read_worker_restart_request()

    ok = not split["split_brain_suspected"]
    summary = "healthy" if ok else "split_brain_suspected"
    if not heartbeat and identity.get("production"):
        ok = False
        summary = "worker_heartbeat_missing"
    elif (
        heartbeat_age_seconds is not None
        and heartbeat_age_seconds > _HEARTBEAT_STALE_SECONDS
        and heartbeat_running
    ):
        ok = False
        summary = "worker_heartbeat_stale"
    elif snapshot_age_seconds is not None and snapshot_age_seconds > stale_after_seconds:
        ok = False
        summary = "snapshot_stale"
    # Non-fatal but trust-relevant: a corrupt configured strategy silently fell back to
    # default. Keep ok=True (the system still serves a safe strategy) but surface it.
    if strategy_config_errors and summary == "healthy":
        summary = "strategy_config_fallback"

    cached_grading = cached_health.read_cached_ops_grading_health()
    grading_health: dict = {"status": "unknown"}
    track_state: dict = {"error": "unavailable"}
    grading_cache = {
        "generated_at": None,
        "stale": True,
        "ttl_seconds": 15 * 60,
    }
    if cached_grading is None:
        _schedule_ops_grading_refresh()
    else:
        report = cached_grading["report"]
        grading_health = dict(report.get("grading") or grading_health)
        track_state = dict(report.get("tracks") or track_state)
        grading_cache = {
            "generated_at": cached_grading["generated_at"],
            "stale": cached_grading["stale"],
            "ttl_seconds": cached_grading["ttl_seconds"],
        }
        if cached_grading["stale"]:
            _schedule_ops_grading_refresh()

    grading_health["last_auto_grade_at"] = status.get("last_auto_grade_at")
    grading_health["last_auto_grade_status"] = status.get("last_auto_grade_status")
    if grading_health.get("status") == "discrepancies" and ok:
        summary = "grading_discrepancies"

    if disk.get("guard_state") == "hard" or disk.get("state") == "hard":
        ok = False
        summary = "disk_floor_breached"

    db_unavailable = bool(db_health.get("unavailable") or integrity_state.get("restore_in_progress"))
    if db_unavailable:
        ok = False
        summary = "database_unavailable"

    return {
        "ok": ok,
        "summary": summary,
        "identity": identity,
        "heartbeat": heartbeat,
        "split_brain_suspected": split["split_brain_suspected"],
        "split_brain_reasons": split["reasons"],
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "strategy_config_errors": strategy_config_errors,
        "tracks": track_state,
        "grading": grading_health,
        "grading_cache": grading_cache,
        "disk": disk,
        "db": {
            "unavailable": db_unavailable,
            "reason": db_health.get("reason") or integrity_state.get("reason"),
            "restore_in_progress": bool(integrity_state.get("restore_in_progress")),
        },
        "db_unavailable": db_unavailable,
        "worker_restart_request": worker_restart_request,
        "live_refresh": {
            "running": bool(status.get("running")),
            "refresh_state": (status.get("progress") or {}).get("refresh_state"),
            "phase": status.get("phase"),
            "last_error": status.get("last_error"),
            "snapshot_generated_at": generated_at,
            "snapshot_age_seconds": snapshot_age_seconds,
            "stale_after_seconds": stale_after_seconds,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "last_auto_grade_at": status.get("last_auto_grade_at"),
            "last_auto_grade_status": status.get("last_auto_grade_status"),
        },
    }


@router.post("/api/ops/worker/restart")
async def post_worker_restart(payload: WorkerRestartRequest | None = None):
    """Queue a live-refresh worker restart for the next watchdog pass."""
    from src.worker_restart import request_worker_restart

    body = payload or WorkerRestartRequest()
    request = request_worker_restart(requested_by=body.requested_by)
    return {
        "ok": True,
        "status": "queued",
        "request": request,
        "message": "Worker restart queued for the next watchdog cycle (within ~5 minutes).",
    }
