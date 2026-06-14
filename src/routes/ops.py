"""Ops health API route (extracted from app.py — engine-scale Wave 4 decomposition).

Behavior-preserving extraction: response shape is byte-identical to the inline route.
First step of the incremental app.py -> src/routes/ decomposition (H).
"""

import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["ops"])

_HEARTBEAT_STALE_SECONDS = 900


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
    from src.disk_guard import disk_usage_summary
    from src.runtime_paths import detect_split_brain, get_data_dir, get_runtime_identity, read_heartbeat
    from backtester.dashboard_runtime import get_live_refresh_status, read_snapshot
    from src.runtime_health import recent_strategy_config_errors
    from src.live_refresh_health import detect_worker_wedged, restart_live_refresh_worker, snapshot_stale_after_seconds

    ensure_initialized()
    identity = get_runtime_identity()
    heartbeat = read_heartbeat()
    split = detect_split_brain(heartbeat=heartbeat)
    snapshot = read_snapshot()
    status = get_live_refresh_status()
    disk = disk_usage_summary(str(get_data_dir()))
    generated_at = snapshot.get("generated_at") if isinstance(snapshot, dict) else None
    strategy_config_errors = recent_strategy_config_errors()
    snapshot_age_seconds = status.get("snapshot_age_seconds")
    stale_after_seconds = _snapshot_stale_after_seconds()
    heartbeat_age_seconds = split.get("heartbeat_age_seconds")
    heartbeat_running = bool((heartbeat or {}).get("running"))
    wedged = detect_worker_wedged(
        snapshot_age_seconds=snapshot_age_seconds,
        stale_after_seconds=stale_after_seconds,
        heartbeat=heartbeat,
    )

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
    elif wedged.get("wedged"):
        ok = False
        summary = "worker_wedged"
    elif disk.get("ok") and disk.get("status") == "critical":
        ok = False
        summary = "disk_critical"
    # Non-fatal but trust-relevant: a corrupt configured strategy silently fell back to
    # default. Keep ok=True (the system still serves a safe strategy) but surface it.
    if strategy_config_errors and summary == "healthy":
        summary = "strategy_config_fallback"
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
        "live_refresh": {
            "running": bool(status.get("running")),
            "refresh_state": (status.get("progress") or {}).get("refresh_state"),
            "phase": status.get("phase"),
            "last_error": status.get("last_error"),
            "snapshot_generated_at": generated_at,
            "snapshot_age_seconds": snapshot_age_seconds,
            "stale_after_seconds": stale_after_seconds,
            "worker_wedged": wedged,
        },
        "disk": disk,
    }


@router.post("/api/ops/remediate-live-refresh")
async def remediate_live_refresh():
    """Restart wedged worker and optionally run one guarded snapshot cycle."""
    from src.db import ensure_initialized
    from src.runtime_paths import get_runtime_identity, read_heartbeat
    from backtester.dashboard_runtime import generate_snapshot_once, get_live_refresh_status, read_snapshot
    from src.autoresearch_settings import get_settings
    from src.live_refresh_health import (
        detect_worker_wedged,
        restart_live_refresh_worker,
        snapshot_stale_after_seconds,
    )

    ensure_initialized()
    identity = get_runtime_identity()
    if not identity.get("production"):
        return JSONResponse(
            status_code=403,
            content={"ok": False, "reason": "Remediation is only available on production hosts."},
        )

    settings = (get_settings().get("live_refresh") or {})
    tour = str(settings.get("tour", "pga"))
    stale_after = snapshot_stale_after_seconds()
    status = get_live_refresh_status()
    snapshot_age = status.get("snapshot_age_seconds")
    heartbeat = read_heartbeat()
    wedged = detect_worker_wedged(
        snapshot_age_seconds=snapshot_age,
        stale_after_seconds=stale_after,
        heartbeat=heartbeat,
    )

    actions: list[dict] = []
    if wedged.get("wedged") or (snapshot_age is not None and snapshot_age > stale_after):
        restart_result = restart_live_refresh_worker(reason="; ".join(wedged.get("reasons") or []))
        actions.append({"action": "restart_worker", **restart_result})
        if not restart_result.get("ok"):
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "remediation": "restart_failed",
                    "actions": actions,
                    "wedged": wedged,
                },
            )
        for _ in range(18):
            await asyncio.sleep(5)
            status = get_live_refresh_status()
            snapshot_age = status.get("snapshot_age_seconds")
            if snapshot_age is not None and snapshot_age <= stale_after:
                break

    status = get_live_refresh_status()
    snapshot_age = status.get("snapshot_age_seconds")
    if snapshot_age is not None and snapshot_age > stale_after:
        try:
            snapshot = await asyncio.wait_for(
                asyncio.to_thread(generate_snapshot_once, tour=tour),
                timeout=120.0,
            )
            actions.append(
                {
                    "action": "emergency_snapshot",
                    "ok": bool(snapshot),
                    "generated_at": snapshot.get("generated_at") if isinstance(snapshot, dict) else None,
                }
            )
        except Exception as exc:
            actions.append({"action": "emergency_snapshot", "ok": False, "error": str(exc)})

    snapshot = read_snapshot()
    generated_at = snapshot.get("generated_at") if isinstance(snapshot, dict) else None
    status = get_live_refresh_status()
    snapshot_age = status.get("snapshot_age_seconds")
    recovered = snapshot_age is not None and snapshot_age <= stale_after
    return {
        "ok": recovered,
        "remediation": "recovered" if recovered else "still_stale",
        "snapshot_age_seconds": snapshot_age,
        "stale_after_seconds": stale_after,
        "snapshot_generated_at": generated_at,
        "actions": actions,
        "wedged": detect_worker_wedged(
            snapshot_age_seconds=snapshot_age,
            stale_after_seconds=stale_after,
        ),
    }
