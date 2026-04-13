"""Utilities for writing per-run provenance artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _collect_blend_by_market(value_bets: dict[str, list[dict[str, Any]]] | None) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for market, bets in (value_bets or {}).items():
        if not bets:
            continue
        sample = next((bet for bet in bets if isinstance(bet, dict)), None)
        if not sample:
            continue
        dg = sample.get("blend_dg_used")
        model = sample.get("blend_model_used")
        if dg is None and model is None:
            continue
        output[market] = {
            "dg": float(dg if dg is not None else 0.0),
            "model": float(model if model is not None else 0.0),
        }
    return output


def write_run_provenance(
    *,
    event_name: str,
    output_dir: str,
    strategy_meta: dict[str, Any] | None,
    runtime_settings: dict[str, Any] | None,
    run_quality: dict[str, Any] | None,
    value_bets: dict[str, list[dict[str, Any]]] | None,
    matchup_diagnostics: dict[str, Any] | None = None,
    source: str = "pipeline",
) -> str:
    safe_name = event_name.lower().replace(" ", "_").replace("'", "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    output_path = Path(output_dir) / f"{safe_name}_provenance_{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event_name": event_name,
        "source": source,
        "strategy_meta": strategy_meta or {},
        "runtime_settings": runtime_settings or {},
        "run_quality": run_quality or {},
        "blend_by_market": _collect_blend_by_market(value_bets),
        "matchup_diagnostics": matchup_diagnostics or {},
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(output_path)
