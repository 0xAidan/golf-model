"""Tests for live-refresh watchdog idle heartbeat detection and ordering."""

from __future__ import annotations

from unittest.mock import patch

from scripts.live_refresh_watchdog import evaluate, main


def test_watchdog_restarts_idle_worker_with_stale_heartbeat():
    with patch("scripts.live_refresh_watchdog.read_heartbeat", return_value={"running": True, "refresh_state": "idle"}):
        with patch("scripts.live_refresh_watchdog.heartbeat_age_seconds", return_value=1200):
            with patch("scripts.live_refresh_watchdog._snapshot_age_seconds", return_value=100):
                result = evaluate(heartbeat_stale_seconds=900, snapshot_stale_seconds=999_999)
    assert result["restart"] is True
    assert any("idle" in reason for reason in result["reasons"])


def test_watchdog_restart_runs_before_grading_discrepancy_exit():
    with patch("scripts.live_refresh_watchdog.evaluate") as evaluate_mock:
        evaluate_mock.return_value = {
            "restart": True,
            "reasons": ["worker heartbeat stale (1200s > 900s) while idle"],
            "heartbeat_age_seconds": 1200,
            "snapshot_age_seconds": 100,
            "stale_after_seconds": 900,
            "heartbeat_running": True,
            "heartbeat_phase": None,
        }
        with patch("scripts.live_refresh_watchdog._restart_worker", return_value=0) as restart_mock:
            with patch(
                "scripts.live_refresh_watchdog._run_grading_sweep",
                return_value=({"ok": False}, 1),
            ) as grading_mock:
                with patch("sys.argv", ["live_refresh_watchdog.py", "--restart", "--ensure-grading"]):
                    exit_code = main()

    restart_mock.assert_called_once()
    grading_mock.assert_called_once()
    assert exit_code == 0


def test_watchdog_grading_failure_exits_when_no_restart_needed():
    with patch(
        "scripts.live_refresh_watchdog.evaluate",
        return_value={
            "restart": False,
            "reasons": [],
            "heartbeat_age_seconds": 30,
            "snapshot_age_seconds": 30,
            "stale_after_seconds": 900,
            "heartbeat_running": True,
            "heartbeat_phase": None,
        },
    ):
        with patch("scripts.live_refresh_watchdog._restart_worker") as restart_mock:
            with patch(
                "scripts.live_refresh_watchdog._run_grading_sweep",
                return_value=({"ok": False}, 1),
            ):
                with patch("sys.argv", ["live_refresh_watchdog.py", "--ensure-grading"]):
                    exit_code = main()

    restart_mock.assert_not_called()
    assert exit_code == 1


def test_watchdog_would_restart_exit_code_without_restart_flag():
    with patch(
        "scripts.live_refresh_watchdog.evaluate",
        return_value={
            "restart": True,
            "reasons": ["snapshot stale (5000s > 2700s)"],
            "heartbeat_age_seconds": 30,
            "snapshot_age_seconds": 5000,
            "stale_after_seconds": 900,
            "heartbeat_running": True,
            "heartbeat_phase": None,
        },
    ):
        with patch("scripts.live_refresh_watchdog._restart_worker") as restart_mock:
            with patch("sys.argv", ["live_refresh_watchdog.py"]):
                exit_code = main()

    restart_mock.assert_not_called()
    assert exit_code == 2
