#!/usr/bin/env python3
"""Run immutable checkpoint-based autoresearch evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtester.autoresearch_config import (  # noqa: E402
    ContractValidationError,
    build_strategy_from_overrides,
    load_pilot_contract,
    load_strategy_overrides,
    strategy_hash,
    validate_contract_documents,
)
from backtester.checkpoint_replay import (  # noqa: E402
    assert_checkpoint_temporal_integrity,
    get_pilot_checkpoints,
    replay_checkpoint,
    summarize_checkpoint_results,
)
from backtester.model_registry import get_live_weekly_model, get_research_champion  # noqa: E402
from backtester.weighted_walkforward import compute_blended_score, evaluate_guardrails  # noqa: E402
from src.db import ensure_initialized  # noqa: E402

EVALUATOR_VERSION = 1


def _evaluate(strategy_overrides_path: Path | None = None) -> dict:
    ensure_initialized()
    validate_contract_documents()
    contract = load_pilot_contract()
    if int(contract["evaluation_contract_version"]) != EVALUATOR_VERSION:
        raise ContractValidationError(
            f"evaluation_contract_version mismatch: {contract['evaluation_contract_version']} != {EVALUATOR_VERSION}"
        )

    baseline = get_research_champion("global") or get_live_weekly_model("global")
    overrides = load_strategy_overrides(strategy_overrides_path)
    candidate = build_strategy_from_overrides(overrides, baseline)

    pilot = get_pilot_checkpoints()
    event = pilot["pilot_event"]
    checkpoints = pilot["checkpoints"]

    candidate_results = []
    baseline_results = []
    for checkpoint in checkpoints:
        as_of = checkpoint["as_of_date"]
        assert_checkpoint_temporal_integrity(event["event_id"], event["year"], as_of)
        candidate_results.append(
            replay_checkpoint(
                event_id=event["event_id"],
                year=event["year"],
                strategy=candidate,
                as_of_date=as_of,
                checkpoint_id=checkpoint["id"],
            )
        )
        baseline_results.append(
            replay_checkpoint(
                event_id=event["event_id"],
                year=event["year"],
                strategy=baseline,
                as_of_date=as_of,
                checkpoint_id=checkpoint["id"],
            )
        )

    candidate_summary = summarize_checkpoint_results(candidate_results)
    baseline_summary = summarize_checkpoint_results(baseline_results)
    guardrails = evaluate_guardrails(candidate_summary, baseline_summary, min_bets=30)
    blended_score = compute_blended_score(candidate_summary, guardrails)

    return {
        "metric": blended_score,
        "guardrails": guardrails,
        "sample": candidate_summary["total_bets"],
        "checkpoint_summary": {
            "event": event,
            "checkpoint_set_id": contract["checkpoint_set_id"],
            "candidate": candidate_summary,
            "baseline": baseline_summary,
            "checkpoints": candidate_results,
        },
        "metadata": {
            "strategy_hash": strategy_hash(overrides),
            "pilot_contract_version": contract["pilot_contract_version"],
            "evaluation_contract_version": contract["evaluation_contract_version"],
            "evaluator_version": EVALUATOR_VERSION,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run immutable autoresearch evaluation")
    parser.add_argument("--strategy-config", type=Path, default=None, help="Optional strategy config path")
    args = parser.parse_args()

    try:
        result = _evaluate(args.strategy_config)
    except Exception as exc:
        print(f"autoresearch_error: {exc}")
        return 1

    guardrail_pass = bool(result["guardrails"].get("passed", False))
    print(f"autoresearch_metric: {result['metric']}")
    print(f"autoresearch_guardrails: {'pass' if guardrail_pass else 'fail'}")
    print(f"autoresearch_sample: {int(result['sample'])}")
    print(f"autoresearch_checkpoint_summary: {json.dumps(result['checkpoint_summary'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

