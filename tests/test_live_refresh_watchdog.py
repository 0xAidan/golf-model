"""Tests for live-refresh watchdog idle heartbeat detection."""

from __future__ import annotations

from scripts.live_refresh_watchdog import evaluate


def test_watchdog_restarts_idle_worker_with_stale_heartbeat():
    result = evaluate(
        heartbeat_stale_seconds=900,
        snapshot_stale_seconds=999_999,
    )
    # Without monkeypatching read_heartbeat, result depends on live env — patch inline
    from unittest.mock import patch

    with patch("scripts.live_refresh_watchdog.read_heartbeat", return_value={"running": True, "refresh_state": "idle"}):
        with patch("scripts.live_refresh_watchdog.heartbeat_age_seconds", return_value=1200):
            with patch("scripts.live_refresh_watchdog._snapshot_age_seconds", return_value=100):
                result = evaluate(heartbeat_stale_seconds=900, snapshot_stale_seconds=999_999)
    assert result["restart"] is True
    assert any("idle" in reason for reason in result["reasons"])
