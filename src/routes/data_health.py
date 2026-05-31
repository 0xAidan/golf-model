"""Data platform health API."""

from fastapi import APIRouter, Query

from src.data_health import build_data_health_report
from src.data_views import ensure_analytics_views
from src.db import ensure_initialized

router = APIRouter(tags=["data-health"])


@router.get("/api/data-health")
async def get_data_health(year: int = Query(2026, ge=2020, le=2100)):
    """Coverage, storage breakdown, gaps, and autoresearch preflight."""
    ensure_initialized()
    ensure_analytics_views()
    return build_data_health_report(year=year)
