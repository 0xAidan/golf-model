"""Sweep disposable leftover files so backups and vacuum can fit.

Never touches the live database, WAL/SHM sidecars, KEEP_FOREVER tables,
or the newest verified backup. Only leftover temp copies and test dirs.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from src import db as db_mod
from src.runtime_paths import get_data_dir

_logger = logging.getLogger(__name__)

TMP_DB_NAME_RE = re.compile(r"^tmp[A-Za-z0-9_]+\.db$")
GOLF_TEMP_DIR_PREFIXES = ("golf_backup_", "golf_health_backup_")
DEFAULT_FILE_MIN_AGE_SECONDS = 2 * 60 * 60
DEFAULT_DIR_MIN_AGE_SECONDS = 24 * 60 * 60


def get_os_tmp_dir() -> Path:
    override = (os.environ.get("STORAGE_JANITOR_TMP_DIR") or "").strip()
    return Path(override) if override else Path(tempfile.gettempdir())


def get_backup_temp_dir() -> Path:
    override = (os.environ.get("STORAGE_BACKUP_TMP_DIR") or "").strip()
    path = Path(override) if override else (get_data_dir() / "tmp" / "backup")
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_backup_temp_db(*, prefix: str = "golf_integrity_") -> str:
    """Create a managed SQLite temp file for backup integrity decompress."""
    handle = tempfile.NamedTemporaryFile(
        prefix=prefix,
        suffix=".db",
        dir=str(get_backup_temp_dir()),
        delete=False,
    )
    handle.close()
    return handle.name


def _protected_paths(db_path: str | None) -> set[str]:
    if not db_path:
        return set()
    live = os.path.realpath(db_path)
    return {
        live,
        live + "-wal",
        live + "-shm",
        live + "-journal",
    }


def _is_old_enough(path: Path, min_age_seconds: int, now: float) -> bool:
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return False
    return age >= min_age_seconds


def _remove_file(path: Path, protected: set[str]) -> int | None:
    real = os.path.realpath(path)
    if real in protected:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    try:
        path.unlink()
    except OSError as exc:
        _logger.warning("could not remove leftover %s: %s", path, exc)
        return None
    return size


def _remove_tree(path: Path, protected: set[str]) -> int | None:
    real = os.path.realpath(path)
    if real in protected or any(item.startswith(real + os.sep) for item in protected):
        return None
    try:
        size = sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
    except OSError:
        size = 0
    try:
        shutil.rmtree(path)
    except OSError as exc:
        _logger.warning("could not remove leftover dir %s: %s", path, exc)
        return None
    return size


def sweep_os_tmp_leftovers(
    *,
    tmp_dir: str | os.PathLike[str] | None = None,
    db_path: str | None = None,
    min_age_seconds: int = DEFAULT_FILE_MIN_AGE_SECONDS,
    dir_min_age_seconds: int = DEFAULT_DIR_MIN_AGE_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Remove crashed sqlite temps and golf backup test dirs from the OS temp dir."""
    root = Path(tmp_dir) if tmp_dir else get_os_tmp_dir()
    protected = _protected_paths(db_path)
    clock = time.time() if now is None else now
    removed: list[dict[str, Any]] = []
    bytes_freed = 0

    if not root.is_dir():
        return {"ok": True, "removed": [], "bytes_freed": 0, "tmp_dir": str(root)}

    try:
        children = list(root.iterdir())
    except OSError as exc:
        return {"ok": False, "error": str(exc), "removed": [], "bytes_freed": 0, "tmp_dir": str(root)}

    for child in children:
        if child.is_file() and TMP_DB_NAME_RE.match(child.name):
            if not _is_old_enough(child, min_age_seconds, clock):
                continue
            size = _remove_file(child, protected)
            if size is None:
                continue
            bytes_freed += size
            removed.append({"path": str(child), "bytes": size, "kind": "tmp_db"})
            continue

        if child.is_dir() and child.name.startswith(GOLF_TEMP_DIR_PREFIXES):
            if not _is_old_enough(child, dir_min_age_seconds, clock):
                continue
            size = _remove_tree(child, protected)
            if size is None:
                continue
            bytes_freed += size
            removed.append({"path": str(child), "bytes": size, "kind": "golf_tmp_dir"})

    return {
        "ok": True,
        "tmp_dir": str(root),
        "removed": removed,
        "count": len(removed),
        "bytes_freed": bytes_freed,
    }


def sweep_backup_temp_dir(
    *,
    backup_tmp_dir: str | os.PathLike[str] | None = None,
    db_path: str | None = None,
    min_age_seconds: int = DEFAULT_FILE_MIN_AGE_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Remove leftover integrity-decompress files from the managed backup temp dir."""
    root = Path(backup_tmp_dir) if backup_tmp_dir else get_backup_temp_dir()
    protected = _protected_paths(db_path)
    clock = time.time() if now is None else now
    removed: list[dict[str, Any]] = []
    bytes_freed = 0

    if not root.is_dir():
        return {"ok": True, "removed": [], "bytes_freed": 0, "backup_tmp_dir": str(root)}

    try:
        children = list(root.iterdir())
    except OSError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "removed": [],
            "bytes_freed": 0,
            "backup_tmp_dir": str(root),
        }

    for child in children:
        if not child.is_file():
            continue
        if not _is_old_enough(child, min_age_seconds, clock):
            continue
        size = _remove_file(child, protected)
        if size is None:
            continue
        bytes_freed += size
        removed.append({"path": str(child), "bytes": size, "kind": "backup_tmp"})

    return {
        "ok": True,
        "backup_tmp_dir": str(root),
        "removed": removed,
        "count": len(removed),
        "bytes_freed": bytes_freed,
    }


def sweep_disposable_storage(
    *,
    tmp_dir: str | os.PathLike[str] | None = None,
    backup_tmp_dir: str | os.PathLike[str] | None = None,
    db_path: str | None = None,
    min_age_seconds: int = DEFAULT_FILE_MIN_AGE_SECONDS,
    dir_min_age_seconds: int = DEFAULT_DIR_MIN_AGE_SECONDS,
) -> dict[str, Any]:
    """Run every disposable-file sweep. Safe to call from backup and cleanup."""
    live_db = db_path or db_mod.DB_PATH
    os_tmp = sweep_os_tmp_leftovers(
        tmp_dir=tmp_dir,
        db_path=live_db,
        min_age_seconds=min_age_seconds,
        dir_min_age_seconds=dir_min_age_seconds,
    )
    backup_tmp = sweep_backup_temp_dir(
        backup_tmp_dir=backup_tmp_dir,
        db_path=live_db,
        min_age_seconds=min_age_seconds,
    )
    bytes_freed = int(os_tmp.get("bytes_freed") or 0) + int(backup_tmp.get("bytes_freed") or 0)
    removed = list(os_tmp.get("removed") or []) + list(backup_tmp.get("removed") or [])
    return {
        "ok": bool(os_tmp.get("ok", True) and backup_tmp.get("ok", True)),
        "bytes_freed": bytes_freed,
        "count": len(removed),
        "removed": removed,
        "os_tmp": os_tmp,
        "backup_tmp": backup_tmp,
    }
