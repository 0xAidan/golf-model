"""Concurrency guarantees for lightweight API endpoints."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone

import httpx
import pytest


pytestmark = pytest.mark.anyio


def _fresh_ops_cache() -> dict:
    return {
        "report": {"grading": {"status": "ok"}, "tracks": {"active": {}}},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stale": False,
        "ttl_seconds": 900,
    }


@pytest.mark.anyio
async def test_lightweight_routes_respond_while_data_health_refresh_blocks(monkeypatch) -> None:
    import app as app_module
    from src import cached_health

    refresh_started = threading.Event()
    release_refresh = threading.Event()

    def slow_refresh(year: int) -> dict:
        refresh_started.set()
        release_refresh.wait(timeout=5)
        return {"status": "green", "year": year}

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(cached_health, "refresh_data_health_cache", slow_refresh)
    monkeypatch.setattr(cached_health, "read_cached_data_health", lambda year: None)
    monkeypatch.setattr(cached_health, "read_cached_ops_grading_health", _fresh_ops_cache)

    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        queued = await client.get("/api/data-health?year=2026")
        assert queued.status_code == 200
        assert await asyncio.to_thread(refresh_started.wait, 1)

        started_at = time.perf_counter()
        home, version, refresh_status = await asyncio.gather(
            client.get("/"),
            client.get("/api/version"),
            client.get("/api/live-refresh/status"),
        )
        elapsed = time.perf_counter() - started_at

    release_refresh.set()
    assert elapsed < 0.5
    assert home.status_code in {200, 503}
    assert version.json() == {"ok": True, "service": "golf-model"}
    assert refresh_status.status_code == 200


@pytest.mark.anyio
async def test_ops_health_returns_from_cache_without_waiting_for_reconciliation(monkeypatch) -> None:
    import app as app_module
    from src import cached_health

    release_reconciliation = threading.Event()

    def slow_reconciliation(**_kwargs):
        release_reconciliation.wait(timeout=5)
        return {"status": "ok"}

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(cached_health, "read_cached_ops_grading_health", _fresh_ops_cache)
    monkeypatch.setattr("src.grading_reconciliation.reconcile_grading", slow_reconciliation)

    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started_at = time.perf_counter()
        response = await client.get("/api/ops/health")
        elapsed = time.perf_counter() - started_at

    release_reconciliation.set()
    assert elapsed < 0.5
    assert response.status_code == 200
    assert response.json()["grading"]["status"] == "ok"


@pytest.mark.anyio
async def test_past_events_does_not_block_event_loop_on_rate_limit(monkeypatch) -> None:
    """A 429 cooldown must not freeze Refresh / status while past-events runs."""
    import app as app_module
    from src import datagolf

    def sleepy_network(*_args, **_kwargs):
        time.sleep(5)
        raise AssertionError("past-events must not call Data Golf")

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        app_module,
        "list_completed_snapshot_events",
        lambda limit=40, exclude_event_ids=None: [{"event_id": "32", "event_name": "RBC Canadian Open"}],
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: {"upcoming_tournament": {"source_event_id": "26"}},
    )
    monkeypatch.setattr(datagolf, "_call_api", sleepy_network)
    datagolf.REQUEST_MANAGER.cache.clear()
    datagolf.REQUEST_MANAGER.request_times.clear()
    datagolf.REQUEST_MANAGER.blocked_until = time.time() + 300

    try:
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started_at = time.perf_counter()
            past, home, status = await asyncio.gather(
                client.get("/api/live-refresh/past-events"),
                client.get("/"),
                client.get("/api/live-refresh/status"),
            )
            elapsed = time.perf_counter() - started_at
    finally:
        datagolf.REQUEST_MANAGER.cache.clear()
        datagolf.REQUEST_MANAGER.request_times.clear()
        datagolf.REQUEST_MANAGER.blocked_until = 0.0

    assert elapsed < 0.5
    assert past.status_code == 200
    assert home.status_code in {200, 503}
    assert status.status_code == 200
