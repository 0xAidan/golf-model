"""Operator warnings when free disk space is low (non-blocking)."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

_logger = logging.getLogger(__name__)


def warn_if_low_disk(path: str, *, context: str) -> dict[str, Any] | None:
    """Log a warning when free space is below ``DISK_FREE_MB_WARN`` (env, MB). Returns a small dict or None."""
    raw = (os.environ.get("DISK_FREE_MB_WARN") or "").strip()
    if not raw:
        return None
    try:
        threshold_mb = int(raw)
    except ValueError:
        return None
    if threshold_mb <= 0:
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
    warn_raw = (os.environ.get("DISK_FREE_MB_WARN") or "").strip()
    hard_raw = (os.environ.get("DISK_FREE_MB_HARD") or "").strip()
    try:
        warn_mb = int(warn_raw) if warn_raw else None
    except ValueError:
        warn_mb = None
    try:
        hard_mb = int(hard_raw) if hard_raw else None
    except ValueError:
        hard_mb = None
    if warn_mb is not None and warn_mb <= 0:
        warn_mb = None
    if hard_mb is not None and hard_mb <= 0:
        hard_mb = None

    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return {
            "free_mb": None,
            "warn_mb": warn_mb,
            "hard_mb": hard_mb,
            "state": "unknown",
            "error": str(exc),
            "path": path,
        }

    free_mb = int(usage.free // (1024 * 1024))
    state = "healthy"
    if hard_mb is not None and free_mb < hard_mb:
        state = "critical"
    elif warn_mb is not None and free_mb < warn_mb:
        state = "warn"
    return {
        "free_mb": free_mb,
        "warn_mb": warn_mb,
        "hard_mb": hard_mb,
        "state": state,
        "path": path,
    }
