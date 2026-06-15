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
