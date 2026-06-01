#!/usr/bin/env python3
"""Run Phase 2/3 matchup lab research sweeps and emit markdown/json artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
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
MIN_CANDIDATE_N = 200
MIN_WIREUP_N = 250


@dataclass
class ScenarioSpec:
    scenario_id: str
    title: str
    family: str
    strategy_overrides: dict[str, Any]
    filters: dict[str, Any]
    unsupported_reason: str | None = None
    notes: str | None = None


def _baseline_strategy() -> StrategyConfig:
    return StrategyConfig(
        name="matchup_lab_baseline",
        markets=["matchup"],
        stake_mode="flat",
        flat_stake=1.0,
        min_ev=float(getattr(config, "DEFAULT_EV_THRESHOLD", 0.08)),
        matchup_ev_threshold=float(getattr(config, "MATCHUP_EV_THRESHOLD", 0.05)),
        platt_a=float(getattr(config, "MATCHUP_PLATT_A", -0.05)),
        platt_b=float(getattr(config, "MATCHUP_PLATT_B", 0.0)),
        min_composite_gap=0.0,
        max_win_prob_cap=0.99,
        dg_matchup_blend_weight=float(getattr(config, "DG_MATCHUP_BLEND_WEIGHT", 0.8)),
        model_matchup_blend_weight=float(getattr(config, "MODEL_MATCHUP_BLEND_WEIGHT", 0.2)),
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
    windows = {
        "primary": [e for e in events if int(e.get("year", 0)) in PRIMARY_YEARS],
        "holdout": [e for e in events if int(e.get("year", 0)) in HOLDOUT_YEARS],
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
    return out


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit_rate_pct": 0.0, "roi_pct": 0.0, "brier": None, "drawdown_pct": 0.0}
    wins = sum(1 for r in rows if r.get("won"))
    pnl = sum(float(r.get("payout", 0.0)) - float(r.get("wager", 0.0)) for r in rows)
    staked = sum(float(r.get("wager", 0.0)) for r in rows)
    brier = mean((float(r.get("model_prob", 0.0)) - (1.0 if r.get("won") else 0.0)) ** 2 for r in rows)
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
    }


def _collect_rows_for_window(
    *,
    events: list[dict[str, Any]],
    strategy: StrategyConfig,
    rolling_platt: bool,
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
        matchup_rows = [r for r in event_rows if r.get("market") == "matchup" and float(r.get("ev", 0.0) or 0.0) > 0.0]
        for row in matchup_rows:
            row["event_id"] = str(event["event_id"])
            row["year"] = int(event["year"])
        rows.extend(matchup_rows)
    return rows


def _run_scenario(spec: ScenarioSpec, windows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    strategy = _baseline_strategy()
    for k, v in spec.strategy_overrides.items():
        setattr(strategy, k, v)

    result = {
        "scenario_id": spec.scenario_id,
        "title": spec.title,
        "family": spec.family,
        "strategy_overrides": spec.strategy_overrides,
        "filters": spec.filters,
        "unsupported_reason": spec.unsupported_reason,
        "notes": spec.notes,
        "windows": {},
    }

    for window_name, events in windows.items():
        raw_rows = _collect_rows_for_window(
            events=events,
            strategy=strategy,
            rolling_platt=bool(spec.filters.get("rolling_platt")),
        )
        filtered_rows = _apply_filters(raw_rows, spec.filters)
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


def _build_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Matchup tuning report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Primary years: `{payload['primary_years']}`")
    lines.append(f"- Holdout years: `{payload['holdout_years']}`")
    lines.append(f"- Flat stake: `1u`")
    lines.append("")
    lines.append("## Winner ranking")
    lines.append("")
    for rank, row in enumerate(payload["ranking"][:10], start=1):
        lines.append(
            f"{rank}. `{row['scenario_id']}` — primary ROI `{row['primary_roi_pct']}%`, "
            f"hit `{row['primary_hit_rate_pct']}%`, brier `{row['primary_brier']}`, "
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
    lines.append("| Scenario | Family | Primary ROI | Primary Hit | Primary Brier | Primary n | Holdout ROI | Holdout Hit | Holdout Brier | Holdout n |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["ranking"]:
        lines.append(
            f"| `{row['scenario_id']}` | {row['family']} | {row['primary_roi_pct']} | {row['primary_hit_rate_pct']} | "
            f"{row['primary_brier']} | {row['primary_n']} | {row['holdout_roi_pct']} | {row['holdout_hit_rate_pct']} | "
            f"{row['holdout_brier']} | {row['holdout_n']} |"
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
    winner = payload.get("winner") or {}
    if winner:
        lines.append(
            f"- Winner candidate: `{winner.get('scenario_id')}` "
            f"(primary n={winner.get('primary_n')}, holdout n={winner.get('holdout_n')})"
        )
    else:
        lines.append("- No candidate met minimum gating requirements.")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run matchup lab research sweep matrix and holdout report")
    parser.add_argument("--db-path", default="/opt/golf-model/data/golf.db")
    parser.add_argument("--out-dir", default="output/research")
    parser.add_argument("--run-optuna-trials", type=int, default=0, help="Run additional matchup MO optuna trials")
    args = parser.parse_args()

    db.DB_PATH = args.db_path
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    windows = _load_event_windows()
    specs = _all_specs()
    results = [_run_scenario(spec, windows) for spec in specs if spec.filters.get("optuna") is None]
    pareto = _pareto_candidates(results)

    ranking = []
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
                "primary_n": p["n"],
                "holdout_roi_pct": h["roi_pct"],
                "holdout_hit_rate_pct": h["hit_rate_pct"],
                "holdout_brier": h["brier"],
                "holdout_n": h["n"],
            }
        )
    ranking.sort(key=lambda x: (x["primary_roi_pct"], x["primary_hit_rate_pct"], -float(x["primary_brier"] or 9e9)), reverse=True)

    baseline = next((r for r in results if r["scenario_id"] == "E0"), None)
    winner = None
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
                winner = row
                break

    optuna_summary = None
    if args.run_optuna_trials > 0:
        optuna_summary = _optuna_matchup_mo(_baseline_strategy(), args.run_optuna_trials, windows)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": args.db_path,
        "primary_years": PRIMARY_YEARS,
        "holdout_years": HOLDOUT_YEARS,
        "minimum_candidate_n": MIN_CANDIDATE_N,
        "minimum_wireup_n": MIN_WIREUP_N,
        "results": results,
        "pareto_frontier": pareto,
        "ranking": ranking,
        "winner": winner,
        "optuna_matchup_mo": optuna_summary,
    }

    json_path = out_dir / f"matchup_tuning_{stamp}.json"
    md_path = out_dir / f"matchup_tuning_{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(payload), encoding="utf-8")

    if optuna_summary:
        ledger_path = out_dir / "ledger.jsonl"
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": payload["generated_at"], "source": "matchup_lab_optuna", "summary": optuna_summary}) + "\n")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if winner:
        print(
            f"winner={winner['scenario_id']} primary_roi={winner['primary_roi_pct']} "
            f"primary_hit={winner['primary_hit_rate_pct']} holdout_roi={winner['holdout_roi_pct']}"
        )
    else:
        print("winner=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
