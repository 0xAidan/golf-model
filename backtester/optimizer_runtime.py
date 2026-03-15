"""Continuous optimizer runtime built on top of bounded research cycles."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from backtester.research_cycle import run_research_cycle

_logger = logging.getLogger("autoresearch.runtime")
_state_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_state: dict[str, Any] = {
    "running": False,
    "scope": "global",
    "interval_seconds": 300,
    "max_candidates": 3,
    "years": None,
    "run_count": 0,
    "last_cycle_key": None,
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "last_error": None,
    "keep_rate": 0.0,
    "crash_rate": 0.0,
    "guardrail_fail_rate": 0.0,
}


def _emit(message: str) -> None:
    line = f"[AUTORESEARCH] {message}"
    print(line, flush=True)
    _logger.info(line)


def _run_loop(scope: str, interval_seconds: float, max_candidates: int, years: list[int] | None) -> None:
    while not _stop_event.is_set():
        cycle_started = datetime.now(timezone.utc)
        with _state_lock:
            _state["last_run_started_at"] = cycle_started.isoformat()
            _state["last_error"] = None
        _emit(
            "cycle starting"
            f" scope={scope}"
            f" max_candidates={max_candidates}"
            f" years={years or 'auto'}"
        )
        try:
            result = run_research_cycle(
                scope=scope,
                source="optimizer_daemon",
                max_candidates=max_candidates,
                years=years,
            )
            cycle_finished = datetime.now(timezone.utc)
            with _state_lock:
                _state["run_count"] += 1
                _state["last_cycle_key"] = result.get("cycle_key")
                _state["last_result"] = result
                _state["last_run_finished_at"] = cycle_finished.isoformat()
                winner = result.get("winner") or {}
                guardrails = (winner.get("guardrail_results") or {}) if isinstance(winner, dict) else {}
                _state["keep_rate"] = 1.0 if winner else 0.0
                _state["crash_rate"] = 0.0
                _state["guardrail_fail_rate"] = 0.0 if guardrails.get("passed", True) else 1.0
            _emit(
                "cycle finished"
                f" run_count={_state['run_count']}"
                f" cycle_key={result.get('cycle_key')}"
                f" winner={'yes' if result.get('winner') else 'no'}"
                f" elapsed_seconds={(cycle_finished - cycle_started).total_seconds():.2f}"
            )
        except Exception as exc:
            cycle_finished = datetime.now(timezone.utc)
            with _state_lock:
                _state["last_error"] = str(exc)
                _state["last_run_finished_at"] = cycle_finished.isoformat()
                _state["crash_rate"] = 1.0
            _emit(
                "cycle failed"
                f" error={exc}"
                f" elapsed_seconds={(cycle_finished - cycle_started).total_seconds():.2f}"
            )
        if _stop_event.wait(interval_seconds):
            break
    with _state_lock:
        _state["running"] = False
    _emit("engine loop stopped")


def start_continuous_optimizer(
    *,
    scope: str = "global",
    interval_seconds: float = 300,
    max_candidates: int = 3,
    years: list[int] | None = None,
) -> dict[str, Any]:
    global _thread
    with _state_lock:
        if _state.get("running"):
            _emit("start requested but engine already running")
            return dict(_state)
        _stop_event.clear()
        _state.update(
            {
                "running": True,
                "scope": scope,
                "interval_seconds": interval_seconds,
                "max_candidates": max_candidates,
                "years": years,
                "last_error": None,
            }
        )
    _emit(
        "engine starting"
        f" scope={scope}"
        f" interval_seconds={interval_seconds}"
        f" max_candidates={max_candidates}"
        f" years={years or 'auto'}"
    )
    _thread = threading.Thread(
        target=_run_loop,
        args=(scope, interval_seconds, max_candidates, years),
        daemon=True,
        name="continuous-optimizer",
    )
    _thread.start()
    return get_optimizer_status()


def stop_continuous_optimizer() -> dict[str, Any]:
    global _thread
    _emit("stop requested")
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)
    _thread = None
    with _state_lock:
        _state["running"] = False
    return get_optimizer_status()


def get_optimizer_status() -> dict[str, Any]:
    with _state_lock:
        return dict(_state)
