"""Mutable study state file (heartbeat, active study, counters)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "output" / "research" / "study_state.json"


def read_study_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_study_state(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into existing state and persist."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = read_study_state()
    current.update(updates)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2, sort_keys=True, default=str)
    return dict(current)


def touch_heartbeat(
    *,
    engine_running: bool,
    engine_mode: str,
    active_study_name: str | None = None,
    last_cycle_key: str | None = None,
) -> dict[str, Any]:
    return write_study_state(
        {
            "engine_running": engine_running,
            "engine_mode": engine_mode,
            "active_study_name": active_study_name,
            "last_cycle_key": last_cycle_key,
        }
    )
