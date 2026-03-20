"""Continuous optimizer runtime: research_cycle (theory + walk-forward) or Optuna MO trials."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from backtester.autoresearch_engine import run_cycle as run_autoresearch_cycle
from backtester.research_cycle import (
    PIT_EVALUATION_YEARS,
    get_current_baseline_metrics,
)

_logger = logging.getLogger("autoresearch.runtime")
_state_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_state: dict[str, Any] = {
    "running": False,
    "scope": "global",
    "interval_seconds": 300,
    "max_candidates": 5,
    "years": None,
    "engine_mode": "research_cycle",
    "optuna_study_name": "golf_mo_dashboard",
    "optuna_trials_per_cycle": 3,
    "run_count": 0,
    "last_cycle_key": None,
    "last_run_started_at": None,
    "last_run_finished_at": None,
    "last_error": None,
    "keep_rate": 0.0,
    "crash_rate": 0.0,
    "guardrail_fail_rate": 0.0,
    "cycles_kept": 0,
    "cycles_guardrail_pass": 0,
    "at_start_baseline_roi": None,
    "at_start_baseline_clv": None,
}


def _emit(message: str) -> None:
    line = f"[AUTORESEARCH] {message}"
    print(line, flush=True)
    _logger.info(line)


def _research_cycle_result_kept(result: dict[str, Any]) -> bool:
    if result.get("research_champion_updated"):
        return True
    winner = result.get("winner") or {}
    if (winner.get("guardrail_results") or {}).get("passed"):
        return True
    for c in result.get("top_candidates") or []:
        if (c.get("guardrail_results") or {}).get("passed"):
            return True
    return False


def _research_cycle_any_guardrail_pass(result: dict[str, Any]) -> bool:
    for c in result.get("top_candidates") or []:
        if (c.get("guardrail_results") or {}).get("passed"):
            return True
    return False


def _run_optuna_cycle(
    scope: str,
    years: list[int] | None,
    trials: int,
    study_name: str,
) -> dict[str, Any]:
    from backtester.experiments import get_active_strategy
    from backtester.model_registry import get_live_weekly_model, get_research_champion
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import run_mo_study, study_summary

    baseline = get_research_champion(scope) or get_live_weekly_model(scope) or get_active_strategy(scope)
    spec = WalkForwardBenchmarkSpec(years=years)
    study = run_mo_study(
        n_trials=trials,
        baseline=baseline,
        benchmark_spec=spec,
        study_name=study_name,
    )
    summ = study_summary(study)
    kept = False
    for pt in summ.get("pareto_trials", []):
        ua = pt.get("user_attrs") or {}
        if ua.get("feasible") and ua.get("guardrail_passed"):
            kept = True
            break
    any_gr = any((pt.get("user_attrs") or {}).get("guardrail_passed") for pt in summ.get("pareto_trials", []))
    cycle_key = f"optuna:{study_name}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    return {
        "cycle_key": cycle_key,
        "evaluation_mode": "optuna_mo",
        "optuna_summary": summ,
        "winner": None,
        "top_candidates": [],
        "research_champion_updated": False,
        "promotion_decision": "optuna_cycle",
        "data_health": None,
        "guardrail_mode": None,
        "eval_contract_version_walk_forward": None,
        "_optuna_kept": kept,
        "_optuna_any_guardrail_pass": any_gr,
    }


def _run_loop(
    scope: str,
    interval_seconds: float,
    max_candidates: int,
    years: list[int] | None,
    engine_mode: str,
    optuna_study_name: str,
    optuna_trials_per_cycle: int,
) -> None:
    if years is None:
        years = PIT_EVALUATION_YEARS
    while not _stop_event.is_set():
        cycle_started = datetime.now(timezone.utc)
        with _state_lock:
            _state["last_run_started_at"] = cycle_started.isoformat()
            _state["last_error"] = None
        _emit(
            "cycle starting"
            f" mode={engine_mode}"
            f" scope={scope}"
            f" max_candidates={max_candidates}"
            f" years={years or 'auto'}"
        )
        try:
            result = None
            last_exc = None
            for attempt in range(2):
                try:
                    if engine_mode == "optuna":
                        result = _run_optuna_cycle(
                            scope,
                            years,
                            optuna_trials_per_cycle,
                            optuna_study_name,
                        )
                    else:
                        result = run_autoresearch_cycle(
                            scope=scope,
                            source="optimizer_daemon",
                            max_candidates=max_candidates,
                            years=years,
                        )
                    break
                except Exception as exc:
                    last_exc = exc
                    if attempt == 0 and ("disk I/O" in str(exc) or "I/O error" in str(exc).lower()):
                        _emit("disk I/O error, retrying in 5s...")
                        _stop_event.wait(5.0)
                        continue
                    raise
            if result is None:
                raise last_exc
            cycle_finished = datetime.now(timezone.utc)
            with _state_lock:
                _state["run_count"] += 1
                rc = _state["run_count"]
                _state["last_cycle_key"] = result.get("cycle_key")
                _state["last_result"] = result
                _state["last_run_finished_at"] = cycle_finished.isoformat()
                _state["crash_rate"] = 0.0
                if engine_mode == "optuna":
                    if result.get("_optuna_kept"):
                        _state["cycles_kept"] += 1
                    if result.get("_optuna_any_guardrail_pass"):
                        _state["cycles_guardrail_pass"] += 1
                else:
                    if _research_cycle_result_kept(result):
                        _state["cycles_kept"] += 1
                    if _research_cycle_any_guardrail_pass(result):
                        _state["cycles_guardrail_pass"] += 1
                ck = _state["cycles_kept"]
                cg = _state["cycles_guardrail_pass"]
                _state["keep_rate"] = round(ck / max(1, rc), 4)
                _state["guardrail_fail_rate"] = round(1.0 - (cg / max(1, rc)), 4)
            _emit(
                "cycle finished"
                f" run_count={_state['run_count']}"
                f" cycle_key={result.get('cycle_key')}"
                f" keep_rate={_state['keep_rate']}"
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
    max_candidates: int | None = None,
    years: list[int] | None = None,
    engine_mode: str | None = None,
    optuna_study_name: str | None = None,
    optuna_trials_per_cycle: int | None = None,
) -> dict[str, Any]:
    global _thread
    from backtester.research_lab.cycle_config import load_cycle_config
    from src.autoresearch_settings import get_settings

    settings = get_settings()
    cc = load_cycle_config()
    if max_candidates is None:
        max_candidates = int(cc.get("max_candidates_per_cycle") or 5)
    em = (engine_mode or settings.get("engine_mode") or "research_cycle").strip().lower()
    if em not in ("research_cycle", "optuna"):
        em = "research_cycle"
    sn = (optuna_study_name or settings.get("optuna_study_name") or "golf_mo_dashboard").strip()[:120]
    try:
        ot = int(optuna_trials_per_cycle if optuna_trials_per_cycle is not None else settings.get("optuna_trials_per_cycle") or 3)
    except (TypeError, ValueError):
        ot = 3
    ot = max(1, min(50, ot))

    with _state_lock:
        if _state.get("running"):
            _emit("start requested but engine already running")
            return dict(_state)
        _stop_event.clear()
    baseline = get_current_baseline_metrics(scope)
    with _state_lock:
        _state.update(
            {
                "running": True,
                "scope": scope,
                "interval_seconds": interval_seconds,
                "max_candidates": max_candidates,
                "years": years,
                "engine_mode": em,
                "optuna_study_name": sn,
                "optuna_trials_per_cycle": ot,
                "last_error": None,
                "at_start_baseline_roi": baseline.get("weighted_roi_pct"),
                "at_start_baseline_clv": baseline.get("weighted_clv_avg"),
                "cycles_kept": 0,
                "cycles_guardrail_pass": 0,
                "run_count": 0,
                "keep_rate": 0.0,
                "guardrail_fail_rate": 0.0,
            }
        )
    _emit(
        "engine starting"
        f" mode={em}"
        f" scope={scope}"
        f" interval_seconds={interval_seconds}"
        f" max_candidates={max_candidates}"
        f" optuna_trials={ot}"
        f" years={years or 'auto'}"
    )
    _thread = threading.Thread(
        target=_run_loop,
        args=(scope, interval_seconds, max_candidates, years, em, sn, ot),
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
