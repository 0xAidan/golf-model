"""Ops health API route (extracted from app.py — engine-scale Wave 4 decomposition).

Behavior-preserving extraction: response shape is byte-identical to the inline route.
First step of the incremental app.py -> src/routes/ decomposition (H).
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["ops"])

_HEARTBEAT_STALE_SECONDS = 900


class WorkerRestartRequest(BaseModel):
    requested_by: str = Field(default="api")


def _snapshot_stale_after_seconds() -> int:
    from src.autoresearch_settings import get_settings
    from src.live_refresh_policy import resolve_cadence

    settings = get_settings().get("live_refresh") or {}
    cadence = resolve_cadence(settings)
    return max(900, int(cadence.recompute_seconds) + 120)


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

    # Track-registry state (active config hashes per track) for incident triage without SSH.
    track_state: dict = {}
    try:
        from src import track_registry

        listing = track_registry.list_tracks(history_limit=1)
        track_state = {
            "active": {
                t: {"config_hash": row.get("config_hash"), "model_variant": row.get("model_variant")}
                for t, row in (listing.get("tracks") or {}).items()
            },
            "effective_config_hash": listing.get("effective_config_hash"),
            "last_activation": (listing.get("history") or [{}])[0].get("activated_at"),
        }
    except Exception:
        track_state = {"error": "unavailable"}
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

    grading_health: dict = {"status": "unknown"}
    try:
        from src.grading_reconciliation import reconcile_grading

        reconciliation = reconcile_grading(limit_events=5)
        grading_health = {
            "status": reconciliation.get("status"),
            "events_with_ungraded_positive_ev": reconciliation.get("events_with_ungraded_positive_ev"),
            "orphan_outcomes": reconciliation.get("orphan_outcomes"),
            "last_auto_grade_at": status.get("last_auto_grade_at"),
            "last_auto_grade_status": status.get("last_auto_grade_status"),
        }
        if reconciliation.get("status") == "discrepancies" and ok:
            summary = "grading_discrepancies"
    except Exception as exc:
        grading_health = {"status": "error", "message": str(exc)}

    if disk.get("guard_state") == "hard":
        summary = "disk_floor_breached"

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
        "disk": disk,
        "worker_restart_request": worker_restart_request,
        "live_refresh": {
            "running": bool(status.get("running")),
            "refresh_state": (status.get("progress") or {}).get("refresh_state"),
            "phase": status.get("phase"),
            "last_error": status.get("last_error"),
            "snapshot_generated_at": generated_at,
            "snapshot_age_seconds": snapshot_age_seconds,
            "stale_after_seconds": stale_after_seconds,
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
