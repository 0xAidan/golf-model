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


def test_verify_backup_integrity_missing_file() -> None:
    result = backup.verify_backup_integrity("/tmp/does-not-exist-golf-backup.db")
    assert result["ok"] is False
    assert "not found" in (result.get("error") or "").lower()
