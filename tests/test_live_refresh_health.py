"""Tests for live-refresh wedged-worker detection."""

from __future__ import annotations

from src.live_refresh_health import detect_worker_wedged


def test_detect_worker_wedged_fresh_heartbeat_stale_snapshot():
    wedged = detect_worker_wedged(
        snapshot_age_seconds=50_000,
        stale_after_seconds=3_720,
        heartbeat={
            "running": True,
            "phase": "recompute",
            "refresh_state": "running",
            "updated_at": "2099-01-01T00:00:00+00:00",
        },
    )
    assert wedged["wedged"] is True
    assert any("snapshot stale" in reason for reason in wedged["reasons"])


def test_detect_worker_wedged_not_wedged_when_snapshot_fresh():
    wedged = detect_worker_wedged(
        snapshot_age_seconds=120,
        stale_after_seconds=3_720,
        heartbeat={
            "running": True,
            "phase": "recompute",
            "refresh_state": "running",
            "updated_at": "2099-01-01T00:00:00+00:00",
        },
    )
    assert wedged["wedged"] is False


def test_detect_worker_wedged_when_worker_not_running_and_snapshot_stale():
    wedged = detect_worker_wedged(
        snapshot_age_seconds=10_000,
        stale_after_seconds=3_720,
        heartbeat={"running": False, "phase": None, "refresh_state": "idle"},
    )
    assert wedged["wedged"] is True
