"""
Database Backup Utility

Creates timestamped backups of the SQLite database.
Keeps the last N backups and auto-rotates.

Usage:
    python -m src.backup              # Create a backup now
    python -m src.backup --keep 10    # Keep last 10 backups
"""

import os
import shutil
import glob
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "golf.db")
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")


def create_backup(keep: int = 7) -> str | None:
    """
    Create a timestamped backup of the database.

    Args:
        keep: Number of recent backups to keep (older ones deleted).

    Returns:
        Path to the new backup file, or None if DB doesn't exist.
    """
    if not os.path.exists(DB_PATH):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"golf_model_{timestamp}.db")

    shutil.copy2(DB_PATH, backup_path)

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
    if os.path.exists(DB_PATH):
        pre_restore = DB_PATH + ".pre_restore"
        shutil.copy2(DB_PATH, pre_restore)
        print(f"  Current DB saved to: {pre_restore}")

    shutil.copy2(backup_path, DB_PATH)
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
    args = parser.parse_args()

    if args.list:
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
