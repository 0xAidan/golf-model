#!/usr/bin/env python3
"""Export one Optuna scalar trial: raw params, metrics, and merge-ready autoresearch patch."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import optuna
from optuna.storages import RDBStorage
from optuna.trial import FixedTrial, TrialState

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_storage_path() -> Path:
    from backtester.research_lab.mo_study import default_storage_path

    return default_storage_path()


def _list_study_names(storage: RDBStorage) -> list[str]:
    return sorted(s.study_name for s in optuna.get_all_study_summaries(storage))


def _resolve_study_name(storage: RDBStorage, explicit: str | None) -> str:
    names = _list_study_names(storage)
    if explicit:
        if explicit not in names:
            raise SystemExit(
                f"Study {explicit!r} not found. Available: {names}"
            )
        return explicit
    scalar = [n for n in names if "weighted_roi_pct" in n or "scalar" in n.lower()]
    if len(scalar) == 1:
        return scalar[0]
    if len(names) == 1:
        return names[0]
    raise SystemExit(
        "Pass --study-name. Studies in DB:\n  " + "\n  ".join(names)
    )


def _autoresearch_merge_keys() -> list[str]:
    path = ROOT / "autoresearch" / "strategy_config.json"
    if not path.exists():
        return [
            "name",
            "w_sub_course_fit",
            "w_sub_form",
            "w_sub_momentum",
            "min_ev",
            "max_implied_prob",
            "min_model_prob",
            "kelly_fraction",
            "softmax_temp",
            "ai_adj_cap",
            "use_weather",
        ]
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.keys())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Optuna scalar trial → JSON (params + autoresearch/strategy_config.json patch)."
    )
    parser.add_argument(
        "--trial",
        type=int,
        required=True,
        help="Optuna trial number (e.g. 241)",
    )
    parser.add_argument(
        "--study-name",
        type=str,
        default=None,
        help="Optuna study name (default: auto-detect scalar study)",
    )
    parser.add_argument(
        "--storage",
        type=Path,
        default=None,
        help="Path to studies.db",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default="global",
        help="Registry scope for baseline StrategyConfig",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write JSON to this file (default: stdout only)",
    )
    args = parser.parse_args()

    from src.db import ensure_initialized

    ensure_initialized()

    from backtester.experiments import get_active_strategy
    from backtester.model_registry import get_live_weekly_model, get_research_champion
    from backtester.research_lab.param_space import strategy_from_optuna_trial

    storage_path = args.storage or _default_storage_path()
    if not storage_path.exists():
        raise SystemExit(f"Optuna storage not found: {storage_path}")

    storage = RDBStorage(f"sqlite:///{storage_path.resolve()}")
    study_name = _resolve_study_name(storage, args.study_name)
    study = optuna.load_study(study_name=study_name, storage=storage)

    trial = None
    for t in study.get_trials(deepcopy=False):
        if t.number == args.trial:
            trial = t
            break
    if trial is None:
        raise SystemExit(
            f"No trial with number {args.trial} in study {study_name!r}."
        )

    baseline = (
        get_research_champion(args.scope)
        or get_live_weekly_model(args.scope)
        or get_active_strategy(args.scope)
    )
    if trial.state != TrialState.COMPLETE or not trial.params:
        raise SystemExit(
            f"Trial {args.trial} is not usable (state={trial.state}, params={bool(trial.params)})."
        )

    fixed = FixedTrial(trial.params, number=trial.number)
    resolved = strategy_from_optuna_trial(fixed, baseline)
    merge_keys = _autoresearch_merge_keys()
    full = asdict(resolved)
    merge_patch = {k: full[k] for k in merge_keys if k in full}
    merge_patch["name"] = f"trial_{trial.number}_weighted_roi_{trial.value}"

    payload = {
        "study_name": study_name,
        "storage_path": str(storage_path),
        "trial_number": trial.number,
        "state": trial.state.name,
        "value": trial.value,
        "params": dict(trial.params),
        "user_attrs": dict(trial.user_attrs),
        "resolved_strategy_config_patch": merge_patch,
        "note": (
            "Merge resolved_strategy_config_patch into autoresearch/strategy_config.json "
            "after review; Edge Tuner is report-only by default."
        ),
    }

    text = json.dumps(payload, indent=2, default=str) + "\n"
    sys.stdout.write(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
