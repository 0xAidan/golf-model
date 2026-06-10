#!/usr/bin/env python3
"""Revalidate the promoted lab champion (trial 327) on frozen walk-forward windows (H-1).

Trial 327's headline ROI (+13.8% primary / +9.05% holdout) lives only in a gitignored
Optuna study; no committed per-trial dossier exists, and the matrix that shipped alongside
it was holdout-negative on every row. This harness replays the trial-327 StrategyConfig on
the pinned primary (2024-2025) and holdout (2026) windows using the same walk-forward
primitives as the frozen baseline benchmark, and writes a committable dossier under
docs/research/experiments/ with the robust gate verdict.

NOTE: this requires the production DB (historical_matchup_odds etc.). The local dev DB is a
fixture; run on the VPS:
    python3 scripts/revalidate_trial327.py --db-path /opt/golf-model/data/golf.db --write
The authoritative max-ROI reproduction remains scripts/run_matchup_lab_research.py
--only-max-roi; this harness is the committed, gate-checked sanity replay.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester.strategy import StrategyConfig, replay_event
from backtester.weighted_walkforward import load_historical_events
from src import db
from src.lab_champion import build_lab_pipeline_config, lab_champion_meta, load_lab_champion_strategy

# Pinned windows (match scripts/run_matchup_lab_research.py + LAB_EXPERIMENT_BASELINE).
PRIMARY_YEARS = [2024, 2025]
HOLDOUT_YEARS = [2026]
ROBUST_MIN_PRIMARY_N = 300
ROBUST_MIN_HOLDOUT_N = 200
ROBUST_MIN_HOLDOUT_ROI_PCT = 8.0


def _lab_strategy() -> StrategyConfig:
    cfg = build_lab_pipeline_config(load_lab_champion_strategy())
    kwargs = dict(
        name="lab_matchup_champion_trial_327_revalidation",
        markets=["matchup"],
        model_variant=str(cfg.get("model_variant", "v5")),
    )
    for field in (
        "platt_a",
        "platt_b",
        "min_composite_gap",
        "matchup_ev_threshold",
        "max_win_prob_cap",
        "dg_matchup_blend_weight",
        "model_matchup_blend_weight",
        "w_sub_course_fit",
        "w_sub_form",
        "w_sub_momentum",
    ):
        if cfg.get(field) is not None:
            kwargs[field] = cfg[field]
    return StrategyConfig(**kwargs)


def _metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit_rate_pct": 0.0, "roi_pct": 0.0, "brier": None}
    wins = sum(1 for r in rows if r.get("won"))
    pnl = sum(
        (r.get("payout", 0.0) - r.get("wager", 0.0)) / max(r.get("wager", 1.0), 1e-9)
        for r in rows
    )
    brier = mean(
        (float(r.get("model_prob", 0.0)) - (1.0 if r.get("won") else 0.0)) ** 2 for r in rows
    )
    return {
        "n": n,
        "hit_rate_pct": round(100.0 * wins / n, 2),
        "roi_pct": round(100.0 * pnl / n, 2),
        "brier": round(brier, 4),
    }


def _replay_window(years: list[int], strategy: StrategyConfig) -> dict:
    events = load_historical_events(years=years)
    rows: list[dict] = []
    for event in events:
        bets = replay_event(event["event_id"], event["year"], strategy)
        rows.extend(
            r for r in bets
            if r.get("market") == "matchup" and float(r.get("ev", 0.0) or 0.0) > 0.0
        )
    return _metrics(rows)


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Revalidate trial 327")
    parser.add_argument("--db-path", default=db.DB_PATH)
    parser.add_argument("--write", action="store_true", help="write dossier under docs/research/experiments/")
    args = parser.parse_args()

    db.DB_PATH = args.db_path
    strategy = _lab_strategy()
    meta = lab_champion_meta()

    primary = _replay_window(PRIMARY_YEARS, strategy)
    holdout = _replay_window(HOLDOUT_YEARS, strategy)

    robust_pass = (
        primary["n"] >= ROBUST_MIN_PRIMARY_N
        and holdout["n"] >= ROBUST_MIN_HOLDOUT_N
        and holdout["roi_pct"] >= ROBUST_MIN_HOLDOUT_ROI_PCT
    )

    dossier = {
        "experiment": "trial_327_revalidation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "db_path": args.db_path,
        "champion_meta": meta,
        "claim": {"primary_roi_pct": meta.get("primary_roi_pct"), "holdout_roi_pct": meta.get("holdout_roi_pct")},
        "windows": {"primary_years": PRIMARY_YEARS, "holdout_years": HOLDOUT_YEARS},
        "primary": primary,
        "holdout": holdout,
        "robust_gate": {
            "min_primary_n": ROBUST_MIN_PRIMARY_N,
            "min_holdout_n": ROBUST_MIN_HOLDOUT_N,
            "min_holdout_roi_pct": ROBUST_MIN_HOLDOUT_ROI_PCT,
            "passed": robust_pass,
        },
    }
    print(json.dumps(dossier, indent=2))

    if args.write:
        out_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "docs/research/experiments"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        (out_dir / f"trial_327_revalidation_{stamp}.json").write_text(json.dumps(dossier, indent=2), encoding="utf-8")
        print(f"\nWrote {out_dir / f'trial_327_revalidation_{stamp}.json'}")

    return 0 if robust_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
