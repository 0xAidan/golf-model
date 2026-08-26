"""Tests for Data Golf schedule status helpers."""

from __future__ import annotations

from datetime import date

import pytest

from src import datagolf


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"status": "completed", "start_date": "2026-06-11"}, True),
        ({"status": "upcoming", "start_date": "2026-06-18"}, False),
        ({"status": "in_progress", "start_date": "2026-06-12"}, False),
        ({"end_date": "2026-01-01"}, True),
        ({"start_date": "2026-06-18", "end_date": "2026-06-22"}, False),
    ],
)
def test_is_schedule_event_completed(row, expected):
    assert datagolf.is_schedule_event_completed(row, today=date(2026, 6, 14)) is expected


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"status": "in_progress", "start_date": "2026-06-12"}, True),
        ({"status": "live", "start_date": "2026-06-12"}, True),
        ({"status": "upcoming", "start_date": "2026-06-18"}, False),
        ({"status": "completed", "start_date": "2026-06-11"}, False),
        (
            {"start_date": "2026-06-12", "end_date": "2026-06-16"},
            True,
        ),
    ],
)
def test_is_schedule_event_live(row, expected):
    assert datagolf.is_schedule_event_live(row, today=date(2026, 6, 14)) is expected


def test_get_latest_completed_event_info_uses_status_without_end_date(monkeypatch):
    schedule = [
        {
            "event_id": "26",
            "event_name": "U.S. Open",
            "status": "upcoming",
            "start_date": "2026-06-18",
        },
        {
            "event_id": "32",
            "event_name": "RBC Canadian Open",
            "status": "completed",
            "start_date": "2026-06-11",
        },
        {
            "event_id": "10",
            "event_name": "Older Event",
            "status": "completed",
            "start_date": "2026-05-01",
        },
    ]
    monkeypatch.setattr(datagolf, "_call_api", lambda endpoint, params=None: schedule)

    latest = datagolf.get_latest_completed_event_info(tour="pga", as_of=date(2026, 6, 14))

    assert latest is not None
    assert latest["event_id"] == "32"
    assert latest["event_name"] == "RBC Canadian Open"


def _reset_request_manager() -> None:
    datagolf.REQUEST_MANAGER.cache.clear()
    datagolf.REQUEST_MANAGER.request_times.clear()
    datagolf.REQUEST_MANAGER.blocked_until = 0.0


def test_fetch_schedule_allow_network_false_uses_cache_only(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("cache-only fetch_schedule must not call Data Golf")

    monkeypatch.setattr(datagolf, "_call_api", boom)
    _reset_request_manager()
    datagolf.REQUEST_MANAGER.set_cached(
        datagolf._cache_key("get-schedule", {"file_format": "json", "tour": "pga"}),
        [{"event_id": "26", "status": "upcoming"}],
        ttl_seconds=60,
    )

    try:
        rows = datagolf.fetch_schedule(tour="pga", upcoming_only=False, allow_network=False)
        assert rows == [{"event_id": "26", "status": "upcoming"}]
        assert datagolf.fetch_schedule(tour="pga", upcoming_only=True, allow_network=False) == []
    finally:
        _reset_request_manager()
