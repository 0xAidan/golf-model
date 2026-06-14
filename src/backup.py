"""
Database Backup Utility

Creates timestamped backups of the SQLite database.
Keeps the last N backups and auto-rotates.

Usage:
    python -m src.backup                     # Create a backup now
    python -m src.backup --keep 10           # Keep last 10 backups
    python -m src.backup --compress          # gzip new backup to .db.gz (explicit opt-in)
    python -m src.backup --print-path        # Print authoritative DB path (for shell scripts)
    python -m src.backup --print-backup-dir  # Print backup directory path
"""

import os
import shutil
import glob
import gzip
import sqlite3
import tempfile
from datetime import datetime
from typing import Any

from src import db
from src.disk_guard import warn_if_low_disk


def _current_db_path() -> str:
    """Return the authoritative DB path at call time (not at import time).

    ``src.db.DB_PATH`` is set once at import, but tests or ops tooling may
    mutate it. Always read the live value so callers (shell scripts, tests)
    stay in sync with whatever :mod:`src.db` considers authoritative.
    """
    return db.DB_PATH


# Back-compat alias. Some callers/tests import ``DB_PATH`` directly.
# Prefer ``_current_db_path()`` in new code.
DB_PATH = _current_db_path()
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")


def _backup_globs() -> tuple[str, str]:
    """Patterns for timestamped backup artifacts (plain DB and optional gzip)."""
    return (
        os.path.join(BACKUP_DIR, "golf_model_*.db"),
        os.path.join(BACKUP_DIR, "golf_model_*.db.gz"),
    )


def _enforce_disk_hard_floor(path: str) -> None:
    """Abort backup when free space is below ``DISK_FREE_MB_HARD`` (env, MB) if set."""
    raw = (os.environ.get("DISK_FREE_MB_HARD") or "").strip()
    if not raw:
        return
    try:
        hard_mb = int(raw)
    except ValueError:
        return
    if hard_mb <= 0:
        return
    usage = shutil.disk_usage(path)
    free_mb = int(usage.free // (1024 * 1024))
    if free_mb < hard_mb:
        raise RuntimeError(
            f"Refusing backup: only {free_mb} MiB free (DISK_FREE_MB_HARD={hard_mb} MiB)."
        )


def _sorted_backup_paths() -> list[str]:
    """Oldest first (mtime) for rotation."""
    paths: list[str] = []
    for pattern in _backup_globs():
        paths.extend(glob.glob(pattern))
    paths = list(set(paths))
    return sorted(paths, key=lambda p: os.path.getmtime(p))


def verify_backup_integrity(backup_path: str) -> dict[str, Any]:
    """Run SQLite ``quick_check`` on a backup file (plain or gzip)."""
    if not os.path.isfile(backup_path):
        return {"ok": False, "error": "backup file not found", "path": backup_path}

    check_path = backup_path
    temp_path: str | None = None
    try:
        if backup_path.endswith(".gz"):
            temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
            os.close(temp_fd)
            with gzip.open(backup_path, "rb") as gz, open(temp_path, "wb") as out:
                shutil.copyfileobj(gz, out)
            check_path = temp_path

        conn = sqlite3.connect(f"file:{check_path}?mode=ro", uri=True, timeout=120.0)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            result = str(row[0]) if row else "unknown"
        finally:
            conn.close()

        ok = result == "ok"
        return {
            "ok": ok,
            "quick_check": result,
            "path": backup_path,
            "checked_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "path": backup_path,
            "checked_at": datetime.now().isoformat(),
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def create_backup(keep: int = 7, *, compress: bool = False) -> str | None:
    """
    Create a timestamped backup of the database.

    Args:
        keep: Number of recent backups to keep (older ones deleted).
        compress: When True, gzip the new backup to ``*.db.gz`` (explicit opt-in).

    Returns:
        Path to the new backup file, or None if DB doesn't exist.
    """
    db_path = _current_db_path()
    if not os.path.exists(db_path):
        return None

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _enforce_disk_hard_floor(repo_root)
    warn_info = warn_if_low_disk(repo_root, context="backup_create")
    if warn_info and warn_info.get("warned"):
        print(
            f"  Warning: low disk ({warn_info.get('free_mb')} MiB free; "
            f"warn below {warn_info.get('threshold_mb')} MiB)."
        )

    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Prune *before* creating a new file so peak disk use stays at ~`keep` full
    # copies (not `keep` + 1). Small VPS volumes often fail sqlite backup with
    # "database or disk is full" when rotation ran only after the new backup.
    backups = _sorted_backup_paths()
    while len(backups) >= int(keep):
        oldest = backups.pop(0)
        try:
            os.remove(oldest)
            print(f"  Removed old backup to free space: {oldest}")
        except OSError as exc:
            print(f"  Warning: could not remove {oldest}: {exc}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"golf_model_{timestamp}.db")

    source_conn = sqlite3.connect(db_path)
    backup_conn = sqlite3.connect(backup_path)
    try:
        source_conn.backup(backup_conn)
    except Exception:
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass
        raise
    finally:
        backup_conn.close()
        source_conn.close()

    final_path = backup_path
    if compress:
        gz_path = backup_path + ".gz"
        with open(backup_path, "rb") as raw, gzip.open(gz_path, "wb", compresslevel=6) as gz:
            shutil.copyfileobj(raw, gz)
        os.remove(backup_path)
        final_path = gz_path

    # Rotate old backups (safety if keep changed or races added files)
    backups = _sorted_backup_paths()
    while len(backups) > int(keep):
        os.remove(backups.pop(0))

    size_mb = os.path.getsize(final_path) / (1024 * 1024)
    retained = len(_sorted_backup_paths())
    integrity = verify_backup_integrity(final_path)
    print(f"  Backup created: {final_path} ({size_mb:.1f} MB)")
    print(f"  Backups retained: {retained}")
    if integrity.get("ok"):
        print("  Backup integrity: quick_check ok")
    else:
        print(f"  Backup integrity FAILED: {integrity.get('quick_check') or integrity.get('error')}")

    return final_path


def restore_backup(backup_path: str) -> bool:
    """
    Restore the database from a backup file.

    Args:
        backup_path: Path to the backup file.

    Returns:
        True if restored successfully.
    """
    if not os.path.exists(backup_path):
        print(f"  Backup not found: {backup_path}")
        return False

    db_path = _current_db_path()
    if os.path.exists(db_path):
        pre_restore = db_path + ".pre_restore"
        shutil.copy2(db_path, pre_restore)
        print(f"  Current DB saved to: {pre_restore}")

    if backup_path.endswith(".gz"):
        with gzip.open(backup_path, "rb") as gz, open(db_path, "wb") as out:
            shutil.copyfileobj(gz, out)
        print(f"  Restored from gzip: {backup_path}")
        return True

    shutil.copy2(backup_path, db_path)
    print(f"  Restored from: {backup_path}")
    return True


def list_backups() -> list[dict]:
    """List all available backups."""
    if not os.path.exists(BACKUP_DIR):
        return []

    paths: list[str] = []
    for pattern in _backup_globs():
        paths.extend(glob.glob(pattern))
    paths = list(set(paths))
    backups = sorted(paths, key=lambda p: os.path.getmtime(p), reverse=True)
    results = []
    for path in backups:
        size_mb = os.path.getsize(path) / (1024 * 1024)
        name = os.path.basename(path)
        results.append({
            "path": path,
            "name": name,
            "size_mb": round(size_mb, 1),
            "created": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
        })
    return results


if __name__ == "__main__":
    import argparse

    _env_keep_raw = (os.environ.get("DEPLOY_BACKUP_KEEP") or "").strip()
    try:
        _default_keep = int(_env_keep_raw) if _env_keep_raw else 7
    except ValueError:
        _default_keep = 7
    if _default_keep < 1:
        _default_keep = 7

    parser = argparse.ArgumentParser(description="Database backup utility")
    parser.add_argument("--keep", type=int, default=_default_keep, help="Number of backups to keep")
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Gzip the new backup to .db.gz (off by default; explicit opt-in).",
    )
    parser.add_argument("--list", action="store_true", help="List available backups")
    parser.add_argument("--restore", type=str, help="Restore from a backup file")
    parser.add_argument(
        "--print-path",
        action="store_true",
        help="Print the authoritative DB path and exit (for shell scripts).",
    )
    parser.add_argument(
        "--print-backup-dir",
        action="store_true",
        help="Print the backup directory path and exit (for shell scripts).",
    )
    args = parser.parse_args()

    if args.print_path:
        print(_current_db_path())
    elif args.print_backup_dir:
        print(BACKUP_DIR)
    elif args.list:
        backups = list_backups()
        if not backups:
            print("  No backups found.")
        else:
            for b in backups:
                print(f"  {b['name']} ({b['size_mb']} MB) — {b['created']}")
    elif args.restore:
        restore_backup(args.restore)
    else:
        create_backup(keep=args.keep, compress=args.compress)
