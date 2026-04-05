"""Append-only research trial ledger (JSONL). Karpathy-aligned audit trail."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "output" / "research" / "ledger.jsonl"
LEGACY_LOOP_LEDGER = ROOT / "output" / "research" / "autoresearch_runs.jsonl"

VALID_SOURCES = frozenset({"optuna_mo", "optuna_scalar", "research_cycle", "cli_loop", "agent"})


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def append_ledger_row(row: dict[str, Any]) -> None:
    """
    Append one JSON object to ledger.jsonl (and mirror legacy path for cli_loop when source is cli_loop).

    Required-ish fields per SPEC: ts, source, duration_ms; callers should set trial_id, params, etc.
    """
    out = dict(row)
    if "ts" not in out:
        out["ts"] = datetime.now(timezone.utc).isoformat()
    src = out.get("source")
    if src not in VALID_SOURCES:
        raise ValueError(f"ledger source must be one of {sorted(VALID_SOURCES)}, got {src!r}")
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(out, sort_keys=True, default=str) + "\n"
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)

    # Dual-write CLI loop rows to legacy filename for older tooling (same content).
    if src == "cli_loop":
        LEGACY_LOOP_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEGACY_LOOP_LEDGER.open("a", encoding="utf-8") as handle:
            handle.write(line)


def ledger_row_from_optuna_trial(
    *,
    source: str,
    study_name: str,
    trial_number: int,
    params: dict[str, Any],
    user_attrs: dict[str, Any],
    values: list[float] | None,
    duration_ms: int,
    error: str | None,
    eval_contract_version: int,
    benchmark_spec_hash: str,
    strategy_hash: str | None,
    git_commit: str | None = None,
    scalar_metric: float | None = None,
    scalar_metric_name: str | None = None,
) -> dict[str, Any]:
    """Build a normalized ledger row for an Optuna trial."""
    gid = git_commit if git_commit is not None else _git_head()
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "trial_id": f"{study_name}:{trial_number}",
        "study_id": study_name,
        "git_commit": gid,
        "strategy_hash": strategy_hash,
        "eval_contract_version": eval_contract_version,
        "params": params,
        "objective_vector": list(values) if values is not None else None,
        "scalar_metric": scalar_metric,
        "scalar_metric_name": scalar_metric_name,
        "feasible": user_attrs.get("feasible"),
        "guardrail_passed": user_attrs.get("guardrail_passed"),
        "benchmark_spec_hash": benchmark_spec_hash,
        "duration_ms": duration_ms,
        "error": error,
        "optuna_trial_number": trial_number,
        "study_mode": "multi_objective" if source == "optuna_mo" else "scalar",
    }
    return row


def timed_eval(
    fn: Any,
    *args: Any,
    **kwargs: Any,
) -> tuple[Any, int, str | None]:
    """Run fn(*args, **kwargs); return (result, duration_ms, error_str_or_none)."""
    t0 = time.perf_counter()
    try:
        out = fn(*args, **kwargs)
        ms = int((time.perf_counter() - t0) * 1000)
        return out, ms, None
    except Exception as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        return None, ms, str(exc)
