"""Live-refresh worker health: wedged detection and remediation helpers."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from src.autoresearch_settings import get_settings
from src.live_refresh_policy import resolve_cadence
from src.runtime_paths import heartbeat_age_seconds, read_heartbeat


_ACTIVE_PHASES = frozenset({"ingest", "recompute", "publish", "persist", "shadow_mc"})


def snapshot_stale_after_seconds() -> int:
    settings = get_settings().get("live_refresh") or {}
    cadence = resolve_cadence(settings)
    return max(900, int(cadence.recompute_seconds) + 120)


def recompute_timeout_seconds() -> int:
    raw = os.environ.get("LIVE_REFRESH_RECOMPUTE_TIMEOUT_S", "2700")
    try:
        return max(300, int(float(raw)))
    except (TypeError, ValueError):
        return 2700


def _phase_age_seconds(heartbeat: dict[str, Any]) -> int | None:
    phase_started_at = heartbeat.get("phase_started_at")
    if not isinstance(phase_started_at, str) or not phase_started_at.strip():
        return None
    try:
        iso_value = phase_started_at.replace("Z", "+00:00")
        started_dt = datetime.fromisoformat(iso_value)
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - started_dt).total_seconds()))
    except ValueError:
        return None


def detect_worker_wedged(
    *,
    snapshot_age_seconds: int | None,
    stale_after_seconds: int | None = None,
    heartbeat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """True when the worker looks busy but snapshots are not advancing."""
    stale_after = stale_after_seconds if stale_after_seconds is not None else snapshot_stale_after_seconds()
    hb = heartbeat if heartbeat is not None else read_heartbeat()
    hb_age = heartbeat_age_seconds(hb)
    running = bool((hb or {}).get("running"))
    phase = (hb or {}).get("phase")
    refresh_state = str((hb or {}).get("refresh_state") or "")
    phase_age = _phase_age_seconds(hb) if hb else None
    recompute_timeout = recompute_timeout_seconds()

    reasons: list[str] = []
    wedged = False

    if snapshot_age_seconds is not None and snapshot_age_seconds > stale_after:
        if running and (phase in _ACTIVE_PHASES or refresh_state == "running"):
            wedged = True
            reasons.append(
                f"snapshot stale ({snapshot_age_seconds}s > {stale_after}s) while worker "
                f"phase={phase!r} refresh_state={refresh_state!r}"
            )
        elif not running:
            wedged = True
            reasons.append(
                f"snapshot stale ({snapshot_age_seconds}s > {stale_after}s) and worker not running"
            )

    if (
        running
        and phase in _ACTIVE_PHASES
        and phase_age is not None
        and phase_age > recompute_timeout
    ):
        wedged = True
        reasons.append(
            f"worker phase {phase!r} exceeded recompute timeout ({phase_age}s > {recompute_timeout}s)"
        )

    return {
        "wedged": wedged,
        "reasons": reasons,
        "snapshot_age_seconds": snapshot_age_seconds,
        "stale_after_seconds": stale_after,
        "heartbeat_age_seconds": hb_age,
        "heartbeat_phase": phase,
        "heartbeat_refresh_state": refresh_state,
        "phase_age_seconds": phase_age,
        "recompute_timeout_seconds": recompute_timeout,
    }


def restart_live_refresh_worker(*, reason: str = "") -> dict[str, Any]:
    """Restart the systemd live-refresh worker (production remediation)."""
    cmd = ["systemctl", "restart", "golf-live-refresh.service"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "ok": proc.returncode == 0,
        "command": " ".join(cmd),
        "reason": reason,
        "stderr": (proc.stderr or proc.stdout or "").strip() or None,
        "returncode": proc.returncode,
    }
