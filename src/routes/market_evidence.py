"""Additive read-only reporting; independent of database initialization/models."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from src.market_evidence import build_market_evidence

router = APIRouter(tags=["market-evidence"])


@router.get("/api/market-evidence")
def market_evidence(
    lane: Literal["dashboard", "lab", "all"] = "dashboard",
    season: int | None = Query(None, ge=2000, le=2100),
) -> dict:
    """Descriptive evidence only; no recomputation or writes to historical stores."""
    return build_market_evidence(lane=lane, season=season)
