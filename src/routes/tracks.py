"""Model-track registry API routes (engine-scale Wave 1, read-only).

Exposes the two model-track config slots (dashboard champion, lab challenger) with a
stable ``config_hash`` for provenance. The promotion/rollback workflow is added in a
later wave; this surface is read-only.
"""

from fastapi import APIRouter

from src.db import ensure_initialized
from src import track_registry

router = APIRouter(tags=["tracks"])


@router.get("/api/tracks")
async def get_tracks():
    """Both active track config slots + effective hashes + recent activation history."""
    ensure_initialized()
    return track_registry.list_tracks()
