"""Keep raw DataGolf odds responses exactly as they arrived.

The tick tables store derived rows and drop fields that later work needs:
player ids on most rows, the book's ``ties`` rule, and which round a matchup
belongs to. Without them a pick cannot be regraded under the book's own rule
and closing-line value cannot be measured.

Each distinct response is written once as a gzip file under
``<data dir>/raw_dg/<YYYY-MM-DD>/``. Every fetch, changed or not, appends one
line to that day's ``index.jsonl``, so the time a price was last seen is kept
without storing the same payload twice.

Capture never raises into the caller: a failed write must not break a fetch.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime_paths import get_data_dir

logger = logging.getLogger(__name__)

CAPTURE_ENDPOINTS = frozenset({
    "betting-tools/matchups",
    "betting-tools/matchups-all-pairings",
    "betting-tools/outrights",
})
ENABLED_ENV = "RAW_DG_CAPTURE"
MIN_FREE_MB_ENV = "RAW_DG_CAPTURE_MIN_FREE_MB"
DEFAULT_MIN_FREE_MB = 2048
_SECRET_PARAMS = frozenset({"key"})
_OFF = frozenset({"0", "false", "no", "off"})
_ON = frozenset({"1", "true", "yes", "on"})

_lock = threading.Lock()


def capture_enabled() -> bool:
    """On by default in production; off under pytest unless asked for explicitly."""
    raw = (os.environ.get(ENABLED_ENV) or "").strip().lower()
    if raw in _OFF:
        return False
    if raw in _ON:
        return True
    return not bool(os.environ.get("PYTEST_CURRENT_TEST"))


def capture_root() -> Path:
    return get_data_dir() / "raw_dg"


def _min_free_bytes() -> int:
    raw = (os.environ.get(MIN_FREE_MB_ENV) or "").strip()
    try:
        mb = int(raw) if raw else DEFAULT_MIN_FREE_MB
    except ValueError:
        mb = DEFAULT_MIN_FREE_MB
    return max(0, mb) * 1024 * 1024


def _slug(endpoint: str, params: dict[str, Any]) -> str:
    parts = [endpoint.replace("/", "_")]
    for name in sorted(params):
        if name in _SECRET_PARAMS or name == "file_format":
            continue
        parts.append(f"{name}-{params[name]}")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", "__".join(parts))[:180]


def capture_response(
    endpoint: str,
    params: dict[str, Any] | None,
    data: Any,
    *,
    now: datetime | None = None,
) -> Path | None:
    """Store ``data`` if it differs from the last capture for this request.

    Returns the path written, or None when nothing new was written (endpoint not
    captured, capture off, unchanged payload, low disk, or any error).
    """
    try:
        if endpoint not in CAPTURE_ENDPOINTS or not capture_enabled():
            return None
        safe_params = {k: v for k, v in (params or {}).items() if k not in _SECRET_PARAMS}
        stamp = now or datetime.now(timezone.utc)
        slug = _slug(endpoint, safe_params)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
        digest = hashlib.sha256(canonical).hexdigest()

        root = capture_root()
        day_dir = root / stamp.strftime("%Y-%m-%d")
        marker_dir = root / ".last"
        day_dir.mkdir(parents=True, exist_ok=True)
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / f"{slug}.json"

        with _lock:
            previous: dict[str, Any] = {}
            if marker.is_file():
                try:
                    previous = json.loads(marker.read_text())
                except (OSError, ValueError):
                    previous = {}
            unchanged = previous.get("sha256") == digest
            written: Path | None = None

            if not unchanged:
                if shutil.disk_usage(root).free < _min_free_bytes():
                    logger.warning("raw capture skipped for %s: free space below floor", endpoint)
                    return None
                name = f"{stamp.strftime('%H%M%S%f')}Z__{slug}__{digest[:12]}.json.gz"
                written = day_dir / name
                payload = {
                    "endpoint": endpoint,
                    "params": safe_params,
                    "fetched_at": stamp.isoformat(),
                    "sha256": digest,
                    "response": data,
                }
                tmp = written.with_suffix(written.suffix + ".tmp")
                with gzip.open(tmp, "wt", encoding="utf-8") as handle:
                    json.dump(payload, handle, separators=(",", ":"), default=str)
                os.replace(tmp, written)
                tmp_marker = marker.with_suffix(".tmp")
                tmp_marker.write_text(json.dumps({
                    "sha256": digest,
                    "file": str(written.relative_to(root)),
                }))
                os.replace(tmp_marker, marker)

            index_line = {
                "fetched_at": stamp.isoformat(),
                "request": slug,
                "sha256": digest,
                "file": str(written.relative_to(root)) if written else previous.get("file"),
                "changed": not unchanged,
            }
            with open(day_dir / "index.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps(index_line, separators=(",", ":")) + "\n")
        return written
    except Exception as exc:  # capture must never break a fetch
        logger.warning("raw capture failed for %s: %s", endpoint, exc)
        return None
