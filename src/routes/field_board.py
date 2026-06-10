"""Field-complete player board API (engine-scale Wave 2).

`GET /api/players/field-board` returns one response for the whole tournament field
(rank on both tracks, composite components, pick involvement, best-effort SG splits),
built single-pass from the current live-refresh snapshot and cached per snapshot_id.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Query

from src.db import ensure_initialized
from src.field_board import build_field_board, load_sg_by_player

router = APIRouter(tags=["players"])

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "value": None}


@router.get("/api/players/field-board")
async def get_field_board(section: str = Query("auto", pattern="^(auto|live|upcoming)$")):
    """Field-wide player intelligence for the current event (cached per snapshot_id)."""
    ensure_initialized()
    from backtester.dashboard_runtime import read_snapshot

    snapshot = read_snapshot() or {}
    snapshot_id = snapshot.get("snapshot_id") or snapshot.get("generated_at") or ""
    cache_key = f"{snapshot_id}:{section}"

    with _cache_lock:
        if _cache["key"] == cache_key and _cache["value"] is not None:
            return _cache["value"]

    # Resolve the active section's tournament id for SG enrichment.
    board_preview = build_field_board(snapshot, section=section)
    sg_by_player = load_sg_by_player(board_preview.get("tournament_id"))
    board = build_field_board(snapshot, section=section, sg_by_player=sg_by_player)

    with _cache_lock:
        _cache["key"] = cache_key
        _cache["value"] = board
    return board
