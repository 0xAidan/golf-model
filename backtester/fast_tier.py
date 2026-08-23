"""Fast-tier experiment runner: cached PIT sub-scores + precomputed baselines.

The dominant cost of walk-forward replay is re-deriving point-in-time form /
course-fit / momentum scores per event for every candidate. Those sub-scores are
strategy-INDEPENDENT (only the final blend uses the candidate's w_sub_* values),
so they can be prefetched once per window and reused across all trials.

Design guarantees:
- The frozen evaluator is NOT duplicated. We inject a cache in front of
  ``backtester.strategy.compute_pit_composite``; on any miss it delegates to the
  real implementation. tests/test_fast_tier.py asserts fast-tier results are
  IDENTICAL to plain replay results.
- Baseline walk-forward results are computed once and passed as
  ``precomputed_baseline`` (supported by evaluate_weighted_walkforward).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backtester import strategy as strategy_module
from backtester.pit_models import (
    compute_pit_composite,
    compute_pit_course_fit,
    compute_pit_form,
    compute_pit_momentum,
)
from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
from backtester.sealed_holdout import filter_sealed_events
from backtester.weighted_walkforward import (
    _default_replay_runner,
    build_expanding_splits,
    load_historical_events,
)

# Effort presets (operator-facing dial; persisted setting read by the orchestrator).
EFFORT_PRESETS: dict[str, dict[str, Any]] = {
    "light": {"max_wall_seconds": 20 * 60, "max_trials": 30},
    "standard": {"max_wall_seconds": 60 * 60, "max_trials": 100},
    "max": {"max_wall_seconds": 3 * 60 * 60, "max_trials": 300},
}
DEFAULT_EFFORT = "standard"

SEARCH_WINDOW_SIZE = 13
CONFIRMATION_WINDOW_SIZE = 3


def resolve_effort(name: str | None) -> dict[str, Any]:
    """Return the preset for an effort name (falls back to standard)."""
    return EFFORT_PRESETS.get((name or DEFAULT_EFFORT).strip().lower(), EFFORT_PRESETS[DEFAULT_EFFORT])


@dataclass
class EffortBudget:
    max_wall_seconds: float
    max_trials: int
    started_at: float = field(default_factory=time.perf_counter)
    trials_used: int = 0

    @classmethod
    def for_effort(cls, name: str | None) -> "EffortBudget":
        preset = resolve_effort(name)
        return cls(max_wall_seconds=float(preset["max_wall_seconds"]), max_trials=int(preset["max_trials"]))

    def start_trial(self) -> bool:
        """Claim one trial slot if budget allows; returns whether the trial may run."""
        if self.trials_used >= self.max_trials:
            return False
        if (time.perf_counter() - self.started_at) >= self.max_wall_seconds:
            return False
        self.trials_used += 1
        return True

    def exhausted(self) -> bool:
        return (
            self.trials_used >= self.max_trials
            or (time.perf_counter() - self.started_at) >= self.max_wall_seconds
        )

    def elapsed_seconds(self) -> float:
        return round(time.perf_counter() - self.started_at, 3)


def select_research_windows(
    *,
    search_size: int = SEARCH_WINDOW_SIZE,
    confirmation_size: int = CONFIRMATION_WINDOW_SIZE,
    years: list[int] | None = None,
    require_pit: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """
    Deterministic window selection per PROGRAM.md:

      sealed holdout (2 oldest capture-era events, excluded forever)
      -> remaining events ordered chronologically
      -> CONFIRMATION = most recent `confirmation_size`
      -> SEARCH = the `search_size` completed events immediately before them

    Events without PIT rows cannot be replayed; when require_pit is True they
    are skipped entirely so windows never contain dead slots.
    """
    events = load_historical_events(years)
    events = [e for e in events if e.get("event_date")]
    if require_pit:
        events = _filter_events_with_pit(events)
    events = filter_sealed_events(events)
    events.sort(key=lambda e: (e.get("event_date") or "", e.get("year") or 0))

    if len(events) <= confirmation_size:
        return {"search": [], "confirmation": events, "excluded_sealed": True}

    confirmation = events[-confirmation_size:]
    pool = events[:-confirmation_size]
    search = pool[-search_size:] if len(pool) > search_size else pool
    return {"search": search, "confirmation": confirmation, "excluded_sealed": True}


def _filter_events_with_pit(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from src.db import get_conn

    conn = get_conn()
    try:
        built = {
            (str(row[0]), int(row[1]))
            for row in conn.execute(
                "SELECT DISTINCT event_id, year FROM pit_rolling_stats"
            ).fetchall()
        }
    finally:
        conn.close()
    return [
        e for e in events if (str(e.get("event_id")), int(e.get("year") or 0)) in built
    ]


# ---------------------------------------------------------------------------
# PIT sub-score cache (injected in front of the frozen composite builder)
# ---------------------------------------------------------------------------


class _PITSubScoreCache:
    """Prefetches per-event (form, course_fit, momentum) score dicts."""

    def __init__(self) -> None:
        self._raw: dict[tuple[str, int], tuple[dict, dict, dict]] = {}
        self.hits = 0
        self.misses = 0

    def prefetch(self, event_id: str, year: int) -> None:
        key = (str(event_id), int(year))
        if key not in self._raw:
            self._raw[key] = (
                compute_pit_form(str(event_id), int(year)),
                compute_pit_course_fit(str(event_id), int(year)),
                compute_pit_momentum(str(event_id), int(year)),
            )

    def get(self, event_id: str, year: int) -> tuple[dict, dict, dict] | None:
        return self._raw.get((str(event_id), int(year)))

    def stats(self) -> dict[str, int]:
        return {"events_cached": len(self._raw)}


_CACHE: _PITSubScoreCache | None = None
_ORIGINAL_COMPUTE_PIT_COMPOSITE = strategy_module.compute_pit_composite


def _cached_compute_pit_composite(
    event_id: str,
    year: int,
    w_course_fit: float = 0.40,
    w_form: float = 0.40,
    w_momentum: float = 0.20,
) -> dict:
    """Drop-in for pit_models.compute_pit_composite backed by prefetched raw scores."""
    assert _CACHE is not None
    raw = _CACHE.get(event_id, year)
    if raw is None:
        return _ORIGINAL_COMPUTE_PIT_COMPOSITE(
            str(event_id), int(year),
            w_course_fit=w_course_fit, w_form=w_form, w_momentum=w_momentum,
        )
    form_scores, course_scores, momentum_scores = raw
    return _blend_sub_scores(form_scores, course_scores, momentum_scores, w_course_fit, w_form, w_momentum)


def _blend_sub_scores(
    form_scores: dict,
    course_scores: dict,
    momentum_scores: dict,
    w_course_fit: float,
    w_form: float,
    w_momentum: float,
) -> dict:
    """Exact mirror of pit_models.compute_pit_composite's blend block (kept in sync by tests)."""
    all_players = set()
    all_players.update(form_scores.keys())
    all_players.update(course_scores.keys())
    all_players.update(momentum_scores.keys())

    if not all_players:
        return {}

    has_course_data = bool(course_scores)
    if not has_course_data:
        w_form_adj = w_form + w_course_fit * 0.7
        w_momentum_adj = w_momentum + w_course_fit * 0.3
        w_course_adj = 0.0
    else:
        w_course_adj = w_course_fit
        w_form_adj = w_form
        w_momentum_adj = w_momentum

    results: dict[str, dict[str, Any]] = {}
    for pk in all_players:
        cs = course_scores.get(pk, {})
        fs = form_scores.get(pk, {})
        ms = momentum_scores.get(pk, {})

        course_score = cs.get("score", 50.0)
        form_score = fs.get("score", 50.0)
        momentum_score = ms.get("score", 50.0)

        composite = (
            w_course_adj * course_score
            + w_form_adj * form_score
            + w_momentum_adj * momentum_score
        )
        composite = max(0.0, min(100.0, composite))

        results[pk] = {
            "composite": round(composite, 2),
            "course_fit": round(course_score, 2),
            "form": round(form_score, 2),
            "momentum": round(momentum_score, 2),
            "momentum_direction": ms.get("direction", "unknown"),
            "course_confidence": cs.get("confidence", 0),
            "course_rounds": cs.get("rounds", 0),
        }

    return results


class FastTierWindow:
    """Context manager: activate the sub-score cache for a set of events."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.cache = _PITSubScoreCache()
        self.events = events
        self.prefetch_seconds: float | None = None

    def __enter__(self) -> "FastTierWindow":
        global _CACHE
        t0 = time.perf_counter()
        for event in self.events:
            self.cache.prefetch(event["event_id"], event["year"])
        self.prefetch_seconds = round(time.perf_counter() - t0, 3)
        _CACHE = self.cache
        strategy_module.compute_pit_composite = _cached_compute_pit_composite
        return self

    def __exit__(self, *_exc) -> None:
        global _CACHE
        strategy_module.compute_pit_composite = _ORIGINAL_COMPUTE_PIT_COMPOSITE
        _CACHE = None
        return None


# ---------------------------------------------------------------------------
# Evaluation entry points
# ---------------------------------------------------------------------------


def compute_precomputed_baseline_results(
    baseline_strategy,
    events: list[dict[str, Any]],
    *,
    min_train_events: int = 2,
    test_window_size: int = 1,
) -> list[dict[str, Any]]:
    """Baseline per-event results once, in split-test order (for precomputed_baseline)."""
    splits = build_expanding_splits(
        events, min_train_events=min_train_events, test_window_size=test_window_size
    )
    results: list[dict[str, Any]] = []
    for split in splits:
        for event in split["test_events"]:
            metrics = _default_replay_runner(event, baseline_strategy)
            results.append({**event, **metrics})
    return results


def make_fast_eval_fn(
    baseline_strategy,
    spec: WalkForwardBenchmarkSpec,
    events: list[dict[str, Any]],
):
    """
    Build an evaluate_fn for research_lab.mo_study.make_objective that (a) runs
    inside the fast-tier cache window and (b) reuses one precomputed baseline.

    Signature matches evaluate_walk_forward_benchmark(strategy, baseline, spec).
    """
    with FastTierWindow(events) as window:
        baseline_results = compute_precomputed_baseline_results(
            baseline_strategy,
            events,
            min_train_events=spec.min_train_events,
            test_window_size=spec.test_window_size,
        )
    baseline_payload = [
        {
            k: row.get(k)
            for k in ("roi_pct", "clv_avg", "calibration_error", "total_bets", "max_drawdown_pct")
        }
        | {"event_id": row.get("event_id"), "year": row.get("year"),
           "event_name": row.get("event_name"), "event_date": row.get("event_date"),
           "event_class": row.get("event_class"), "weight": row.get("weight", 1.0)}
        for row in baseline_results
    ]

    from backtester.research_lab.canonical import evaluation_from_walk_forward_dict
    from backtester.weighted_walkforward import evaluate_weighted_walkforward

    def evaluate_fn(candidate, baseline, benchmark_spec):
        with FastTierWindow(events):
            raw = evaluate_weighted_walkforward(
                strategy=candidate,
                baseline_strategy=baseline,
                events=events,
                years=benchmark_spec.years,
                min_train_events=benchmark_spec.min_train_events,
                test_window_size=benchmark_spec.test_window_size,
                weighting_mode=benchmark_spec.weighting_mode,
                precomputed_baseline=baseline_payload,
            )
        result = evaluation_from_walk_forward_dict(
            raw, eval_contract_version=benchmark_spec.eval_contract_version
        )
        result.metadata = {"fast_tier": True, "prefetch_seconds": window.prefetch_seconds}
        return result

    return evaluate_fn
