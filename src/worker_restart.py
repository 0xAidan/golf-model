"""Operator-initiated live-refresh worker restart requests (file-based, no systemd in API)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from src.runtime_paths import get_worker_restart_request_path


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_worker_restart(*, requested_by: str = "api") -> dict[str, Any]:
    """Queue a worker restart for the next watchdog pass."""
    path = get_worker_restart_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "request_id": str(uuid.uuid4()),
        "requested_at": _iso_now(),
        "requested_by": requested_by,
        "status": "pending",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def read_worker_restart_request() -> dict[str, Any] | None:
    path = get_worker_restart_request_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def acknowledge_worker_restart_request(request_id: str | None = None) -> None:
    """Clear a fulfilled restart request from disk."""
    path = get_worker_restart_request_path()
    if not path.is_file():
        return
    if request_id:
        payload = read_worker_restart_request()
        if not payload or str(payload.get("request_id")) != str(request_id):
            return
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return
