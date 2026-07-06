"""
Dedicated always-on worker process for dashboard live refresh snapshots.
"""

from __future__ import annotations

import logging
import os
import signal
import time

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in some environments
    load_dotenv = None

from backtester.dashboard_runtime import (
    runtime_thread_alive,
    start_live_refresh,
    stop_live_refresh,
)
from src.autoresearch_settings import get_settings
from src.db import ensure_initialized

_shutdown = False

DEFAULT_PIDFILE = "/tmp/golf_live_refresh.pid"


def _pidfile_path() -> str:
    return os.environ.get("LIVE_REFRESH_PIDFILE", DEFAULT_PIDFILE)


def _write_pidfile(path: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()}\n")
    except OSError as exc:
        logging.getLogger("live_refresh_worker").warning(
            "Failed to write pidfile %s: %s", path, exc
        )


def _remove_pidfile(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        logging.getLogger("live_refresh_worker").warning(
            "Failed to remove pidfile %s: %s", path, exc
        )


def _pid_alive(pid: int) -> bool:
    """True if a process with this pid exists (signal 0 probe)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _clear_stale_pidfile(path: str) -> None:
    """If a prior worker was SIGKILLed, its pidfile survives and would otherwise block the
    dashboard's embedded-autostart guard / port-owner checks. Detect a pidfile pointing at a
    dead process on startup and clear it (the finally-block handles clean/exception exits)."""
    log = logging.getLogger("live_refresh_worker")
    try:
        with open(path, encoding="utf-8") as fh:
            existing = int((fh.read().strip() or "0"))
    except FileNotFoundError:
        return
    except (OSError, ValueError):
        log.warning("Unreadable pidfile %s; clearing", path)
        _remove_pidfile(path)
        return
    if existing == os.getpid():
        return
    if _pid_alive(existing):
        log.warning(
            "Pidfile %s points at a live process (pid %s); another worker may be running.",
            path,
            existing,
        )
        return
    log.warning("Clearing stale pidfile %s (pid %s not alive)", path, existing)
    _remove_pidfile(path)


def _handle_signal(signum, _frame):
    global _shutdown
    _shutdown = True
    logging.getLogger("live_refresh_worker").info("Received signal %s, stopping...", signum)


def main() -> int:
    if load_dotenv:
        load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    ensure_initialized()
    live_cfg = (get_settings().get("live_refresh") or {})
    tour = str(live_cfg.get("tour", "pga"))

    pidfile = _pidfile_path()
    _clear_stale_pidfile(pidfile)
    _write_pidfile(pidfile)
    try:
        start_live_refresh(tour=tour)
        log = logging.getLogger("live_refresh_worker")

        while not _shutdown:
            if not runtime_thread_alive():
                log.critical(
                    "Live refresh runtime thread died unexpectedly; exiting for systemd restart"
                )
                return 1
            time.sleep(1.0)

        stop_live_refresh()
    finally:
        _remove_pidfile(pidfile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
