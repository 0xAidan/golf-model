"""Operator warnings when free disk space is low (non-blocking)."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any

_logger = logging.getLogger(__name__)

_DEFAULT_WARN_MB = 2048
_DEFAULT_CRITICAL_MB = 512


def disk_usage_summary(path: str) -> dict[str, Any]:
    """Return free/total disk stats for ops health and prune decisions."""
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return {"ok": False, "path": path, "error": str(exc)}
    total = int(usage.total)
    free = int(usage.free)
    used = int(usage.used)
    free_percent = round((free / total) * 100.0, 2) if total else 0.0
    warn_mb = _warn_threshold_mb()
    critical_mb = _critical_threshold_mb()
    status = "ok"
    if free < critical_mb * 1024 * 1024:
        status = "critical"
    elif free < warn_mb * 1024 * 1024:
        status = "low"
    return {
        "ok": True,
        "path": path,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "free_mb": int(free // (1024 * 1024)),
        "free_percent": free_percent,
        "warn_threshold_mb": warn_mb,
        "critical_threshold_mb": critical_mb,
        "status": status,
    }


def _warn_threshold_mb() -> int:
    raw = (os.environ.get("DISK_FREE_MB_WARN") or str(_DEFAULT_WARN_MB)).strip()
    try:
        return max(64, int(raw))
    except ValueError:
        return _DEFAULT_WARN_MB


def _critical_threshold_mb() -> int:
    raw = (os.environ.get("DISK_FREE_MB_CRITICAL") or str(_DEFAULT_CRITICAL_MB)).strip()
    try:
        return max(32, int(raw))
    except ValueError:
        return _DEFAULT_CRITICAL_MB


def warn_if_low_disk(path: str, *, context: str) -> dict[str, Any] | None:
    """Log a warning when free space is below ``DISK_FREE_MB_WARN`` (env, MB). Returns a small dict or None."""
    summary = disk_usage_summary(path)
    if not summary.get("ok"):
        _logger.warning("disk check failed (%s): %s", context, summary.get("error"))
        return None
    threshold_mb = int(summary["warn_threshold_mb"])
    free_mb = int(summary["free_mb"])
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
