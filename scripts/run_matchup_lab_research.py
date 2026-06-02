#!/usr/bin/env python3
"""Run Phase 2/3 matchup lab research sweeps and emit markdown/json artifacts."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtester.strategy import StrategyConfig, replay_event
from backtester.weighted_walkforward import load_historical_events
from backtester.checkpoint_replay import assert_checkpoint_temporal_integrity
from src import config, db

try:
    import optuna
except ImportError:  # pragma: no cover - optional runtime dependency
    optuna = None

try:
    from sklearn.linear_model import LogisticRegression
except ImportError:  # pragma: no cover - optional runtime dependency
    LogisticRegression = None


PRIMARY_YEARS = [2024, 2025]
HOLDOUT_YEARS = [2026]
PRIMARY_DATE_START = "2024-01-01"
PRIMARY_DATE_END = "2025-12-31"
HOLDOUT_DATE_START = "2026-01-01"
HOLDOUT_DATE_END = "2026-12-31"
MIN_CANDIDATE_N = 200
MIN_WIREUP_N = 250
FULL_SLATE_EV_FLOOR = -1000.0


@dataclass
class ScenarioSpec:
    scenario_id: str
    title: str
    family: str
    strategy_overrides: dict[str, Any]
    filters: dict[str, Any]
    unsupported_reason: str | None = None
    notes: str | None = None


def _softmax_weights(logits: list[float]) -> list[float]:
    if not logits:
        return []
    max_logit = max(logits)
    exps = [math.exp(v - max_logit) for v in logits]
    denom = sum(exps)
    if denom <= 0:
        return [1.0 / len(logits)] * len(logits)
    return [v / denom for v in exps]


def _baseline_strategy() -> StrategyConfig:
    return StrategyConfig(
        name="matchup_lab_baseline",
        markets=["matchup"],
        stake_mode="flat",
        flat_stake=1.0,
        min_ev=float(getattr(config, "DEFAULT_EV_THRESHOLD", 0.08)),
        # Collect full slate in replay and apply thresholds in post-filters.
        matchup_ev_threshold=FULL_SLATE_EV_FLOOR,
        platt_a=float(getattr(config, "MATCHUP_PLATT_A", -0.05)),
        platt_b=float(getattr(config, "MATCHUP_PLATT_B", 0.0)),
        min_composite_gap=0.0,
        max_win_prob_cap=0.99,
        matchup_market_types=[
            "72-hole Match",
            "R1 Match-Up",
            "R2 Match-Up",
            "R3 Match-Up",
            "R4 Match-Up",
        ],
        dg_matchup_blend_weight=float(getattr(config, "DG_MATCHUP_BLEND_WEIGHT", 0.8)),
        model_matchup_blend_weight=float(getattr(config, "MODEL_MATCHUP_BLEND_WEIGHT", 0.2)),
        matchup_require_positive_ev=False,
        matchup_include_all_sides=True,
        matchup_include_all_books=True,
    )


def _all_specs() -> list[ScenarioSpec]:
    specs: list[ScenarioSpec] = [
        ScenarioSpec("E0", "Frozen baseline", "experiment_matrix", {}, {}),
        ScenarioSpec("E1", "EV floor 8%", "experiment_matrix", {"matchup_ev_threshold": 0.08}, {}),
        ScenarioSpec("E2", "EV floor 10%", "experiment_matrix", {"matchup_ev_threshold": 0.10}, {}),
        ScenarioSpec("E3", "GOOD+ tier only", "experiment_matrix", {}, {"tier_floor": "GOOD"}),
        ScenarioSpec("E4", "marketing_safe required", "experiment_matrix", {}, {"marketing_safe_required": True}),
        ScenarioSpec(
            "E5a",
            "DG/model blend 70/30",
            "experiment_matrix",
            {"dg_matchup_blend_weight": 0.70, "model_matchup_blend_weight": 0.30},
            {},
            unsupported_reason="Historical matchup replay rows do not include DG matchup probabilities; blend weights are inert in replay-only evaluation.",
        ),
        ScenarioSpec(
            "E5b",
            "DG/model blend 90/10",
            "experiment_matrix",
            {"dg_matchup_blend_weight": 0.90, "model_matchup_blend_weight": 0.10},
            {},
            unsupported_reason="Historical matchup replay rows do not include DG matchup probabilities; blend weights are inert in replay-only evaluation.",
        ),
        ScenarioSpec("E6", "Rolling Platt by split", "experiment_matrix", {}, {"rolling_platt": True}),
        ScenarioSpec("E7", "Exclude odds > +300", "experiment_matrix", {}, {"max_positive_odds": 300}),
        ScenarioSpec("E8", "v5 tie-aware EV", "experiment_matrix", {"model_variant": "v5"}, {}),
    ]

    # H1-H13
    specs.extend(
        [
            ScenarioSpec("H1_fix_a-0.06_b0.00", "H1 fixed Platt A/B", "hypothesis", {"platt_a": -0.06, "platt_b": 0.00}, {}),
            ScenarioSpec("H1_fix_a-0.04_b0.02", "H1 fixed Platt A/B", "hypothesis", {"platt_a": -0.04, "platt_b": 0.02}, {}),
            ScenarioSpec("H2_blend_050", "H2 DG blend 0.50", "hypothesis", {"dg_matchup_blend_weight": 0.50, "model_matchup_blend_weight": 0.50}, {}, "Replay lacks DG probabilities; blend sweep is non-identifiable."),
            ScenarioSpec("H2_blend_075", "H2 DG blend 0.75", "hypothesis", {"dg_matchup_blend_weight": 0.75, "model_matchup_blend_weight": 0.25}, {}, "Replay lacks DG probabilities; blend sweep is non-identifiable."),
            ScenarioSpec("H2_blend_095", "H2 DG blend 0.95", "hypothesis", {"dg_matchup_blend_weight": 0.95, "model_matchup_blend_weight": 0.05}, {}, "Replay lacks DG probabilities; blend sweep is non-identifiable."),
            ScenarioSpec("H3_agreement_off", "H3 DG/model agreement OFF", "hypothesis", {}, {}, "Replay does not include DG probabilities, so agreement gate does not trigger."),
            ScenarioSpec("H3_agreement_on", "H3 DG/model agreement ON", "hypothesis", {}, {}, "Replay does not include DG probabilities, so agreement gate does not trigger."),
            ScenarioSpec("H4_tieaware_on", "H4 tie-aware ON", "hypothesis", {"model_variant": "v5"}, {}),
            ScenarioSpec("H4_tieaware_off", "H4 tie-aware OFF", "hypothesis", {"model_variant": "baseline"}, {}),
            ScenarioSpec("H5_sigmoid_a-0.08", "H5 sigmoid slope sweep", "hypothesis", {"platt_a": -0.08, "max_win_prob_cap": 0.90}, {}),
            ScenarioSpec("H5_sigmoid_a-0.03", "H5 sigmoid slope sweep", "hypothesis", {"platt_a": -0.03, "max_win_prob_cap": 0.80}, {}),
            ScenarioSpec("H6_tier_LEAN", "H6 tier floor LEAN+", "hypothesis", {}, {"tier_floor": "LEAN"}),
            ScenarioSpec("H6_tier_GOOD", "H6 tier floor GOOD+", "hypothesis", {}, {"tier_floor": "GOOD"}),
            ScenarioSpec("H6_tier_STRONG", "H6 tier floor STRONG", "hypothesis", {}, {"tier_floor": "STRONG"}),
            ScenarioSpec("H7_ev_005", "H7 EV floor 5%", "hypothesis", {"matchup_ev_threshold": 0.05}, {}),
            ScenarioSpec("H7_ev_006", "H7 EV floor 6%", "hypothesis", {"matchup_ev_threshold": 0.06}, {}),
            ScenarioSpec("H7_ev_007", "H7 EV floor 7%", "hypothesis", {"matchup_ev_threshold": 0.07}, {}),
            ScenarioSpec("H7_ev_008", "H7 EV floor 8%", "hypothesis", {"matchup_ev_threshold": 0.08}, {}),
            ScenarioSpec("H7_ev_009", "H7 EV floor 9%", "hypothesis", {"matchup_ev_threshold": 0.09}, {}),
            ScenarioSpec("H7_ev_010", "H7 EV floor 10%", "hypothesis", {"matchup_ev_threshold": 0.10}, {}),
            ScenarioSpec("H7_ev_011", "H7 EV floor 11%", "hypothesis", {"matchup_ev_threshold": 0.11}, {}),
            ScenarioSpec("H7_ev_012", "H7 EV floor 12%", "hypothesis", {"matchup_ev_threshold": 0.12}, {}),
            ScenarioSpec("H8_marketing_on", "H8 marketing gate ON", "hypothesis", {}, {"marketing_safe_required": True}),
            ScenarioSpec("H8_marketing_off", "H8 marketing gate OFF", "hypothesis", {}, {"marketing_safe_required": False}),
            ScenarioSpec("H9_exposure_cap_2", "H9 player exposure cap=2", "hypothesis", {}, {"max_player_exposure": 2}),
            ScenarioSpec("H9_exposure_cap_3", "H9 player exposure cap=3", "hypothesis", {}, {"max_player_exposure": 3}),
            ScenarioSpec("H10_odds_cap_300", "H10 odds quality cap +300", "hypothesis", {}, {"max_positive_odds": 300}),
            ScenarioSpec("H10_odds_cap_250", "H10 odds quality cap +250", "hypothesis", {}, {"max_positive_odds": 250}),
            ScenarioSpec("H11_raw_gap", "H11 raw composite gap", "hypothesis", {}, {}),
            ScenarioSpec("H11_gap_5", "H11 course-aware gap proxy", "hypothesis", {"min_composite_gap": 5.0}, {}),
            ScenarioSpec("H12_optuna_mo", "H12 multi-objective Optuna", "hypothesis", {}, {"optuna": "mo"}),
            ScenarioSpec("H13_segment_gate_on", "H13 segment gate momentum/form", "hypothesis", {}, {"segment_gate": True}),
            ScenarioSpec("H13_segment_gate_off", "H13 segment gate baseline", "hypothesis", {}, {"segment_gate": False}),
        ]
    )
    return specs


def _load_event_windows() -> dict[str, list[dict[str, Any]]]:
    events = load_historical_events(years=sorted(set(PRIMARY_YEARS + HOLDOUT_YEARS)))
    primary = [
        e
        for e in events
        if PRIMARY_DATE_START <= str(e.get("event_date", "")) <= PRIMARY_DATE_END
    ]
    holdout = [
        e
        for e in events
        if HOLDOUT_DATE_START <= str(e.get("event_date", "")) <= HOLDOUT_DATE_END
    ]
    windows = {
        "primary": primary,
        "holdout": holdout,
    }
    return windows


def _fit_platt_params(training_rows: list[dict[str, Any]]) -> tuple[float, float] | None:
    if LogisticRegression is None:
        return None
    if len(training_rows) < 120:
        return None
    x = [[float(row["composite_gap"])] for row in training_rows]
    y = [1 if row.get("won") else 0 for row in training_rows]
    if sum(y) in (0, len(y)):
        return None
    lr = LogisticRegression(C=1.0, solver="lbfgs")
    lr.fit(x, y)
    a = -float(lr.coef_[0][0])
    b = -float(lr.intercept_[0])
    return (a, b)


def _apply_filters(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    tier_order = {"LEAN": 0, "GOOD": 1, "STRONG": 2}
    out = list(rows)
    floor = filters.get("tier_floor")
    if floor:
        min_rank = tier_order.get(str(floor).upper(), 0)
        out = [r for r in out if tier_order.get(str(r.get("tier", "LEAN")).upper(), 0) >= min_rank]
    if "marketing_safe_required" in filters:
        if filters["marketing_safe_required"]:
            out = [r for r in out if bool(r.get("marketing_safe"))]
    max_positive_odds = filters.get("max_positive_odds")
    if max_positive_odds is not None:
        out = [r for r in out if not (int(r.get("odds", 0)) > int(max_positive_odds))]
    max_exposure = filters.get("max_player_exposure")
    if max_exposure:
        filtered: list[dict[str, Any]] = []
        exposure: dict[str, int] = {}
        for r in sorted(out, key=lambda row: float(row.get("ev", 0.0)), reverse=True):
            pk = str(r.get("player_key") or "")
            if not pk:
                continue
            if exposure.get(pk, 0) >= int(max_exposure):
                continue
            exposure[pk] = exposure.get(pk, 0) + 1
            filtered.append(r)
        out = filtered
    if filters.get("segment_gate"):
        out = [r for r in out if bool(r.get("momentum_aligned")) or abs(float(r.get("form_gap", 0.0))) >= 5.0]
    if "matchup_ev_threshold" in filters:
        ev_floor = float(filters["matchup_ev_threshold"])
        out = [r for r in out if float(r.get("ev", 0.0) or 0.0) >= ev_floor]
    return out


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "hit_rate_pct": 0.0,
            "roi_pct": 0.0,
            "brier": None,
            "drawdown_pct": 0.0,
            "clv_avg": None,
            "clv_bps": None,
        }
    wins = sum(1 for r in rows if r.get("won"))
    pnl = sum(float(r.get("payout", 0.0)) - float(r.get("wager", 0.0)) for r in rows)
    staked = sum(float(r.get("wager", 0.0)) for r in rows)
    brier = mean((float(r.get("model_prob", 0.0)) - (1.0 if r.get("won") else 0.0)) ** 2 for r in rows)
    clv_avg = mean(float(r.get("clv", 0.0)) for r in rows if r.get("clv") is not None)
    curve = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rows:
        curve += float(r.get("payout", 0.0)) - float(r.get("wager", 0.0))
        peak = max(peak, curve)
        max_dd = max(max_dd, peak - curve)
    dd_pct = (100.0 * max_dd / staked) if staked > 0 else 0.0
    return {
        "n": n,
        "hit_rate_pct": round(100.0 * wins / n, 2),
        "roi_pct": round(100.0 * pnl / staked, 2) if staked > 0 else 0.0,
        "brier": round(float(brier), 4),
        "drawdown_pct": round(dd_pct, 2),
        "clv_avg": round(float(clv_avg), 6),
        "clv_bps": round(float(clv_avg) * 10000.0, 2),
    }


def _collect_rows_for_window(
    *,
    events: list[dict[str, Any]],
    strategy: StrategyConfig,
    rolling_platt: bool,
    include_all_rows: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rolling_cache: dict[int, tuple[float, float] | None] = {}
    replay_cache_by_year: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        year = int(event["year"])
        if rolling_platt:
            if year not in rolling_cache:
                if year not in replay_cache_by_year:
                    train_events = [e for e in events if int(e["year"]) < year]
                    train_rows: list[dict[str, Any]] = []
                    for te in train_events:
                        tmp = StrategyConfig(**asdict(strategy))
                        tmp.platt_a = strategy.platt_a
                        tmp.platt_b = strategy.platt_b
                        train_rows.extend(
                            [
                                r
                                for r in replay_event(str(te["event_id"]), int(te["year"]), tmp)
                                if r.get("market") == "matchup" and float(r.get("ev", 0.0) or 0.0) > 0.0
                            ]
                        )
                    replay_cache_by_year[year] = train_rows
                rolling_cache[year] = _fit_platt_params(replay_cache_by_year[year])
        use_strategy = StrategyConfig(**asdict(strategy))
        if rolling_platt and rolling_cache.get(year):
            use_strategy.platt_a, use_strategy.platt_b = rolling_cache[year]  # type: ignore[misc]
        event_rows = replay_event(str(event["event_id"]), int(event["year"]), use_strategy)
        matchup_rows = [r for r in event_rows if r.get("market") == "matchup"]
        if not include_all_rows:
            matchup_rows = [r for r in matchup_rows if float(r.get("ev", 0.0) or 0.0) > 0.0]
        for row in matchup_rows:
            row["event_id"] = str(event["event_id"])
            row["year"] = int(event["year"])
        rows.extend(matchup_rows)
    return rows


def _run_scenario(spec: ScenarioSpec, windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    strategy = _baseline_strategy()
    effective_filters = dict(spec.filters)
    for k, v in spec.strategy_overrides.items():
        if k == "matchup_ev_threshold":
            # Keep replay in full-slate mode and apply EV floor in post-filtering.
            effective_filters["matchup_ev_threshold"] = float(v)
            continue
        setattr(strategy, k, v)
    strategy.matchup_ev_threshold = FULL_SLATE_EV_FLOOR
    strategy.matchup_require_positive_ev = False
    strategy.matchup_include_all_sides = True
    strategy.matchup_include_all_books = True

    result = {
        "scenario_id": spec.scenario_id,
        "title": spec.title,
        "family": spec.family,
        "strategy_overrides": spec.strategy_overrides,
        "filters": effective_filters,
        "unsupported_reason": spec.unsupported_reason,
        "notes": spec.notes,
        "windows": {},
    }

    for window_name, events in windows.items():
        raw_rows = _collect_rows_for_window(
            events=events,
            strategy=strategy,
            rolling_platt=bool(spec.filters.get("rolling_platt")),
            include_all_rows=True,
        )
        filtered_rows = _apply_filters(raw_rows, effective_filters)
        result["windows"][window_name] = {
            "raw": _metrics(raw_rows),
            "filtered": _metrics(filtered_rows),
            "events": len(events),
            "segment": {
                "marketing_safe_n": sum(1 for r in filtered_rows if bool(r.get("marketing_safe"))),
                "strong_tier_n": sum(1 for r in filtered_rows if str(r.get("tier", "")).upper() == "STRONG"),
                "good_tier_n": sum(1 for r in filtered_rows if str(r.get("tier", "")).upper() == "GOOD"),
                "lean_tier_n": sum(1 for r in filtered_rows if str(r.get("tier", "")).upper() == "LEAN"),
                "momentum_aligned_n": sum(1 for r in filtered_rows if bool(r.get("momentum_aligned"))),
            },
        }
    return result


def _pareto_candidates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for r in results:
        f = r["windows"]["primary"]["filtered"]
        if int(f.get("n", 0)) < MIN_CANDIDATE_N:
            continue
        if f.get("brier") is None:
            continue
        rows.append(
            {
                "scenario_id": r["scenario_id"],
                "hit_rate_pct": float(f["hit_rate_pct"]),
                "roi_pct": float(f["roi_pct"]),
                "brier": float(f["brier"]),
                "n": int(f["n"]),
            }
        )
    pareto: list[dict[str, Any]] = []
    for candidate in rows:
        dominated = False
        for other in rows:
            if other["scenario_id"] == candidate["scenario_id"]:
                continue
            if (
                other["hit_rate_pct"] >= candidate["hit_rate_pct"]
                and other["roi_pct"] >= candidate["roi_pct"]
                and other["brier"] <= candidate["brier"]
                and (
                    other["hit_rate_pct"] > candidate["hit_rate_pct"]
                    or other["roi_pct"] > candidate["roi_pct"]
                    or other["brier"] < candidate["brier"]
                )
            ):
                dominated = True
                break
        if not dominated:
            pareto.append(candidate)
    pareto.sort(key=lambda x: (x["roi_pct"], x["hit_rate_pct"], -x["brier"]), reverse=True)
    return pareto


def _pareto_trial_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [r for r in records if r.get("primary_brier") is not None]
    frontier: list[dict[str, Any]] = []
    for candidate in rows:
        dominated = False
        for other in rows:
            if other["number"] == candidate["number"]:
                continue
            if (
                float(other["primary_roi_pct"]) >= float(candidate["primary_roi_pct"])
                and float(other["primary_hit_rate_pct"]) >= float(candidate["primary_hit_rate_pct"])
                and float(other["primary_brier"]) <= float(candidate["primary_brier"])
                and float(other.get("primary_drawdown_pct", 0.0)) <= float(candidate.get("primary_drawdown_pct", 0.0))
                and (
                    float(other["primary_roi_pct"]) > float(candidate["primary_roi_pct"])
                    or float(other["primary_hit_rate_pct"]) > float(candidate["primary_hit_rate_pct"])
                    or float(other["primary_brier"]) < float(candidate["primary_brier"])
                    or float(other.get("primary_drawdown_pct", 0.0)) < float(candidate.get("primary_drawdown_pct", 0.0))
                )
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    frontier.sort(
        key=lambda r: (
            float(r["primary_roi_pct"]),
            float(r["primary_hit_rate_pct"]),
            -float(r["primary_brier"]),
            -float(r.get("primary_drawdown_pct", 0.0)),
        ),
        reverse=True,
    )
    return frontier


def _window_metadata(windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, events in windows.items():
        dates = sorted(str(e.get("event_date", "")) for e in events if e.get("event_date"))
        out[name] = {
            "n_events": len(events),
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
            "event_ids": [str(e.get("event_id")) for e in events],
        }
    return out


def _run_pit_audit(windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    conn = db.get_conn()
    event_rows: list[dict[str, Any]] = []
    fail_count = 0
    for window_name, events in windows.items():
        for event in events:
            event_id = str(event["event_id"])
            year = int(event["year"])
            event_date = str(event.get("event_date") or "")
            has_leakage = False
            leakage_error = None
            try:
                assert_checkpoint_temporal_integrity(event_id, year, event_date)
            except Exception as exc:  # pragma: no cover - safety net
                has_leakage = True
                leakage_error = str(exc)
                fail_count += 1

            pit_stats = conn.execute(
                """
                SELECT
                    COUNT(*) AS pit_players,
                    SUM(
                        CASE
                            WHEN rounds_used > (
                                SELECT COUNT(*)
                                FROM rounds r
                                WHERE r.player_key = p.player_key
                                  AND r.sg_total IS NOT NULL
                                  AND r.event_completed < ?
                            )
                            THEN 1 ELSE 0
                        END
                    ) AS leakage_players
                FROM pit_rolling_stats p
                WHERE p.event_id = ? AND p.year = ?
                """,
                (event_date, event_id, year),
            ).fetchone()
            event_rows.append(
                {
                    "window": window_name,
                    "event_id": event_id,
                    "year": year,
                    "event_date": event_date,
                    "pit_players": int(pit_stats["pit_players"] or 0) if pit_stats else 0,
                    "leakage_players": int(pit_stats["leakage_players"] or 0) if pit_stats else 0,
                    "assert_checkpoint_temporal_integrity_passed": not has_leakage,
                    "leakage_error": leakage_error,
                }
            )
    conn.close()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_contract": {
            "primary": {"start_date": PRIMARY_DATE_START, "end_date": PRIMARY_DATE_END},
            "holdout": {"start_date": HOLDOUT_DATE_START, "end_date": HOLDOUT_DATE_END},
        },
        "window_metadata": _window_metadata(windows),
        "events_checked": len(event_rows),
        "events_failed": fail_count,
        "status": "pass" if fail_count == 0 else "fail",
        "event_audit": event_rows,
    }


def _run_full_slate_coverage_audit(windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    conn = db.get_conn()
    window_event_keys = {
        (str(event["event_id"]), int(event["year"]))
        for events in windows.values()
        for event in events
    }
    source_rows = conn.execute(
        """
        SELECT
            event_id,
            year,
            book,
            bet_type AS market,
            COUNT(*) AS matchup_rows,
            SUM(CASE WHEN p1_close IS NULL AND p1_open IS NULL THEN 1 ELSE 0 END) AS missing_p1_odds,
            SUM(CASE WHEN p2_close IS NULL AND p2_open IS NULL THEN 1 ELSE 0 END) AS missing_p2_odds,
            SUM(CASE WHEN p1_outcome_text IS NULL OR TRIM(p1_outcome_text) = '' THEN 1 ELSE 0 END) AS missing_p1_outcome,
            SUM(CASE WHEN p2_outcome_text IS NULL OR TRIM(p2_outcome_text) = '' THEN 1 ELSE 0 END) AS missing_p2_outcome
        FROM historical_matchup_odds
        GROUP BY event_id, year, book, market
        ORDER BY year, event_id, book, market
        """
    ).fetchall()
    conn.close()

    baseline = _baseline_strategy()
    replay_rows = []
    for name, events in windows.items():
        rows = _collect_rows_for_window(
            events=events,
            strategy=baseline,
            rolling_platt=False,
            include_all_rows=True,
        )
        for row in rows:
            replay_rows.append(
                {
                    "window": name,
                    "event_id": str(row.get("event_id")),
                    "year": int(row.get("year", 0)),
                    "book": str(row.get("book") or ""),
                    "market": str(row.get("matchup_type") or ""),
                    "side": str(row.get("player_key") or ""),
                }
            )

    source_grouped = []
    for r in source_rows:
        event_key = (str(r["event_id"]), int(r["year"]))
        if event_key not in window_event_keys:
            continue
        source_grouped.append(
            {
                "event_id": str(r["event_id"]),
                "year": int(r["year"]),
                "book": str(r["book"] or ""),
                "market": str(r["market"] or ""),
                "matchup_rows": int(r["matchup_rows"] or 0),
                "side_rows": int(r["matchup_rows"] or 0) * 2,
                "missing_p1_odds": int(r["missing_p1_odds"] or 0),
                "missing_p2_odds": int(r["missing_p2_odds"] or 0),
                "missing_p1_outcome": int(r["missing_p1_outcome"] or 0),
                "missing_p2_outcome": int(r["missing_p2_outcome"] or 0),
            }
        )

    replay_group_map: dict[tuple[str, int, str, str], int] = {}
    for row in replay_rows:
        key = (row["event_id"], row["year"], row["book"], row["market"])
        replay_group_map[key] = replay_group_map.get(key, 0) + 1
    replay_grouped = [
        {
            "event_id": k[0],
            "year": k[1],
            "book": k[2],
            "market": k[3],
            "evaluated_side_rows": v,
        }
        for k, v in sorted(replay_group_map.items())
    ]
    unmatched_source_groups = []
    for row in source_grouped:
        key = (row["event_id"], row["year"], row["book"], row["market"])
        replayed = replay_group_map.get(key, 0)
        if replayed < row["side_rows"]:
            unmatched_source_groups.append(
                {
                    "event_id": row["event_id"],
                    "year": row["year"],
                    "book": row["book"],
                    "market": row["market"],
                    "source_side_rows": row["side_rows"],
                    "replayed_side_rows": replayed,
                    "missing_side_rows": row["side_rows"] - replayed,
                }
            )

    source_total_side_rows = sum(r["side_rows"] for r in source_grouped)
    replay_total_side_rows = sum(r["evaluated_side_rows"] for r in replay_grouped)
    coverage_ratio = (replay_total_side_rows / source_total_side_rows) if source_total_side_rows else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_contract": {
            "primary": {"start_date": PRIMARY_DATE_START, "end_date": PRIMARY_DATE_END},
            "holdout": {"start_date": HOLDOUT_DATE_START, "end_date": HOLDOUT_DATE_END},
        },
        "window_metadata": _window_metadata(windows),
        "source_group_counts": source_grouped,
        "replay_group_counts": replay_grouped,
        "source_total_side_rows": source_total_side_rows,
        "replay_total_side_rows": replay_total_side_rows,
        "coverage_ratio": round(coverage_ratio, 6),
        "source_group_count": len(source_grouped),
        "replay_group_count": len(replay_grouped),
        "unmatched_source_groups": unmatched_source_groups,
        "missingness_diagnostics": {
            "missing_p1_odds_rows": sum(r["missing_p1_odds"] for r in source_grouped),
            "missing_p2_odds_rows": sum(r["missing_p2_odds"] for r in source_grouped),
            "missing_p1_outcome_rows": sum(r["missing_p1_outcome"] for r in source_grouped),
            "missing_p2_outcome_rows": sum(r["missing_p2_outcome"] for r in source_grouped),
        },
    }


def _render_pit_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# PIT audit",
        "",
        f"- Generated at: `{audit['generated_at']}`",
        f"- Status: `{audit['status']}`",
        f"- Events checked: `{audit['events_checked']}`",
        f"- Events failed: `{audit['events_failed']}`",
        "",
        "## Window contract",
        "",
        f"- Primary: `{PRIMARY_DATE_START}` to `{PRIMARY_DATE_END}`",
        f"- Holdout: `{HOLDOUT_DATE_START}` to `{HOLDOUT_DATE_END}`",
        "",
        "## Event-level audit",
        "",
        "| Window | Event | Year | Date | PIT players | Leakage players | Passed |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for row in audit.get("event_audit", []):
        lines.append(
            f"| {row['window']} | {row['event_id']} | {row['year']} | {row['event_date']} | "
            f"{row['pit_players']} | {row['leakage_players']} | {row['assert_checkpoint_temporal_integrity_passed']} |"
        )
    return "\n".join(lines) + "\n"


def _render_coverage_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Full-slate coverage audit",
        "",
        f"- Generated at: `{audit['generated_at']}`",
        f"- Source side rows: `{audit['source_total_side_rows']}`",
        f"- Replay evaluated side rows: `{audit['replay_total_side_rows']}`",
        f"- Coverage ratio: `{audit['coverage_ratio']}`",
        f"- Source groups: `{audit.get('source_group_count')}`",
        f"- Replay groups: `{audit.get('replay_group_count')}`",
        f"- Unmatched source groups: `{len(audit.get('unmatched_source_groups', []))}`",
        "",
        "## Missingness diagnostics",
        "",
    ]
    for key, value in (audit.get("missingness_diagnostics") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Source counts by event/year/book/market",
            "",
            "| Event | Year | Book | Market | Matchup rows | Side rows | Missing p1 odds | Missing p2 odds | Missing p1 outcome | Missing p2 outcome |",
            "|---:|---:|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in audit.get("source_group_counts", []):
        lines.append(
            f"| {row['event_id']} | {row['year']} | {row['book']} | {row['market']} | "
            f"{row['matchup_rows']} | {row['side_rows']} | {row['missing_p1_odds']} | {row['missing_p2_odds']} | "
            f"{row['missing_p1_outcome']} | {row['missing_p2_outcome']} |"
        )
    return "\n".join(lines) + "\n"


def _build_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Matchup tuning report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(
        f"- Primary window: `{payload['window_contract']['primary']['start_date']}` → "
        f"`{payload['window_contract']['primary']['end_date']}`"
    )
    lines.append(
        f"- Holdout window: `{payload['window_contract']['holdout']['start_date']}` → "
        f"`{payload['window_contract']['holdout']['end_date']}`"
    )
    lines.append("- Flat stake: `1u`")
    lines.append("")
    lines.append("## Winner ranking")
    lines.append("")
    for rank, row in enumerate(payload["ranking"][:10], start=1):
        lines.append(
            f"{rank}. `{row['scenario_id']}` — primary ROI `{row['primary_roi_pct']}%`, "
            f"hit `{row['primary_hit_rate_pct']}%`, brier `{row['primary_brier']}`, "
            f"clv `{row['primary_clv_bps']}` bps, drawdown `{row['primary_drawdown_pct']}%`, "
            f"holdout ROI `{row['holdout_roi_pct']}%`, n `{row['primary_n']}`"
        )
    lines.append("")
    lines.append("## Pareto frontier (primary window)")
    lines.append("")
    for row in payload["pareto_frontier"]:
        lines.append(
            f"- `{row['scenario_id']}`: ROI `{row['roi_pct']}%`, hit `{row['hit_rate_pct']}%`, "
            f"brier `{row['brier']}`, n `{row['n']}`"
        )
    lines.append("")
    lines.append("## Full scenario table")
    lines.append("")
    lines.append("| Scenario | Family | Primary ROI | Primary Hit | Primary Brier | Primary CLV (bps) | Primary DD | Primary n | Holdout ROI | Holdout Hit | Holdout Brier | Holdout CLV (bps) | Holdout DD | Holdout n |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["ranking"]:
        lines.append(
            f"| `{row['scenario_id']}` | {row['family']} | {row['primary_roi_pct']} | {row['primary_hit_rate_pct']} | "
            f"{row['primary_brier']} | {row['primary_clv_bps']} | {row['primary_drawdown_pct']} | {row['primary_n']} | "
            f"{row['holdout_roi_pct']} | {row['holdout_hit_rate_pct']} | {row['holdout_brier']} | {row['holdout_clv_bps']} | "
            f"{row['holdout_drawdown_pct']} | {row['holdout_n']} |"
        )
    unsupported = [r for r in payload["results"] if r.get("unsupported_reason")]
    if unsupported:
        lines.append("")
        lines.append("## Unsupported / non-identifiable dimensions")
        lines.append("")
        for row in unsupported:
            lines.append(f"- `{row['scenario_id']}`: {row['unsupported_reason']}")
    lines.append("")
    lines.append("## Selection gate check")
    lines.append("")
    winner = payload.get("credible_constrained_winner") or {}
    if winner:
        lines.append(
            f"- Credible constrained winner: `{winner.get('scenario_id')}` "
            f"(primary n={winner.get('primary_n')}, holdout n={winner.get('holdout_n')})"
        )
    else:
        lines.append("- No candidate met constrained sample-size gates.")
    max_roi_candidate = payload.get("max_roi_candidate")
    if max_roi_candidate:
        lines.append(
            f"- Max ROI candidate (unconstrained): `{max_roi_candidate['scenario_id']}` "
            f"(primary ROI `{max_roi_candidate['primary_roi_pct']}%`, n={max_roi_candidate['primary_n']})"
        )
    max_roi = payload.get("max_roi_search") or {}
    if max_roi.get("status") == "ok":
        lines.append("")
        lines.append("## Deep max-ROI search")
        lines.append("")
        lines.append(f"- Trials: `{max_roi.get('n_trials')}`")
        lines.append(f"- Ranked trials captured: `{len(max_roi.get('all_primary_roi_ranked_trials', []))}`")
        lines.append(f"- Pareto trial count: `{len(max_roi.get('pareto_frontier_trials', []))}`")
        unconstrained = max_roi.get("best_primary_roi_unconstrained")
        constrained = max_roi.get("best_primary_roi_constrained")
        if unconstrained:
            lines.append(
                "- Best unconstrained primary ROI: "
                f"`{unconstrained['primary_roi_pct']}%` (primary n={unconstrained['primary_n']}, "
                f"holdout ROI={unconstrained['holdout_roi_pct']}%, holdout n={unconstrained['holdout_n']})"
            )
        if constrained:
            lines.append(
                "- Best constrained primary ROI: "
                f"`{constrained['primary_roi_pct']}%` (primary n={constrained['primary_n']}, "
                f"holdout ROI={constrained['holdout_roi_pct']}%, holdout n={constrained['holdout_n']})"
            )
        elif unconstrained:
            lines.append("- No candidate met constrained sample gate in deep search.")
    return "\n".join(lines) + "\n"


def _optuna_matchup_mo(baseline: StrategyConfig, n_trials: int, windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if optuna is None:
        return {"status": "skipped", "reason": "optuna not installed"}
    study = optuna.create_study(
        study_name=f"matchup_lab_mo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        directions=["maximize", "maximize", "minimize", "minimize"],
    )

    def objective(trial: optuna.Trial) -> tuple[float, float, float, float]:
        candidate = StrategyConfig(**asdict(baseline))
        candidate.matchup_ev_threshold = trial.suggest_float("matchup_ev_threshold", 0.05, 0.12, step=0.01)
        candidate.platt_a = trial.suggest_float("platt_a", -0.12, -0.02, step=0.005)
        candidate.platt_b = trial.suggest_float("platt_b", -0.20, 0.20, step=0.01)
        candidate.min_composite_gap = trial.suggest_float("min_composite_gap", 0.0, 8.0, step=0.5)
        candidate.max_win_prob_cap = trial.suggest_float("max_win_prob_cap", 0.65, 0.90, step=0.01)
        rows = _collect_rows_for_window(events=windows["primary"], strategy=candidate, rolling_platt=False)
        rows = _apply_filters(rows, {})
        m = _metrics(rows)
        if int(m["n"]) < MIN_CANDIDATE_N or m["brier"] is None:
            return (-1e9, -1e9, 1e9, 1e9)
        return (float(m["roi_pct"]), float(m["hit_rate_pct"]), float(m["brier"]), float(m["drawdown_pct"]))

    study.optimize(objective, n_trials=n_trials, n_jobs=1, show_progress_bar=False)
    best = []
    for t in study.best_trials:
        best.append({"number": t.number, "values": list(t.values or []), "params": t.params})
    return {
        "status": "ok",
        "study_name": study.study_name,
        "n_trials": len([t for t in study.trials if t.state.name == "COMPLETE"]),
        "pareto": best,
    }


def _optuna_max_roi_search(
    baseline: StrategyConfig,
    n_trials: int,
    windows: dict[str, list[dict[str, Any]]],
    *,
    study_name: str,
    storage_path: str,
) -> dict[str, Any]:
    if optuna is None:
        return {"status": "skipped", "reason": "optuna not installed"}
    if n_trials <= 0:
        return {"status": "skipped", "reason": "n_trials <= 0"}

    storage_file = Path(storage_path)
    storage_file.parent.mkdir(parents=True, exist_ok=True)
    study = optuna.create_study(
        study_name=study_name,
        storage=f"sqlite:///{storage_file.resolve()}",
        load_if_exists=True,
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    def objective(trial: optuna.Trial) -> float:
        candidate = StrategyConfig(**asdict(baseline))
        candidate.matchup_ev_threshold = FULL_SLATE_EV_FLOOR
        candidate.platt_a = trial.suggest_float("platt_a", -0.14, -0.01, step=0.005)
        candidate.platt_b = trial.suggest_float("platt_b", -0.25, 0.25, step=0.01)
        candidate.min_composite_gap = trial.suggest_float("min_composite_gap", 0.0, 10.0, step=0.5)
        candidate.max_win_prob_cap = trial.suggest_float("max_win_prob_cap", 0.60, 0.95, step=0.01)
        candidate.model_variant = trial.suggest_categorical("model_variant", ["baseline", "v5"])
        candidate.matchup_include_all_sides = True
        candidate.matchup_require_positive_ev = False
        candidate.matchup_include_all_books = True
        sub_logits = [
            trial.suggest_float("logit_w_sub_course_fit", -3.0, 3.0),
            trial.suggest_float("logit_w_sub_form", -3.0, 3.0),
            trial.suggest_float("logit_w_sub_momentum", -3.0, 3.0),
        ]
        sub_weights = _softmax_weights(sub_logits)
        candidate.w_sub_course_fit = round(sub_weights[0], 4)
        candidate.w_sub_form = round(sub_weights[1], 4)
        candidate.w_sub_momentum = round(sub_weights[2], 4)

        filters: dict[str, Any] = {
            "matchup_ev_threshold": trial.suggest_float("matchup_ev_threshold", 0.03, 0.14, step=0.01)
        }
        tier_floor = trial.suggest_categorical("tier_floor", ["LEAN", "GOOD", "STRONG"])
        if tier_floor != "LEAN":
            filters["tier_floor"] = tier_floor
        if trial.suggest_categorical("marketing_safe_required", [False, True]):
            filters["marketing_safe_required"] = True

        odds_cap = trial.suggest_categorical("max_positive_odds", [-1, 400, 350, 300, 250, 200])
        if int(odds_cap) > 0:
            filters["max_positive_odds"] = int(odds_cap)
        exposure_cap = trial.suggest_categorical("max_player_exposure", [0, 2, 3])
        if int(exposure_cap) > 0:
            filters["max_player_exposure"] = int(exposure_cap)
        if trial.suggest_categorical("segment_gate", [False, True]):
            filters["segment_gate"] = True
        rolling_platt = trial.suggest_categorical("rolling_platt", [False, True])

        form_logits = [
            trial.suggest_float("logit_form_sg_tot", -3.0, 3.0),
            trial.suggest_float("logit_form_sg_app", -3.0, 3.0),
            trial.suggest_float("logit_form_sg_ott", -3.0, 3.0),
            trial.suggest_float("logit_form_sg_arg", -3.0, 3.0),
            trial.suggest_float("logit_form_sg_putt", -3.0, 3.0),
        ]
        form_weights = _softmax_weights(form_logits)
        course_logits = [
            trial.suggest_float("logit_course_sg_tot", -3.0, 3.0),
            trial.suggest_float("logit_course_sg_app", -3.0, 3.0),
            trial.suggest_float("logit_course_sg_ott", -3.0, 3.0),
            trial.suggest_float("logit_course_sg_arg", -3.0, 3.0),
            trial.suggest_float("logit_course_sg_putt", -3.0, 3.0),
            trial.suggest_float("logit_course_finish", -3.0, 3.0),
        ]
        course_weights = _softmax_weights(course_logits)
        original_weights = dict(config.DEFAULT_WEIGHTS)
        config.DEFAULT_WEIGHTS["form_sg_tot"] = round(form_weights[0], 4)
        config.DEFAULT_WEIGHTS["form_sg_app"] = round(form_weights[1], 4)
        config.DEFAULT_WEIGHTS["form_sg_ott"] = round(form_weights[2], 4)
        config.DEFAULT_WEIGHTS["form_sg_arg"] = round(form_weights[3], 4)
        config.DEFAULT_WEIGHTS["form_sg_putt"] = round(form_weights[4], 4)
        config.DEFAULT_WEIGHTS["course_sg_tot"] = round(course_weights[0], 4)
        config.DEFAULT_WEIGHTS["course_sg_app"] = round(course_weights[1], 4)
        config.DEFAULT_WEIGHTS["course_sg_ott"] = round(course_weights[2], 4)
        config.DEFAULT_WEIGHTS["course_sg_arg"] = round(course_weights[3], 4)
        config.DEFAULT_WEIGHTS["course_sg_putt"] = round(course_weights[4], 4)
        config.DEFAULT_WEIGHTS["course_par_eff"] = round(course_weights[5], 4)

        try:
            primary_rows = _collect_rows_for_window(
                events=windows["primary"],
                strategy=candidate,
                rolling_platt=rolling_platt,
                include_all_rows=True,
            )
            holdout_rows = _collect_rows_for_window(
                events=windows["holdout"],
                strategy=candidate,
                rolling_platt=rolling_platt,
                include_all_rows=True,
            )
            primary_filtered = _apply_filters(primary_rows, filters)
            holdout_filtered = _apply_filters(holdout_rows, filters)
            pm = _metrics(primary_filtered)
            hm = _metrics(holdout_filtered)
        finally:
            config.DEFAULT_WEIGHTS.clear()
            config.DEFAULT_WEIGHTS.update(original_weights)

        trial.set_user_attr("primary_n", int(pm["n"]))
        trial.set_user_attr("primary_hit_rate_pct", float(pm["hit_rate_pct"]))
        trial.set_user_attr("primary_roi_pct", float(pm["roi_pct"]))
        trial.set_user_attr("primary_brier", pm["brier"])
        trial.set_user_attr("primary_drawdown_pct", float(pm["drawdown_pct"]))
        trial.set_user_attr("primary_clv_bps", pm["clv_bps"])
        trial.set_user_attr("holdout_n", int(hm["n"]))
        trial.set_user_attr("holdout_hit_rate_pct", float(hm["hit_rate_pct"]))
        trial.set_user_attr("holdout_roi_pct", float(hm["roi_pct"]))
        trial.set_user_attr("holdout_brier", hm["brier"])
        trial.set_user_attr("holdout_drawdown_pct", float(hm["drawdown_pct"]))
        trial.set_user_attr("holdout_clv_bps", hm["clv_bps"])
        trial.set_user_attr("rolling_platt", bool(rolling_platt))
        trial.set_user_attr("filters", filters)
        trial.set_user_attr("w_sub", {
            "course_fit": candidate.w_sub_course_fit,
            "form": candidate.w_sub_form,
            "momentum": candidate.w_sub_momentum,
        })
        trial.set_user_attr("form_sg_weights", {
            "tot": round(form_weights[0], 4),
            "app": round(form_weights[1], 4),
            "ott": round(form_weights[2], 4),
            "arg": round(form_weights[3], 4),
            "putt": round(form_weights[4], 4),
        })
        trial.set_user_attr("course_sg_weights", {
            "tot": round(course_weights[0], 4),
            "app": round(course_weights[1], 4),
            "ott": round(course_weights[2], 4),
            "arg": round(course_weights[3], 4),
            "putt": round(course_weights[4], 4),
            "finish": round(course_weights[5], 4),
        })

        primary_n = int(pm["n"])
        holdout_n = int(hm["n"])
        if primary_n < 80 or holdout_n < 40:
            return -1e9
        # maximize primary ROI, but discourage holdout collapse
        score = float(pm["roi_pct"]) + 0.20 * float(hm["roi_pct"])
        if primary_n >= 250:
            score += 0.25
        if holdout_n >= 200:
            score += 0.25
        return score

    study.optimize(objective, n_trials=n_trials, n_jobs=1, show_progress_bar=False)
    complete = [t for t in study.trials if t.state.name == "COMPLETE" and t.value is not None]
    complete.sort(key=lambda t: float(t.user_attrs.get("primary_roi_pct", -1e9)), reverse=True)

    def _trial_record(t: Any) -> dict[str, Any]:
        return {
            "number": int(t.number),
            "objective_value": float(t.value),
            "params": dict(t.params),
            "primary_n": int(t.user_attrs.get("primary_n", 0)),
            "primary_hit_rate_pct": float(t.user_attrs.get("primary_hit_rate_pct", 0.0)),
            "primary_roi_pct": float(t.user_attrs.get("primary_roi_pct", 0.0)),
            "primary_brier": t.user_attrs.get("primary_brier"),
            "primary_drawdown_pct": float(t.user_attrs.get("primary_drawdown_pct", 0.0)),
            "primary_clv_bps": t.user_attrs.get("primary_clv_bps"),
            "holdout_n": int(t.user_attrs.get("holdout_n", 0)),
            "holdout_hit_rate_pct": float(t.user_attrs.get("holdout_hit_rate_pct", 0.0)),
            "holdout_roi_pct": float(t.user_attrs.get("holdout_roi_pct", 0.0)),
            "holdout_brier": t.user_attrs.get("holdout_brier"),
            "holdout_drawdown_pct": float(t.user_attrs.get("holdout_drawdown_pct", 0.0)),
            "holdout_clv_bps": t.user_attrs.get("holdout_clv_bps"),
            "filters": t.user_attrs.get("filters", {}),
            "rolling_platt": bool(t.user_attrs.get("rolling_platt", False)),
        }

    all_ranked = [_trial_record(t) for t in complete]
    best_unconstrained = all_ranked[0] if all_ranked else None
    constrained = [
        t
        for t in complete
        if int(t.user_attrs.get("primary_n", 0)) >= 250 and int(t.user_attrs.get("holdout_n", 0)) >= 200
    ]
    best_constrained = _trial_record(constrained[0]) if constrained else None
    pareto_trials = _pareto_trial_records(all_ranked)

    return {
        "status": "ok",
        "study_name": study.study_name,
        "n_trials": len(complete),
        "n_trials_total_in_study": len([t for t in study.trials if t.state.name == "COMPLETE"]),
        "storage_path": str(storage_file),
        "best_primary_roi_unconstrained": best_unconstrained,
        "best_primary_roi_constrained": best_constrained,
        "top_primary_roi_trials": all_ranked[:20],
        "all_primary_roi_ranked_trials": all_ranked,
        "pareto_frontier_trials": pareto_trials,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run matchup lab research sweep matrix and holdout report")
    parser.add_argument("--db-path", default="/opt/golf-model/data/golf.db")
    parser.add_argument("--out-dir", default="output/research")
    parser.add_argument("--run-optuna-trials", type=int, default=0, help="Run additional matchup MO optuna trials")
    parser.add_argument("--run-max-roi-trials", type=int, default=0, help="Run deep scalar ROI search trials")
    parser.add_argument("--max-roi-study-name", default="matchup_lab_max_roi_deep", help="Persistent study name for max ROI search")
    parser.add_argument("--max-roi-storage-path", default="output/research/optuna/max_roi_studies.db", help="SQLite storage path for persistent max ROI study")
    parser.add_argument("--only-max-roi", action="store_true", help="Skip matrix sweeps and run only deep max-ROI study")
    args = parser.parse_args()

    db.DB_PATH = args.db_path
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    windows = _load_event_windows()
    specs = _all_specs()
    results: list[dict[str, Any]] = []
    pareto: list[dict[str, Any]] = []
    ranking: list[dict[str, Any]] = []
    credible_winner = None

    if not args.only_max_roi:
        results = [_run_scenario(spec, windows) for spec in specs if spec.filters.get("optuna") is None]
        pareto = _pareto_candidates(results)
        for r in results:
            p = r["windows"]["primary"]["filtered"]
            h = r["windows"]["holdout"]["filtered"]
            ranking.append(
                {
                    "scenario_id": r["scenario_id"],
                    "family": r["family"],
                    "primary_roi_pct": p["roi_pct"],
                    "primary_hit_rate_pct": p["hit_rate_pct"],
                    "primary_brier": p["brier"],
                    "primary_clv_bps": p["clv_bps"],
                    "primary_drawdown_pct": p["drawdown_pct"],
                    "primary_n": p["n"],
                    "holdout_roi_pct": h["roi_pct"],
                    "holdout_hit_rate_pct": h["hit_rate_pct"],
                    "holdout_brier": h["brier"],
                    "holdout_clv_bps": h["clv_bps"],
                    "holdout_drawdown_pct": h["drawdown_pct"],
                    "holdout_n": h["n"],
                }
            )
        ranking.sort(key=lambda x: (x["primary_roi_pct"], x["primary_hit_rate_pct"], -float(x["primary_brier"] or 9e9)), reverse=True)

        baseline = next((r for r in results if r["scenario_id"] == "E0"), None)
        if baseline:
            b_primary = baseline["windows"]["primary"]["filtered"]
            b_holdout = baseline["windows"]["holdout"]["filtered"]
            for row in ranking:
                if row["scenario_id"] == "E0":
                    continue
                if row["primary_n"] < MIN_WIREUP_N or row["holdout_n"] < MIN_CANDIDATE_N:
                    continue
                improves_primary = row["primary_roi_pct"] >= b_primary["roi_pct"] and row["primary_hit_rate_pct"] >= b_primary["hit_rate_pct"]
                improves_holdout = row["holdout_roi_pct"] >= b_holdout["roi_pct"]
                brier_ok = (row["primary_brier"] is None or b_primary["brier"] is None or row["primary_brier"] <= b_primary["brier"])
                if improves_primary and improves_holdout and brier_ok:
                    credible_winner = row
                    break

    optuna_summary = None
    if args.run_optuna_trials > 0 and not args.only_max_roi:
        optuna_summary = _optuna_matchup_mo(_baseline_strategy(), args.run_optuna_trials, windows)
    max_roi_search = _optuna_max_roi_search(
        _baseline_strategy(),
        args.run_max_roi_trials,
        windows,
        study_name=args.max_roi_study_name,
        storage_path=args.max_roi_storage_path,
    )
    max_roi_candidate = ranking[0] if ranking else None
    pit_audit = _run_pit_audit(windows)
    coverage_audit = _run_full_slate_coverage_audit(windows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": args.db_path,
        "primary_years": PRIMARY_YEARS,
        "holdout_years": HOLDOUT_YEARS,
        "window_contract": {
            "primary": {"start_date": PRIMARY_DATE_START, "end_date": PRIMARY_DATE_END},
            "holdout": {"start_date": HOLDOUT_DATE_START, "end_date": HOLDOUT_DATE_END},
        },
        "window_metadata": _window_metadata(windows),
        "minimum_candidate_n": MIN_CANDIDATE_N,
        "minimum_wireup_n": MIN_WIREUP_N,
        "results": results,
        "pareto_frontier": pareto,
        "ranking": ranking,
        "max_roi_candidate": max_roi_candidate,
        "credible_constrained_winner": credible_winner,
        "optuna_matchup_mo": optuna_summary,
        "max_roi_search": max_roi_search,
        "only_max_roi_mode": bool(args.only_max_roi),
        "pit_audit": {
            "status": pit_audit["status"],
            "events_checked": pit_audit["events_checked"],
            "events_failed": pit_audit["events_failed"],
        },
        "coverage_audit": {
            "coverage_ratio": coverage_audit["coverage_ratio"],
            "source_total_side_rows": coverage_audit["source_total_side_rows"],
            "replay_total_side_rows": coverage_audit["replay_total_side_rows"],
        },
    }

    json_path = out_dir / f"matchup_tuning_{stamp}.json"
    md_path = out_dir / f"matchup_tuning_{stamp}.md"
    pit_json_path = out_dir / f"pit_audit_{stamp}.json"
    pit_md_path = out_dir / f"pit_audit_{stamp}.md"
    coverage_json_path = out_dir / f"full_slate_coverage_{stamp}.json"
    coverage_md_path = out_dir / f"full_slate_coverage_{stamp}.md"
    checkpoint_path = out_dir / f"optimization_checkpoint_{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(payload), encoding="utf-8")
    pit_json_path.write_text(json.dumps(pit_audit, indent=2), encoding="utf-8")
    pit_md_path.write_text(_render_pit_audit_markdown(pit_audit), encoding="utf-8")
    coverage_json_path.write_text(json.dumps(coverage_audit, indent=2), encoding="utf-8")
    coverage_md_path.write_text(_render_coverage_markdown(coverage_audit), encoding="utf-8")
    checkpoint_payload = {
        "generated_at": payload["generated_at"],
        "study_name": (max_roi_search or {}).get("study_name"),
        "n_trials": (max_roi_search or {}).get("n_trials"),
        "n_trials_total_in_study": (max_roi_search or {}).get("n_trials_total_in_study"),
        "storage_path": (max_roi_search or {}).get("storage_path"),
        "best_primary_roi_unconstrained": (max_roi_search or {}).get("best_primary_roi_unconstrained"),
        "best_primary_roi_constrained": (max_roi_search or {}).get("best_primary_roi_constrained"),
    }
    checkpoint_path.write_text(json.dumps(checkpoint_payload, indent=2), encoding="utf-8")

    if optuna_summary:
        ledger_path = out_dir / "ledger.jsonl"
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": payload["generated_at"], "source": "matchup_lab_optuna", "summary": optuna_summary}) + "\n")
    if max_roi_search and max_roi_search.get("status") == "ok":
        ledger_path = out_dir / "ledger.jsonl"
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": payload["generated_at"], "source": "matchup_lab_max_roi", "summary": max_roi_search}) + "\n")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {pit_json_path}")
    print(f"Wrote {pit_md_path}")
    print(f"Wrote {coverage_json_path}")
    print(f"Wrote {coverage_md_path}")
    print(f"Wrote {checkpoint_path}")
    if credible_winner:
        print(
            f"winner={credible_winner['scenario_id']} primary_roi={credible_winner['primary_roi_pct']} "
            f"primary_hit={credible_winner['primary_hit_rate_pct']} holdout_roi={credible_winner['holdout_roi_pct']}"
        )
    else:
        print("winner=none")
    if max_roi_search and max_roi_search.get("status") == "ok":
        best_unconstrained = max_roi_search.get("best_primary_roi_unconstrained")
        best_constrained = max_roi_search.get("best_primary_roi_constrained")
        if best_unconstrained:
            print(
                "max_primary_roi_unconstrained="
                f"{best_unconstrained['primary_roi_pct']} "
                f"n={best_unconstrained['primary_n']} "
                f"holdout_roi={best_unconstrained['holdout_roi_pct']}"
            )
        if best_constrained:
            print(
                "max_primary_roi_constrained="
                f"{best_constrained['primary_roi_pct']} "
                f"n={best_constrained['primary_n']} "
                f"holdout_roi={best_constrained['holdout_roi_pct']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
