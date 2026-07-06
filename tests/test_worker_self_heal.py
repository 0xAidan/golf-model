"""Tests for live-refresh worker self-healing when the runtime thread dies."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workers import live_refresh_worker as worker


def test_runtime_thread_alive_false_when_no_thread():
    from backtester import dashboard_runtime as runtime

    original = runtime._thread
    runtime._thread = None
    try:
        assert runtime.runtime_thread_alive() is False
    finally:
        runtime._thread = original


def test_runtime_thread_alive_true_for_running_thread():
    import threading
    from backtester import dashboard_runtime as runtime

    started = threading.Event()
    finished = threading.Event()

    def _target() -> None:
        started.set()
        finished.wait(timeout=2.0)

    thread = threading.Thread(target=_target, name="test-runtime-thread")
    original = runtime._thread
    runtime._thread = thread
    thread.start()
    started.wait(timeout=2.0)
    try:
        assert runtime.runtime_thread_alive() is True
    finally:
        finished.set()
        thread.join(timeout=2.0)
        runtime._thread = original


def test_write_heartbeat_survives_oserror(monkeypatch, tmp_path):
    from backtester import dashboard_runtime as runtime

    def _raise_oserror(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(runtime, "atomic_write_json", _raise_oserror)
    runtime._write_heartbeat()  # must not raise


def test_worker_main_exits_when_runtime_thread_dies(monkeypatch):
    monkeypatch.setattr(worker, "load_dotenv", None)
    monkeypatch.setattr(worker, "ensure_initialized", lambda: None)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: {"live_refresh": {"tour": "pga"}},
    )
    monkeypatch.setattr(worker, "_clear_stale_pidfile", lambda _path: None)
    monkeypatch.setattr(worker, "_write_pidfile", lambda _path: None)
    monkeypatch.setattr(worker, "_remove_pidfile", lambda _path: None)
    monkeypatch.setattr(worker, "start_live_refresh", lambda tour="pga": {"running": True})
    monkeypatch.setattr(worker, "stop_live_refresh", lambda: {"running": False})

    alive_calls = {"count": 0}

    def _runtime_thread_alive() -> bool:
        alive_calls["count"] += 1
        return alive_calls["count"] < 2

    monkeypatch.setattr(worker, "runtime_thread_alive", _runtime_thread_alive)

    assert worker.main() == 1


@pytest.mark.parametrize("signum", [2, 15])
def test_worker_main_clean_shutdown_does_not_treat_stopped_thread_as_failure(monkeypatch, signum):
    monkeypatch.setattr(worker, "load_dotenv", None)
    monkeypatch.setattr(worker, "ensure_initialized", lambda: None)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: {"live_refresh": {"tour": "pga"}},
    )
    monkeypatch.setattr(worker, "_clear_stale_pidfile", lambda _path: None)
    monkeypatch.setattr(worker, "_write_pidfile", lambda _path: None)
    monkeypatch.setattr(worker, "_remove_pidfile", lambda _path: None)
    monkeypatch.setattr(worker, "start_live_refresh", lambda tour="pga": {"running": True})
    stop_called = {"value": False}

    def _stop_live_refresh():
        stop_called["value"] = True
        return {"running": False}

    monkeypatch.setattr(worker, "stop_live_refresh", _stop_live_refresh)

    sleeps = {"count": 0}

    def _sleep(_seconds):
        sleeps["count"] += 1
        if sleeps["count"] >= 2:
            worker._shutdown = True

    monkeypatch.setattr(worker.time, "sleep", _sleep)
    monkeypatch.setattr(worker, "runtime_thread_alive", lambda: True)

    with patch.object(worker.signal, "signal"):
        worker._shutdown = False
        assert worker.main() == 0
    assert stop_called["value"] is True
