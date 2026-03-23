"""Optional autoresearch/cycle_config.json — defaults if missing or invalid."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CYCLE_CONFIG_PATH = ROOT / "autoresearch" / "cycle_config.json"

_DEFAULTS: dict[str, Any] = {
    "mode": "weighted_walk_forward",
    "scope": "global",
    "cycles": 3,
    "max_candidates_per_cycle": 5,
    "holdout_tournaments": 3,
    "seed": 42,
}


def load_cycle_config() -> dict[str, Any]:
    """Merge file with defaults; never raises."""
    out = dict(_DEFAULTS)
    if not CYCLE_CONFIG_PATH.exists():
        return out
    try:
        raw = json.loads(CYCLE_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in _DEFAULTS or k in ("mode", "scope"):
                    out[k] = v
    except (OSError, json.JSONDecodeError):
        pass
    return out
