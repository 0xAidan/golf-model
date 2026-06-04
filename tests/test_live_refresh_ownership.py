"""Tests for single-owner coordination of the live refresh loop (defect Q10).

The systemd worker (`workers/live_refresh_worker.py`) is the authoritative owner
of the live-refresh loop. The FastAPI lifespan hook must:

1. Default to NOT starting an embedded loop.
2. Only start the embedded loop when ``LIVE_REFRESH_EMBEDDED_AUTOSTART=1`` AND
   no worker pidfile pointing to a live process exists.
3. Skip (with a WARNING log) when the env var is opted in but the worker is
   already running.
"""

from __future__ import annotations

import os
import subprocess

import pytest
from fastapi.testclient import TestClient


def _reset_autostart_env(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("LIVE_REFRESH_EMBEDDED_AUTOSTART", raising=False)
    else:
        monkeypatch.setenv("LIVE_REFRESH_EMBEDDED_AUTOSTART", value)


@pytest.fixture
def pidfile_path(tmp_path, monkeypatch):
    path = tmp_path / "golf_live_refresh.pid"
    monkeypatch.setenv("LIVE_REFRESH_PIDFILE", str(path))
    return path


@pytest.fixture
def patched_refresh(monkeypatch):
    """Stub the refresh runtime and settings so lifespan is safe to run."""
    calls = {"start": 0, "stop": 0, "last_tour": None}

    def fake_start(tour: str = "pga"):
        calls["start"] += 1
        calls["last_tour"] = tour
        return {"running": True}

    def fake_stop():
        calls["stop"] += 1
        return {"running": False}

    monkeypatch.setattr("backtester.dashboard_runtime.start_live_refresh", fake_start)
    monkeypatch.setattr("backtester.dashboard_runtime.stop_live_refresh", fake_stop)
    monkeypatch.setattr(
        "src.autoresearch_settings.get_settings",
        lambda: {"live_refresh": {"enabled": True, "autostart": True, "tour": "pga"}},
    )
    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    return calls


def _run_lifespan(app_module):
    client = TestClient(app_module.app)
    with client:
        client.get("/api/live-refresh/status")


def test_lifespan_does_not_start_when_autostart_env_unset(
    monkeypatch, patched_refresh, pidfile_path
):
    _reset_autostart_env(monkeypatch, None)
    assert not pidfile_path.exists()

    import app as app_module

    _run_lifespan(app_module)

    assert patched_refresh["start"] == 0, (
        "Embedded lifespan must NOT start live refresh when "
        "LIVE_REFRESH_EMBEDDED_AUTOSTART is unset (default owner is systemd worker)"
    )
    assert patched_refresh["stop"] == 0, "Must not stop a loop it did not start"


def test_lifespan_does_not_start_when_autostart_env_is_zero(
    monkeypatch, patched_refresh, pidfile_path
):
    _reset_autostart_env(monkeypatch, "0")

    import app as app_module

    _run_lifespan(app_module)

    assert patched_refresh["start"] == 0
    assert patched_refresh["stop"] == 0


def test_lifespan_starts_when_opted_in_and_no_pidfile(
    monkeypatch, patched_refresh, pidfile_path, caplog
):
    _reset_autostart_env(monkeypatch, "1")
    assert not pidfile_path.exists()

    import app as app_module

    with caplog.at_level("WARNING", logger="golf.app"):
        _run_lifespan(app_module)

    assert patched_refresh["start"] == 1, (
        "Must start embedded loop when opted in via env var and worker is not running"
    )
    assert patched_refresh["stop"] == 1, "Must stop what it started on shutdown"
    assert patched_refresh["last_tour"] == "pga"
    assert any(
        "LIVE_REFRESH_EMBEDDED_AUTOSTART=1" in record.message
        for record in caplog.records
    ), "Must emit a LOUD warning announcing opt-in embedded autostart"


def test_lifespan_skips_when_pidfile_points_to_live_process(
    monkeypatch, patched_refresh, pidfile_path, caplog
):
    _reset_autostart_env(monkeypatch, "1")
    # Emulate a live worker process by PID + command probe.
    pidfile_path.write_text("4242\n", encoding="utf-8")
    monkeypatch.setattr("app.os.kill", lambda pid, sig: None)
    monkeypatch.setattr(
        "app.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["ps", "-p", "4242", "-o", "command="],
            returncode=0,
            stdout="python /opt/golf-model/workers/live_refresh_worker.py\n",
            stderr="",
        ),
    )

    import app as app_module

    with caplog.at_level("WARNING", logger="golf.app"):
        _run_lifespan(app_module)

    assert patched_refresh["start"] == 0, (
        "Must NOT start a second loop when pidfile indicates worker is running"
    )
    assert patched_refresh["stop"] == 0, (
        "Must not stop a loop it refused to start"
    )
    skip_messages = [
        r.message for r in caplog.records if "Skipping embedded live-refresh autostart" in r.message
    ]
    assert skip_messages, "Must emit WARNING explaining why embedded autostart was skipped"


def test_lifespan_starts_when_pidfile_has_stale_pid(
    monkeypatch, patched_refresh, pidfile_path
):
    _reset_autostart_env(monkeypatch, "1")
    # A PID value we can be confident is not running. Find one.
    stale_pid = 99999999
    while True:
        try:
            os.kill(stale_pid, 0)
            stale_pid += 1
        except (ProcessLookupError, PermissionError, OSError):
            break
    pidfile_path.write_text(f"{stale_pid}\n", encoding="utf-8")

    import app as app_module

    _run_lifespan(app_module)

    assert patched_refresh["start"] == 1, (
        "Stale pidfile must not block a legitimate embedded autostart"
    )


def test_worker_pidfile_helpers_roundtrip(tmp_path, monkeypatch):
    """Worker writes its PID and cleans up the file on removal."""
    from workers import live_refresh_worker

    path = tmp_path / "worker.pid"
    monkeypatch.setenv("LIVE_REFRESH_PIDFILE", str(path))

    assert live_refresh_worker._pidfile_path() == str(path)
    live_refresh_worker._write_pidfile(str(path))
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip() == str(os.getpid())
    live_refresh_worker._remove_pidfile(str(path))
    assert not path.exists()
    # Idempotent: removing a missing pidfile must not raise.
    live_refresh_worker._remove_pidfile(str(path))


def test_pid_probe_rejects_reused_non_worker_pid(tmp_path, monkeypatch):
    import app as app_module

    pidfile = tmp_path / "live_refresh.pid"
    pidfile.write_text("4242\n", encoding="utf-8")

    monkeypatch.setattr(app_module.os, "kill", lambda pid, sig: None)

    def _fake_ps(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ps", "-p", "4242", "-o", "command="],
            returncode=0,
            stdout="python /opt/golf-model/start.py dashboard --port 8000\n",
            stderr="",
        )

    monkeypatch.setattr(app_module.subprocess, "run", _fake_ps)
    assert app_module._live_refresh_worker_is_running(str(pidfile)) is False


def test_pid_probe_accepts_live_refresh_worker_process(tmp_path, monkeypatch):
    import app as app_module

    pidfile = tmp_path / "live_refresh.pid"
    pidfile.write_text("4343\n", encoding="utf-8")

    monkeypatch.setattr(app_module.os, "kill", lambda pid, sig: None)

    def _fake_ps(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ps", "-p", "4343", "-o", "command="],
            returncode=0,
            stdout="python /opt/golf-model/workers/live_refresh_worker.py\n",
            stderr="",
        )

    monkeypatch.setattr(app_module.subprocess, "run", _fake_ps)
    assert app_module._live_refresh_worker_is_running(str(pidfile)) is True


def test_pid_probe_accepts_live_refresh_worker_module_process(tmp_path, monkeypatch):
    import app as app_module

    pidfile = tmp_path / "live_refresh.pid"
    pidfile.write_text("4444\n", encoding="utf-8")

    monkeypatch.setattr(app_module.os, "kill", lambda pid, sig: None)

    def _fake_ps(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ps", "-p", "4444", "-o", "command="],
            returncode=0,
            stdout="/opt/golf-model/venv/bin/python -m workers.live_refresh_worker\n",
            stderr="",
        )

    monkeypatch.setattr(app_module.subprocess, "run", _fake_ps)
    assert app_module._live_refresh_worker_is_running(str(pidfile)) is True


def test_snapshot_does_not_embed_autostart_when_env_unset(monkeypatch, patched_refresh):
    """Stopping the systemd worker must not start recompute inside the API process."""
    _reset_autostart_env(monkeypatch, None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: {"generated_at": "2020-01-01T00:00:00+00:00", "live_tournament": {}, "upcoming_tournament": {}},
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": False},
    )

    import app as app_module

    with TestClient(app_module.app) as client:
        response = client.get("/api/live-refresh/snapshot")

    assert response.status_code == 200
    assert patched_refresh["start"] == 0, (
        "Snapshot GET must not embed live refresh when LIVE_REFRESH_EMBEDDED_AUTOSTART is unset"
    )
