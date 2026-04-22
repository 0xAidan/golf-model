"""Tests for ``src.backup`` CLI and DB-path resolution.

These lock in the contract that shell scripts (``deploy.sh``) rely on:

* ``python -m src.backup --print-path`` prints the authoritative DB path
  that ``src.db`` is currently using.
* ``_current_db_path()`` tracks ``src.db.DB_PATH`` at call time, so test
  and ops tooling that mutate the DB path stay in sync.
* ``create_backup()`` and ``restore_backup()`` use the live ``src.db.DB_PATH``
  (not a stale module-level copy) so that the backup is always of the DB
  the rest of the system is writing to.

Regression target: the deploy script previously hardcoded
``/opt/golf-model/data/golf.db`` in its shell checks and would silently
skip the pre-update backup or report "No database found" when the
resolved DB path differed from the hardcoded one. See
``docs/recovery_defect_register.md`` P0 items 1 & 2.
"""

from __future__ import annotations

import os
import subprocess
import sys
import sqlite3
import tempfile


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_print_path_matches_db_module_path() -> None:
    """``--print-path`` must print the same path ``src.db.DB_PATH`` resolves to.

    Shell callers use this to discover the DB path without parsing Python.
    If this drifts, deploy backup/status checks operate on the wrong file.
    """
    expected = subprocess.run(
        [sys.executable, "-c", "import src.db; print(src.db.DB_PATH)"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()

    got = subprocess.run(
        [sys.executable, "-m", "src.backup", "--print-path"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert got == expected, f"--print-path drift: got {got!r}, expected {expected!r}"


def test_print_backup_dir_is_stable_under_repo() -> None:
    """``--print-backup-dir`` must point inside the repo's ``backups/`` folder."""
    result = subprocess.run(
        [sys.executable, "-m", "src.backup", "--print-backup-dir"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    out = result.stdout.strip()
    assert out.endswith(os.sep + "backups"), f"unexpected backup dir: {out!r}"
    assert os.path.isabs(out), "backup dir should be absolute"


def test_current_db_path_tracks_live_db_module() -> None:
    """``_current_db_path()`` must read ``src.db.DB_PATH`` at call time.

    If ``_current_db_path`` cached the import-time value, ``create_backup``
    and ``restore_backup`` would operate on the original DB even after a
    test fixture repoints ``db.DB_PATH`` at a temp file.
    """
    import src.db as db
    import src.backup as backup

    original_path = db.DB_PATH
    try:
        tmp = os.path.join(tempfile.gettempdir(), "golf_test_drift.db")
        db.DB_PATH = tmp
        assert backup._current_db_path() == tmp
    finally:
        db.DB_PATH = original_path


def test_create_backup_uses_live_db_path(tmp_db) -> None:
    """``create_backup`` must back up whatever DB ``src.db`` is currently using.

    Uses the ``tmp_db`` fixture, which mutates ``src.db.DB_PATH`` to a
    temporary file. A stale module-level ``DB_PATH`` in ``src.backup``
    would cause the backup to target the wrong file (or skip silently
    because the wrong path doesn't exist).
    """
    import src.backup as backup

    # Seed a row so the DB file is non-empty; backup should copy it.
    with tmp_db.get_conn() as conn:
        conn.execute(
            "INSERT INTO runs (status, result_json) VALUES (?, ?)",
            ("ok", '{"test": true}'),
        )
        conn.commit()

    # Redirect the backup dir so we don't clutter the repo's backups/ folder.
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = tempfile.mkdtemp(prefix="golf_backup_test_")
        result = backup.create_backup(keep=3)
        assert result is not None, "create_backup returned None despite live DB"
        assert os.path.exists(result)
        # The backup file must be a real SQLite DB (not empty / not a stale copy).
        with sqlite3.connect(result) as snap:
            tables = snap.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
            ).fetchall()
            assert tables, "backup does not contain expected 'runs' table"
    finally:
        backup.BACKUP_DIR = original_backup_dir
