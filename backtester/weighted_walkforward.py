"""Weighted walk-forward evaluation for proposal-only research runs."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Callable

from backtester.strategy import SimulationResult, StrategyConfig, replay_event
from src import config as src_config
from src import db


MAJOR_EVENTS = {
    "masters tournament",
    "pga championship",
    "u.s. open",
    "us open",
    "the open championship",
    "open championship",
}

SIGNATURE_EVENT_KEYWORDS = (
    "the players championship",
    "arnold palmer invitational",
    "memorial tournament",
    "genesis invitational",
    "travelers championship",
    "wells fargo championship",
    "truist championship",
)


def classify_event(event_name: str | None) -> str:
    name = (event_name or "").strip().lower()
    if name in MAJOR_EVENTS:
        return "major"
    if any(keyword in name for keyword in SIGNATURE_EVENT_KEYWORDS):
        return "signature"
    return "regular"


def event_weight(event_class: str, weighting_mode: str = "full_season_weighted") -> float:
    if weighting_mode != "full_season_weighted":
        return 1.0
    if event_class == "major":
        return 3.0
    if event_class == "signature":
        return 2.0
    return 1.0


def build_expanding_splits(
    events: list[dict[str, Any]],
    min_train_events: int = 2,
    test_window_size: int = 1,
) -> list[dict[str, list[dict[str, Any]]]]:
    ordered = sorted(
        events,
        key=lambda event: (event.get("event_date") or "", event.get("year") or 0, event.get("event_id") or ""),
    )
    splits: list[dict[str, list[dict[str, Any]]]] = []
    for start in range(min_train_events, len(ordered), test_window_size):
        train_events = ordered[:start]
        test_events = ordered[start:start + test_window_size]
        if not test_events:
            continue
        splits.append({"train_events": train_events, "test_events": test_events})
    return splits


def _compute_peak_to_trough_drawdown(event_results: list[dict[str, Any]]) -> float:
    """Compute peak-to-trough drawdown from cumulative weighted ROI across events."""
    if not event_results:
        return 0.0
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for result in event_results:
        weighted_roi = result.get("roi_pct", 0.0) * result.get("weight", 1.0)
        cumulative += weighted_roi
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def compute_weighted_metrics(event_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not event_results:
        return {
            "events_evaluated": 0,
            "total_bets": 0,
            "weighted_roi_pct": 0.0,
            "unweighted_roi_pct": 0.0,
            "weighted_clv_avg": 0.0,
            "unweighted_clv_avg": 0.0,
            "weighted_calibration_error": 0.0,
            "unweighted_calibration_error": 0.0,
            "max_drawdown_pct": 0.0,
        }

    total_weight = sum(result.get("weight", 1.0) for result in event_results) or 1.0

    def _weighted_avg(key: str) -> float:
        return round(
            sum(result.get(key, 0.0) * result.get("weight", 1.0) for result in event_results) / total_weight,
            4,
        )

    def _avg(key: str) -> float:
        return round(mean(result.get(key, 0.0) for result in event_results), 4)

    return {
        "events_evaluated": len(event_results),
        "total_bets": sum(result.get("total_bets", 0) for result in event_results),
        "weighted_roi_pct": _weighted_avg("roi_pct"),
        "unweighted_roi_pct": _avg("roi_pct"),
        "weighted_clv_avg": _weighted_avg("clv_avg"),
        "unweighted_clv_avg": _avg("clv_avg"),
        "weighted_calibration_error": _weighted_avg("calibration_error"),
        "unweighted_calibration_error": _avg("calibration_error"),
        "max_drawdown_pct": round(_compute_peak_to_trough_drawdown(event_results), 4),
    }


def evaluate_guardrails(
    candidate_summary: dict[str, Any],
    baseline_summary: dict[str, Any],
    *,
    min_bets: int | None = None,
    max_clv_regression: float | None = None,
    max_calibration_regression: float | None = None,
    max_drawdown_regression: float | None = None,
) -> dict[str, Any]:
    params = src_config.get_autoresearch_guardrail_params()
    min_bets = min_bets if min_bets is not None else params["min_bets"]
    max_clv_regression = max_clv_regression if max_clv_regression is not None else params["max_clv_regression"]
    max_calibration_regression = (
        max_calibration_regression if max_calibration_regression is not None else params["max_calibration_regression"]
    )
    max_drawdown_regression = (
        max_drawdown_regression if max_drawdown_regression is not None else params["max_drawdown_regression"]
    )
    reasons: list[str] = []

    if candidate_summary.get("total_bets", 0) < min_bets:
        reasons.append("insufficient_sample")
    if candidate_summary.get("weighted_clv_avg", 0.0) < baseline_summary.get("weighted_clv_avg", 0.0) - max_clv_regression:
        reasons.append("clv_regression")
    if candidate_summary.get("weighted_calibration_error", 0.0) > baseline_summary.get("weighted_calibration_error", 0.0) + max_calibration_regression:
        reasons.append("calibration_regression")
    if candidate_summary.get("max_drawdown_pct", 0.0) > baseline_summary.get("max_drawdown_pct", 0.0) + max_drawdown_regression:
        reasons.append("drawdown_regression")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "verdict": "promising" if not reasons else "blocked_by_guardrails",
    }


def compute_blended_score(
    candidate_summary: dict[str, Any],
    guardrail_results: dict[str, Any],
    bet_details: list[dict] | None = None,
) -> float:
    matchup_roi = 0.0
    matchup_hit_rate = 0.0
    if bet_details:
        matchup_bets = [b for b in bet_details if b.get("market") == "matchup"]
        if matchup_bets:
            total_wagered = sum(b.get("wager", 0) for b in matchup_bets)
            total_payout = sum(b.get("payout", 0) for b in matchup_bets)
            matchup_roi = ((total_payout - total_wagered) / total_wagered * 100) if total_wagered > 0 else 0
            matchup_hit_rate = sum(1 for b in matchup_bets if b.get("won")) / len(matchup_bets)

    score = (
        matchup_roi * 2.0
        + matchup_hit_rate * 50.0
        + candidate_summary.get("weighted_roi_pct", 0.0) * 0.5
        + candidate_summary.get("weighted_clv_avg", 0.0) * 100.0
        - candidate_summary.get("weighted_calibration_error", 0.0) * 10.0
        - candidate_summary.get("max_drawdown_pct", 0.0) * 0.1
        + min(candidate_summary.get("total_bets", 0), 200) / 200.0
    )
    if not guardrail_results.get("passed", False):
        score -= 25.0
    return round(score, 4)


def load_historical_events(years: list[int] | None = None) -> list[dict[str, Any]]:
    conn = db.get_conn()
    params: list[Any] = []
    where = ""
    if years:
        placeholders = ",".join("?" for _ in years)
        where = f"WHERE year IN ({placeholders})"
        params.extend(years)

    rows = conn.execute(
        f"""
        SELECT event_id, year, MAX(event_name) AS event_name, MIN(event_completed) AS event_date
        FROM rounds
        {where}
        GROUP BY event_id, year
        HAVING event_id IS NOT NULL AND event_date IS NOT NULL
        ORDER BY event_date ASC, year ASC, event_id ASC
        """,
        params,
    ).fetchall()
    conn.close()

    return [
        {
            "event_id": row["event_id"],
            "year": row["year"],
            "event_name": row["event_name"],
            "event_date": row["event_date"],
        }
        for row in rows
    ]


def _default_replay_runner(event: dict[str, Any], strategy: StrategyConfig) -> dict[str, Any]:
    bets = replay_event(event["event_id"], event["year"], strategy)
    result = SimulationResult(strategy=strategy, events_simulated=1, bet_details=bets)
    result.compute_metrics()
    return {
        "roi_pct": result.roi_pct,
        "clv_avg": result.clv_avg,
        "calibration_error": result.calibration_error,
        "total_bets": result.total_bets,
        "max_drawdown_pct": max(0.0, -result.roi_pct),
    }


def _segment_results(event_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in event_results:
        buckets[result["event_class"]].append(result)
    return {segment: compute_weighted_metrics(rows) for segment, rows in buckets.items()}


def evaluate_weighted_walkforward(
    *,
    strategy: StrategyConfig,
    baseline_strategy: StrategyConfig,
    events: list[dict[str, Any]] | None = None,
    years: list[int] | None = None,
    replay_runner: Callable[[dict[str, Any], StrategyConfig], dict[str, Any]] | None = None,
    min_train_events: int = 2,
    test_window_size: int = 1,
    weighting_mode: str = "full_season_weighted",
    precomputed_baseline: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if events is None:
        events = load_historical_events(years)
    if replay_runner is None:
        replay_runner = _default_replay_runner

    splits = build_expanding_splits(events, min_train_events=min_train_events, test_window_size=test_window_size)
    candidate_results: list[dict[str, Any]] = []
    baseline_results: list[dict[str, Any]] = []

    if precomputed_baseline is not None:
        baseline_results = list(precomputed_baseline)

    for split in splits:
        for event in split["test_events"]:
            event_class = classify_event(event.get("event_name"))
            weight = event_weight(event_class, weighting_mode=weighting_mode)

            candidate_metrics = replay_runner(event, strategy)

            candidate_results.append(
                {
                    **event,
                    **candidate_metrics,
                    "event_class": event_class,
                    "weight": weight,
                }
            )
            if precomputed_baseline is None:
                baseline_metrics = replay_runner(event, baseline_strategy)
                baseline_results.append(
                    {
                        **event,
                        **baseline_metrics,
                        "event_class": event_class,
                        "weight": weight,
                    }
                )

    summary_metrics = compute_weighted_metrics(candidate_results)
    baseline_summary = compute_weighted_metrics(baseline_results)
    guardrail_results = evaluate_guardrails(summary_metrics, baseline_summary)

    return {
        "summary_metrics": summary_metrics,
        "baseline_summary_metrics": baseline_summary,
        "segmented_metrics": _segment_results(candidate_results),
        "baseline_segmented_metrics": _segment_results(baseline_results),
        "guardrail_results": guardrail_results,
        "event_results": candidate_results,
        "baseline_event_results": baseline_results,
        "splits": splits,
    }
