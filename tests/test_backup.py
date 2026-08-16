"""Tests for backup integrity verification."""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

import src.backup as backup


def test_verify_backup_integrity_ok(tmp_db) -> None:
    with tmp_db.get_conn() as conn:
        conn.execute(
            "INSERT INTO runs (status, result_json) VALUES (?, ?)",
            ("ok", '{"integrity": true}'),
        )
        conn.commit()

    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = tempfile.mkdtemp(prefix="golf_backup_integrity_")
        path = backup.create_backup(keep=2)
        assert path is not None
        result = backup.verify_backup_integrity(path)
        assert result["ok"] is True
        assert result["quick_check"] == "ok"
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_verify_backup_integrity_detects_corrupt_file(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    result = backup.verify_backup_integrity(str(corrupt))
    assert result["ok"] is False


def test_verify_backup_integrity_gzip(tmp_db) -> None:
    with tmp_db.get_conn() as conn:
        conn.execute(
            "INSERT INTO runs (status, result_json) VALUES (?, ?)",
            ("ok", '{"gzip": true}'),
        )
        conn.commit()

    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = tempfile.mkdtemp(prefix="golf_backup_gz_integrity_")
        path = backup.create_backup(keep=2, compress=True)
        assert path is not None
        result = backup.verify_backup_integrity(path)
        assert result["ok"] is True
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_prune_old_backups_removes_sidecars(tmp_db, tmp_path) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        db1 = tmp_path / "golf_model_20260101_120000.db"
        db2 = tmp_path / "golf_model_20260201_120000.db"
        db3 = tmp_path / "golf_model_20260301_120000.db"
        db1.write_bytes(b"sqlite")
        db2.write_bytes(b"sqlite")
        db3.write_bytes(b"sqlite")
        (tmp_path / "golf_model_20260101_120000.db-shm").write_bytes(b"shm")
        (tmp_path / "golf_model_20260101_120000.db-wal").write_bytes(b"wal")
        os.utime(db1, (1_000, 1_000))
        os.utime(db2, (2_000, 2_000))
        os.utime(db3, (3_000, 3_000))

        removed = backup.prune_old_backups(1)

        assert str(db1) in removed
        assert str(db2) in removed
        assert db1.exists() is False
        assert db2.exists() is False
        assert (tmp_path / "golf_model_20260101_120000.db-shm").exists() is False
        assert (tmp_path / "golf_model_20260101_120000.db-wal").exists() is False
        assert db3.exists() is True
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_sweep_orphan_sidecars_removes_unmatched(tmp_path) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        orphan = tmp_path / "golf_model_20260101_120000.db-shm"
        orphan.write_bytes(b"orphan")
        kept = tmp_path / "golf_model_20260201_120000.db"
        kept.write_bytes(b"sqlite")
        (tmp_path / "golf_model_20260201_120000.db-wal").write_bytes(b"wal")

        removed = backup.sweep_orphan_sidecars()

        assert str(orphan) in removed
        assert orphan.exists() is False
        assert (tmp_path / "golf_model_20260201_120000.db-wal").exists() is True
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_create_backup_refuses_below_disk_hard_floor(tmp_db, monkeypatch, tmp_path) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        monkeypatch.setenv("DISK_FREE_MB_HARD", "999999999")
        with pytest.raises(RuntimeError, match="Refusing backup"):
            backup.create_backup(keep=2)
    finally:
        backup.BACKUP_DIR = original_backup_dir
        monkeypatch.delenv("DISK_FREE_MB_HARD", raising=False)



def test_prune_until_space_available_removes_oldest(tmp_path, monkeypatch) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        older = tmp_path / "golf_model_20260101_120000.db"
        newer = tmp_path / "golf_model_20260201_120000.db"
        older.write_bytes(b"x" * 1024)
        newer.write_bytes(b"y" * 1024)
        os.utime(older, (1_000, 1_000))
        os.utime(newer, (2_000, 2_000))

        free_values = [100, 10_000_000]
        monkeypatch.setattr(backup, "_free_bytes", lambda _path: free_values.pop(0) if free_values else 10_000_000)

        removed = backup.prune_until_space_available(
            needed_bytes=5_000,
            repo_root=str(tmp_path),
            min_keep=1,
        )
        assert str(older) in removed
        assert older.exists() is False
        assert newer.exists() is True
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_create_backup_integrity_failure_is_nonzero(tmp_db, tmp_path, monkeypatch) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        monkeypatch.setattr(
            backup,
            "verify_backup_integrity",
            lambda _path: {"ok": False, "error": "malformed", "quick_check": "malformed"},
        )
        monkeypatch.delenv("DISK_FREE_MB_HARD", raising=False)
        with pytest.raises(backup.BackupIntegrityError, match="malformed"):
            backup.create_backup(keep=2)
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_restore_backup_removes_wal_and_smoke_checks(tmp_db, tmp_path) -> None:
    original_backup_dir = backup.BACKUP_DIR
    original_db_path = backup.db.DB_PATH
    try:
        backup.BACKUP_DIR = str(tmp_path)
        live = tmp_path / "live.db"
        conn = sqlite3.connect(live)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t (id) VALUES (1)")
        conn.commit()
        conn.close()
        backup.db.DB_PATH = str(live)
        path = backup.create_backup(keep=2)
        assert path is not None
        (tmp_path / "live.db-wal").write_bytes(b"stale-wal")
        (tmp_path / "live.db-shm").write_bytes(b"stale-shm")
        live.write_bytes(b"broken")
        assert backup.restore_backup(path) is True
        assert not (tmp_path / "live.db-wal").exists()
        assert not (tmp_path / "live.db-shm").exists()
        conn = sqlite3.connect(live)
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
        conn.close()
    finally:
        backup.BACKUP_DIR = original_backup_dir
        backup.db.DB_PATH = original_db_path


def test_restore_backup_refuses_bad_integrity(tmp_path) -> None:
    bad = tmp_path / "golf_model_20260101_000000.db"
    bad.write_bytes(b"not sqlite")
    assert backup.restore_backup(str(bad)) is False


def test_create_backup_prunes_for_disk_headroom(tmp_db, tmp_path, monkeypatch) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        stale1 = tmp_path / "golf_model_20260101_120000.db"
        stale2 = tmp_path / "golf_model_20260201_120000.db"
        stale1.write_bytes(b"stale1")
        stale2.write_bytes(b"stale2")
        os.utime(stale1, (1_000, 1_000))
        os.utime(stale2, (2_000, 2_000))

        # First free check inside prune_until is tiny; after pruning, enough space.
        free_seq = [10, 10**12, 10**12, 10**12, 10**12]
        monkeypatch.setattr(backup, "_free_bytes", lambda _p: free_seq.pop(0) if free_seq else 10**12)
        monkeypatch.setattr(backup, "_bytes_needed_for_new_backup", lambda *_a, **_k: 100)
        monkeypatch.delenv("DISK_FREE_MB_HARD", raising=False)

        path = backup.create_backup(keep=2, compress=False)
        assert path is not None
        assert stale1.exists() is False  # pruned for headroom (oldest)
        assert os.path.isfile(path)
        assert os.path.isfile(path + ".integrity.json")
    finally:
        backup.BACKUP_DIR = original_backup_dir
