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

from backtester.dashboard_runtime import start_live_refresh, stop_live_refresh
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
    _write_pidfile(pidfile)
    try:
        start_live_refresh(tour=tour)

        while not _shutdown:
            time.sleep(1.0)

        stop_live_refresh()
    finally:
        _remove_pidfile(pidfile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
