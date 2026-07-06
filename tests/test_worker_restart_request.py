"""Tests for file-based worker restart requests."""

from __future__ import annotations

from scripts.live_refresh_watchdog import main
from src.worker_restart import (
    acknowledge_worker_restart_request,
    read_worker_restart_request,
    request_worker_restart,
)


def test_worker_restart_request_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("GOLF_DATA_DIR", str(tmp_path))
    payload = request_worker_restart(requested_by="test")
    assert read_worker_restart_request()["request_id"] == payload["request_id"]
    acknowledge_worker_restart_request(payload["request_id"])
    assert read_worker_restart_request() is None


def test_watchdog_honors_restart_request(monkeypatch):
    monkeypatch.setattr(
        "src.worker_restart.read_worker_restart_request",
        lambda: {
            "request_id": "req-1",
            "requested_at": "2099-01-01T00:00:00+00:00",
            "requested_by": "api",
            "status": "pending",
        },
    )
    monkeypatch.setattr(
        "scripts.live_refresh_watchdog.evaluate",
        lambda **kwargs: {
            "restart": False,
            "reasons": [],
            "heartbeat_age_seconds": 10,
            "snapshot_age_seconds": 10,
            "stale_after_seconds": 900,
            "heartbeat_running": True,
            "heartbeat_phase": None,
        },
    )
    monkeypatch.setattr("scripts.live_refresh_watchdog._restart_worker", lambda: 0)
    acknowledged: list[str] = []

    def _ack(request_id):
        acknowledged.append(str(request_id))

    monkeypatch.setattr("src.worker_restart.acknowledge_worker_restart_request", _ack)
    monkeypatch.setattr("sys.argv", ["live_refresh_watchdog.py", "--restart"])

    exit_code = main()
    assert exit_code == 0
    assert acknowledged == ["req-1"]
