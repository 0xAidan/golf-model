#!/usr/bin/env python3
"""Run keep/discard autoresearch loop with immutable ledger."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtester.autoresearch_config import (  # noqa: E402
    PILOT_CONTRACT_PATH,
    STRATEGY_CONFIG_PATH,
    load_pilot_contract,
    load_strategy_overrides,
    strategy_hash,
)

EVAL_SCRIPT = ROOT / "scripts" / "run_autoresearch_eval.py"
EVALUATOR_VERSION = 1

MUTABLE_NUMERIC_KEYS = [
    "w_sub_course_fit",
    "w_sub_form",
    "w_sub_momentum",
    "min_ev",
    "max_implied_prob",
    "min_model_prob",
    "kelly_fraction",
    "softmax_temp",
    "ai_adj_cap",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _run_eval(timeout_seconds: int = 120) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(EVAL_SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip() or proc.stderr.strip() or "evaluator_failed")

    parsed: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()

    required = [
        "autoresearch_metric",
        "autoresearch_guardrails",
        "autoresearch_sample",
        "autoresearch_checkpoint_summary",
    ]
    missing = [k for k in required if k not in parsed]
    if missing:
        raise RuntimeError(f"parse_failure: missing lines {missing}")
    return parsed


def _write_ledger_row(row: dict[str, Any]) -> None:
    """Append to unified ledger.jsonl (and legacy autoresearch_runs.jsonl for cli_loop)."""
    from backtester.research_lab.ledger import append_ledger_row

    out = dict(row)
    out["source"] = "cli_loop"
    if "ts" not in out and "timestamp" in out:
        out["ts"] = out.pop("timestamp")
    append_ledger_row(out)


def _load_strategy() -> dict[str, Any]:
    return load_strategy_overrides(STRATEGY_CONFIG_PATH)


def _save_strategy(payload: dict[str, Any]) -> None:
    STRATEGY_CONFIG_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_add_commit(_message: str) -> None:
    """No-op kept for compatibility; loop no longer mutates git history."""
    return None


def _git_reset_previous() -> None:
    """No-op kept for compatibility; destructive reset is intentionally disabled."""
    return None


def _mutate_strategy(payload: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    updated = dict(payload)
    key = rng.choice(MUTABLE_NUMERIC_KEYS)
    current = float(updated.get(key, 0.0))

    if key.startswith("w_sub_"):
        delta = rng.uniform(-0.05, 0.05)
        updated[key] = max(0.0, min(1.0, round(current + delta, 4)))
        # Keep sub weights approximately normalized.
        total = sum(float(updated.get(k, 0.0)) for k in ("w_sub_course_fit", "w_sub_form", "w_sub_momentum")) or 1.0
        for k in ("w_sub_course_fit", "w_sub_form", "w_sub_momentum"):
            updated[k] = round(float(updated.get(k, 0.0)) / total, 4)
    elif key == "min_ev":
        updated[key] = round(max(0.0, min(1.0, current + rng.uniform(-0.01, 0.01))), 4)
    elif key == "max_implied_prob":
        updated[key] = round(max(0.05, min(1.0, current + rng.uniform(-0.03, 0.03))), 4)
    elif key == "min_model_prob":
        updated[key] = round(max(0.0, min(1.0, current + rng.uniform(-0.002, 0.002))), 4)
    elif key == "kelly_fraction":
        updated[key] = round(max(0.01, min(1.0, current + rng.uniform(-0.05, 0.05))), 4)
    elif key == "softmax_temp":
        updated[key] = round(max(0.1, min(50.0, current + rng.uniform(-0.2, 0.2))), 4)
    elif key == "ai_adj_cap":
        updated[key] = round(max(0.0, min(10.0, current + rng.uniform(-0.5, 0.5))), 4)
    return updated


def run_loop(iterations: int, seed: int, timeout_seconds: int) -> dict[str, Any]:
    rng = random.Random(seed)
    pilot_contract = load_pilot_contract()
    baseline = _run_eval(timeout_seconds=timeout_seconds)
    best_metric = float(baseline["autoresearch_metric"])
    kept = 0
    failed = 0
    guardrail_fails = 0

    for i in range(iterations):
        run_id = f"autoresearch-{uuid.uuid4()}"
        current = _load_strategy()
        candidate = _mutate_strategy(current, rng)
        _save_strategy(candidate)

        decision = "discarded"
        failure_reason = None
        metric = None
        guardrail_verdict = "fail"
        t0 = time.perf_counter()
        try:
            evaluated = _run_eval(timeout_seconds=timeout_seconds)
            metric = float(evaluated["autoresearch_metric"])
            guardrail_verdict = evaluated["autoresearch_guardrails"]
            guardrail_pass = guardrail_verdict == "pass"
            if not guardrail_pass:
                guardrail_fails += 1
            if guardrail_pass and metric > best_metric:
                best_metric = metric
                kept += 1
                decision = "kept"
            else:
                _save_strategy(current)
        except Exception as exc:
            failed += 1
            failure_reason = str(exc)
            _save_strategy(current)
            decision = "error"
        duration_ms = int((time.perf_counter() - t0) * 1000)

        row = {
            "trial_id": run_id,
            "run_id": run_id,
            "timestamp": _now_iso(),
            "git_commit": _git_commit(),
            "strategy_hash": strategy_hash(candidate),
            "pilot_contract_version": pilot_contract["pilot_contract_version"],
            "evaluator_version": EVALUATOR_VERSION,
            "checkpoint_set_id": pilot_contract["checkpoint_set_id"],
            "metric": metric,
            "scalar_metric": metric,
            "scalar_metric_name": "checkpoint_autoresearch_metric",
            "guardrail_verdict": guardrail_verdict,
            "decision": decision,
            "seed": seed,
            "failure_reason": failure_reason,
            "duration_ms": duration_ms,
            "error": failure_reason,
            "feasible": metric is not None,
            "guardrail_passed": guardrail_verdict == "pass" if metric is not None else False,
        }
        _write_ledger_row(row)

    total = max(iterations, 1)
    return {
        "iterations": iterations,
        "kept": kept,
        "failed": failed,
        "guardrail_fails": guardrail_fails,
        "keep_rate": round(kept / total, 4),
        "crash_rate": round(failed / total, 4),
        "best_metric": best_metric,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run autoresearch keep/discard loop")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    summary = run_loop(args.iterations, args.seed, args.timeout_seconds)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

