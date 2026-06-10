"""Process-local recorder for non-fatal runtime degradations operators should see.

Some failures are intentionally non-fatal (e.g. a corrupt strategy-config JSON falls
back to a safe default) but must not be *silent* — betting with a fallback strategy
while the operator believes the configured one is live is a trust hazard (defect P1-1).

This module keeps a small thread-safe ring buffer of recent degradation events that
``GET /api/ops/health`` and snapshot diagnostics can surface. It is process-local
(not persisted); the live-refresh worker and the dashboard each keep their own view,
which is fine because both serve ops health from their own process.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_MAX_EVENTS = 25
_lock = threading.Lock()
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)


def record_event(kind: str, source: str, message: str, *, scope: str = "global") -> None:
    """Record a non-fatal runtime degradation event (no secrets in ``message``)."""
    event = {
        "kind": str(kind),
        "scope": str(scope),
        "source": str(source),
        "message": str(message)[:500],
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _events.append(event)


def record_strategy_config_error(scope: str, source: str, message: str) -> None:
    """Record a non-fatal strategy-config resolution failure (parse/load fallback).

    Args:
        scope: resolution scope (e.g. ``"global"``).
        source: which store failed (e.g. ``"active_strategy"``, ``"model_registry"``).
        message: short human-readable reason (no secrets).
    """
    record_event("strategy_config_error", source, message, scope=scope)


def record_run_logging_error(source: str, message: str) -> None:
    """Record a non-fatal failure to persist pipeline run metadata (defect P1-5)."""
    record_event("run_logging_error", source, message)


def recent_events(kind: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Most recent events, newest last (optionally filtered by ``kind``)."""
    with _lock:
        items = list(_events)
    if kind is not None:
        items = [e for e in items if e.get("kind") == kind]
    return items[-limit:]


def recent_strategy_config_errors(limit: int = 10) -> list[dict[str, Any]]:
    """Most recent strategy-config errors, newest last (capped at ``limit``)."""
    return recent_events("strategy_config_error", limit)


def clear() -> None:
    """Clear all recorded events (test helper)."""
    with _lock:
        _events.clear()
