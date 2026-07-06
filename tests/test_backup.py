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

