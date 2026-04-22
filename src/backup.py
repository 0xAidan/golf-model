"""
Database Backup Utility

Creates timestamped backups of the SQLite database.
Keeps the last N backups and auto-rotates.

Usage:
    python -m src.backup                     # Create a backup now
    python -m src.backup --keep 10           # Keep last 10 backups
    python -m src.backup --print-path        # Print authoritative DB path (for shell scripts)
    python -m src.backup --print-backup-dir  # Print backup directory path
"""

import os
import shutil
import glob
from datetime import datetime

from src import db


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


def create_backup(keep: int = 7) -> str | None:
    """
    Create a timestamped backup of the database.

    Args:
        keep: Number of recent backups to keep (older ones deleted).

    Returns:
        Path to the new backup file, or None if DB doesn't exist.
    """
    db_path = _current_db_path()
    if not os.path.exists(db_path):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"golf_model_{timestamp}.db")

    shutil.copy2(db_path, backup_path)

    # Rotate old backups
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "golf_model_*.db")))
    while len(backups) > keep:
        os.remove(backups.pop(0))

    size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"  Backup created: {backup_path} ({size_mb:.1f} MB)")
    print(f"  Backups retained: {min(len(backups) + 1, keep)}")

    return backup_path


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

    # Create a backup of current DB before restoring
    db_path = _current_db_path()
    if os.path.exists(db_path):
        pre_restore = db_path + ".pre_restore"
        shutil.copy2(db_path, pre_restore)
        print(f"  Current DB saved to: {pre_restore}")

    shutil.copy2(backup_path, db_path)
    print(f"  Restored from: {backup_path}")
    return True


def list_backups() -> list[dict]:
    """List all available backups."""
    if not os.path.exists(BACKUP_DIR):
        return []

    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "golf_model_*.db")), reverse=True)
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
    parser = argparse.ArgumentParser(description="Database backup utility")
    parser.add_argument("--keep", type=int, default=7, help="Number of backups to keep")
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
        create_backup(keep=args.keep)
