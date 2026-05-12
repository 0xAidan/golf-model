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
