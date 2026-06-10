"""Model-track registry API routes (engine-scale Wave 1, read-only).

Exposes the two model-track config slots (dashboard champion, lab challenger) with a
stable ``config_hash`` for provenance. The promotion/rollback workflow is added in a
later wave; this surface is read-only.
"""

from fastapi import APIRouter, Body, HTTPException

from src import config
from src.db import ensure_initialized
from src import track_registry

router = APIRouter(tags=["tracks"])


@router.get("/api/tracks")
async def get_tracks():
    """Both active track config slots + effective hashes + recent activation history."""
    ensure_initialized()
    return track_registry.list_tracks()


@router.get("/api/tracks/promotion-readiness")
async def get_promotion_readiness():
    """Gate-by-gate readiness for promoting the challenger into the dashboard slot."""
    ensure_initialized()
    return {
        "promotion_enabled": config.TRACK_PROMOTION_ENABLED,
        **track_registry.evaluate_promotion_readiness(),
    }


@router.post("/api/tracks/promote")
async def promote_track(payload: dict = Body(default_factory=dict)):
    """Promote a track (default lab) into the dashboard slot. Flag-gated + gate-checked.

    Disabled unless TRACK_PROMOTION_ENABLED so promotion can't fire accidentally during
    soak. Mutating endpoint — also covered by the DASHBOARD_API_KEY middleware when set.
    """
    ensure_initialized()
    if not config.TRACK_PROMOTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Track promotion is disabled (set TRACK_PROMOTION_ENABLED=1 after soak).",
        )
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A promotion reason is required (audit trail).")
    from_track = str(payload.get("from_track") or "lab").strip().lower()
    result = track_registry.promote_track(
        from_track=from_track,
        reason=reason,
        activated_by=str(payload.get("activated_by") or "operator"),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/api/tracks/rollback")
async def rollback_track(payload: dict = Body(default_factory=dict)):
    """Roll the dashboard slot back to its parent config (one action)."""
    ensure_initialized()
    if not config.TRACK_PROMOTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Track promotion/rollback is disabled (set TRACK_PROMOTION_ENABLED=1).",
        )
    result = track_registry.rollback_track(str(payload.get("track") or "dashboard").strip().lower())
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result
