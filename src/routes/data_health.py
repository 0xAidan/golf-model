"""Data platform health API."""

import asyncio

from fastapi import APIRouter, Query

from src import cached_health

router = APIRouter(tags=["data-health"])
_refreshing_years: set[int] = set()


def _schedule_refresh(year: int) -> bool:
    if year in _refreshing_years:
        return False
    _refreshing_years.add(year)
    task = asyncio.create_task(asyncio.to_thread(cached_health.refresh_data_health_cache, year))
    task.add_done_callback(lambda _task: _refreshing_years.discard(year))
    return True


def _unavailable_report(year: int) -> dict:
    return {
        "ok": False,
        "status": "unknown",
        "summary": "Data-health audit has not completed yet.",
        "year": year,
        "retention_classifications": {},
        "latest_backup": None,
        "archive_stats": {},
        "investigate_counts": {},
        "research_output": {},
    }


@router.get("/api/data-health")
async def get_data_health(year: int = Query(2026, ge=2020, le=2100)):
    """Return the last completed data-health audit without doing a full scan."""
    cached = cached_health.read_cached_data_health(year)
    if cached is None:
        _schedule_refresh(year)
        return {
            **_unavailable_report(year),
            "generated_at": None,
            "stale": True,
            "ttl_seconds": 6 * 60 * 60,
            "refreshing": True,
        }

    if cached["stale"]:
        _schedule_refresh(year)
    return {
        **cached["report"],
        "generated_at": cached["generated_at"],
        "stale": cached["stale"],
        "ttl_seconds": cached["ttl_seconds"],
        "refreshing": year in _refreshing_years,
    }
