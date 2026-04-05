"""Stable fingerprint for WalkForwardBenchmarkSpec (ledger + reproducibility)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backtester.research_lab.canonical import WalkForwardBenchmarkSpec


def benchmark_spec_hash(spec: WalkForwardBenchmarkSpec) -> str:
    """Short hex hash of benchmark parameters for ledger rows."""
    payload: dict[str, Any] = {
        "years": list(spec.years) if spec.years is not None else None,
        "min_train_events": spec.min_train_events,
        "test_window_size": spec.test_window_size,
        "weighting_mode": spec.weighting_mode,
        "eval_contract_version": spec.eval_contract_version,
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
