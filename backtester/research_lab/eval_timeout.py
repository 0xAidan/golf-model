"""Wall-clock bounded evaluation (Karpathy-style comparable trial budgets)."""

from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def default_max_trial_seconds() -> float | None:
    raw = os.environ.get("AUTORESEARCH_MAX_TRIAL_SECONDS", "").strip()
    if not raw:
        return 3600.0
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return 3600.0


def run_with_timeout(
    fn: Callable[[], T],
    *,
    timeout_seconds: float | None,
) -> tuple[T | None, str | None]:
    """
    Run fn in a worker thread; return (result, error).

    error is None on success, or 'timeout' / exception message string.
    If timeout_seconds is None or <= 0, runs synchronously in the current thread.
    """
    if timeout_seconds is None or timeout_seconds <= 0:
        try:
            return fn(), None
        except Exception as exc:
            return None, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        try:
            return fut.result(timeout=timeout_seconds), None
        except concurrent.futures.TimeoutError:
            return None, "timeout"
        except Exception as exc:
            return None, str(exc)
