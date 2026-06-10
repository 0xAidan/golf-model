"""Eval & validity platform API (engine-scale Wave 3)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.db import ensure_initialized
from src.eval_aggregates import track_comparison

router = APIRouter(tags=["eval"])


@router.get("/api/eval/track-comparison")
async def get_track_comparison(
    window: str = Query("30d", pattern="^(30d|90d|season)$"),
    market: str | None = Query(None),
    book: str | None = Query(None),
):
    """Champion (cockpit) vs challenger (lab) live-graded metrics + pick overlap."""
    ensure_initialized()
    window_days = {"30d": 30, "90d": 90, "season": 365}[window]
    return {"window": window, **track_comparison(window_days=window_days, market=market, book=book)}
