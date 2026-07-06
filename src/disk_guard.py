"""Operator warnings and disk-floor state helpers."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

_logger = logging.getLogger(__name__)


def _parse_threshold_mb(name: str) -> int | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _free_mb(path: str) -> int | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return int(usage.free // (1024 * 1024))


def disk_state(path: str) -> str:
    """Return the env-gated disk guard state: ``ok``, ``warn``, or ``hard``."""
    free_mb = _free_mb(path)
    if free_mb is None:
        return "ok"
    warn_mb = _parse_threshold_mb("DISK_FREE_MB_WARN")
    hard_mb = _parse_threshold_mb("DISK_FREE_MB_HARD")
    if hard_mb is not None and free_mb < hard_mb:
        return "hard"
    if warn_mb is not None and free_mb < warn_mb:
        return "warn"
    return "ok"


def warn_if_low_disk(path: str, *, context: str) -> dict[str, Any] | None:
    """Log a warning when free space is below ``DISK_FREE_MB_WARN`` (env, MB). Returns a small dict or None."""
    threshold_mb = _parse_threshold_mb("DISK_FREE_MB_WARN")
    if threshold_mb is None:
        return None
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        _logger.warning("disk check failed (%s): %s", context, exc)
        return None
    free_mb = int(usage.free // (1024 * 1024))
    if free_mb < threshold_mb:
        _logger.warning(
            "Low disk space (%s): free=%sMB (warn if below %sMB) path=%s",
            context,
            free_mb,
            threshold_mb,
            path,
        )
        return {"warned": True, "free_mb": free_mb, "threshold_mb": threshold_mb, "path": path}
    return {"warned": False, "free_mb": free_mb, "threshold_mb": threshold_mb, "path": path}


def get_disk_state(path: str) -> dict[str, Any]:
    """Return free-space snapshot and warn/hard thresholds for ops surfaces."""
    warn_mb = _parse_threshold_mb("DISK_FREE_MB_WARN")
    hard_mb = _parse_threshold_mb("DISK_FREE_MB_HARD")

    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return {
            "free_mb": None,
            "warn_mb": warn_mb,
            "hard_mb": hard_mb,
            "state": "unknown",
            "guard_state": "ok",
            "error": str(exc),
            "path": path,
        }

    free_mb = int(usage.free // (1024 * 1024))
    state = "healthy"
    guard_state = "ok"
    if hard_mb is not None and free_mb < hard_mb:
        state = "critical"
        guard_state = "hard"
    elif warn_mb is not None and free_mb < warn_mb:
        state = "warn"
        guard_state = "warn"
    return {
        "free_mb": free_mb,
        "warn_mb": warn_mb,
        "hard_mb": hard_mb,
        "state": state,
        "guard_state": guard_state,
        "path": path,
    }
