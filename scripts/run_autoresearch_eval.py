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

from backtester.research_lab.canonical import evaluate_checkpoint_pilot  # noqa: E402


def _evaluate(strategy_overrides_path: Path | None = None) -> dict:
    """Legacy dict shape; delegates to canonical evaluation."""
    result = evaluate_checkpoint_pilot(strategy_overrides_path=strategy_overrides_path)
    return result.to_legacy_checkpoint_eval_dict()


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
