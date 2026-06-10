"""Ops health API route (extracted from app.py — engine-scale Wave 4 decomposition).

Behavior-preserving extraction: response shape is byte-identical to the inline route.
First step of the incremental app.py -> src/routes/ decomposition (H).
"""

from fastapi import APIRouter

router = APIRouter(tags=["ops"])


@router.get("/api/ops/health")
async def get_ops_health():
    """Production identity, worker heartbeat, and split-brain diagnostics (non-secret)."""
    from src.db import ensure_initialized
    from src.runtime_paths import detect_split_brain, get_runtime_identity, read_heartbeat
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
        "heartbeat_age_seconds": split["heartbeat_age_seconds"],
        "strategy_config_errors": strategy_config_errors,
        "tracks": track_state,
        "live_refresh": {
            "running": bool(status.get("running")),
            "refresh_state": (status.get("progress") or {}).get("refresh_state"),
            "phase": status.get("phase"),
            "last_error": status.get("last_error"),
            "snapshot_generated_at": generated_at,
            "snapshot_age_seconds": status.get("snapshot_age_seconds"),
        },
    }
