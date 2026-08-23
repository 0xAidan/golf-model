"""Sealed holdout: immutable event set excluded from all autoresearch evaluation.

The holdout is committed as docs/research/sealed_holdout_events.json. Events on
this list are never served to search or confirmation windows; they are opened
only by operator invocation of scripts/run_autoresearch_sealed_holdout.py, whose
results append permanently to the ledger.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEALED_HOLDOUT_PATH = ROOT / "docs" / "research" / "sealed_holdout_events.json"


class SealedHoldoutError(ValueError):
    """Raised when the sealed-holdout contract is violated."""


def load_sealed_holdout(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the sealed-holdout document."""
    target = path or SEALED_HOLDOUT_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SealedHoldoutError(f"Missing sealed holdout file: {target}") from exc
    except json.JSONDecodeError as exc:
        raise SealedHoldoutError(f"Invalid JSON in {target}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SealedHoldoutError("sealed holdout must be a JSON object")
    if not isinstance(payload.get("sealed_holdout_version"), int):
        raise SealedHoldoutError("sealed_holdout_version must be an integer")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise SealedHoldoutError("sealed holdout must list at least one event")
    for event in events:
        if not isinstance(event, dict) or not event.get("event_id") or not event.get("year"):
            raise SealedHoldoutError(
                "each sealed event requires non-empty event_id and year"
            )
    return payload


def sealed_event_keys(path: Path | None = None) -> set[tuple[str, int]]:
    """Return the set of (event_id, year) keys that are sealed."""
    return {
        (str(event["event_id"]), int(event["year"]))
        for event in load_sealed_holdout(path)["events"]
    }


def assert_not_sealed(event_id: str, year: int, path: Path | None = None) -> None:
    """Raise if an event is sealed. Evaluation windows MUST call this."""
    key = (str(event_id), int(year))
    if key in sealed_event_keys(path):
        raise SealedHoldoutError(
            f"Event {event_id}/{year} is SEALED: it may only be evaluated via "
            "scripts/run_autoresearch_sealed_holdout.py by explicit operator command."
        )


def filter_sealed_events(events: list[dict[str, Any]], path: Path | None = None) -> list[dict[str, Any]]:
    """Return only events NOT on the sealed list (for window builders)."""
    sealed = sealed_event_keys(path)
    kept = []
    for event in events:
        key = (str(event.get("event_id")), int(event.get("year") or 0))
        if key not in sealed:
            kept.append(event)
    return kept
