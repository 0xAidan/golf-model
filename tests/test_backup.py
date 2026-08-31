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


def test_create_backup_sweeps_leftover_temp_before_creating(tmp_db, monkeypatch, tmp_path) -> None:
    leftover = tmp_path / "tmplwd_zutb.db"
    leftover.write_bytes(b"stale-unpacked-backup")
    os.utime(leftover, (1_000, 1_000))
    monkeypatch.setenv("STORAGE_JANITOR_TMP_DIR", str(tmp_path))
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path / "backups")
        os.makedirs(backup.BACKUP_DIR, exist_ok=True)
        path = backup.create_backup(keep=1)
        assert path is not None
        assert leftover.exists() is False
        assert os.path.isfile(path) is True
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_create_backup_refuses_when_it_cannot_fit(tmp_db, monkeypatch, tmp_path) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = str(tmp_path)
        monkeypatch.setattr(
            backup,
            "can_fit_backup",
            lambda *args, **kwargs: {
                "ok": False,
                "free_bytes": 100,
                "needed_bytes": 10 * 1024 * 1024 * 1024,
                "db_bytes": 9 * 1024 * 1024 * 1024,
                "margin_bytes": backup.BACKUP_FIT_MARGIN_BYTES,
            },
        )
        with pytest.raises(RuntimeError, match="Refusing backup"):
            backup.create_backup(keep=2)
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_create_backup_writes_integrity_sidecar(tmp_db) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = tempfile.mkdtemp(prefix="golf_backup_sidecar_")
        path = backup.create_backup(keep=2)
        assert path is not None
        sidecar = backup.read_integrity_sidecar(path)
        assert sidecar is not None
        assert sidecar["ok"] is True
        assert sidecar["quick_check"] == "ok"
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_verify_gzip_trusts_sidecar_without_decompress(tmp_db, monkeypatch) -> None:
    original_backup_dir = backup.BACKUP_DIR
    try:
        backup.BACKUP_DIR = tempfile.mkdtemp(prefix="golf_backup_sidecar_gz_")
        path = backup.create_backup(keep=2, compress=True)
        assert path is not None

        def _boom(*_args, **_kwargs):
            raise AssertionError("should not decompress when sidecar is trusted")

        monkeypatch.setattr(backup.gzip, "open", _boom)
        result = backup.verify_backup_integrity(path)
        assert result["ok"] is True
        assert result["skipped"] is True
        assert result["skip_reason"] == "trusted_sidecar"
    finally:
        backup.BACKUP_DIR = original_backup_dir


def test_verify_gzip_skips_decompress_when_disk_tight(tmp_path, monkeypatch) -> None:
    gz_path = tmp_path / "golf_model_20260101_120000.db.gz"
    gz_path.write_bytes(b"\x1f\x8bnot-a-real-sqlite-backup")
    monkeypatch.setattr(
        backup.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": 1024, "total": 2048, "used": 1024})(),
    )
    result = backup.verify_backup_integrity(str(gz_path), allow_sidecar=False)
    assert result["ok"] is False
    assert result["skipped"] is True
    assert result["skip_reason"] == "insufficient_disk_for_decompress"


def test_restore_backup_moves_live_file_and_drops_wal(tmp_path, monkeypatch) -> None:
    live = tmp_path / "golf.db"
    live.write_bytes(b"corrupt-bytes")
    (tmp_path / "golf.db-wal").write_bytes(b"old-wal")
    (tmp_path / "golf.db-shm").write_bytes(b"old-shm")
    good = tmp_path / "good.db"
    conn = sqlite3.connect(good)
    conn.execute("CREATE TABLE restored (id INTEGER)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(backup.db, "DB_PATH", str(live))
    backup.db.reset_db_availability()
    assert backup.restore_backup(str(good)) is True
    assert (tmp_path / "golf.db-wal").exists() is False
    assert (tmp_path / "golf.db-shm").exists() is False
    asides = list(tmp_path.glob("golf.db.malformed_*"))
    assert asides
    check = sqlite3.connect(f"file:{live}?mode=ro", uri=True)
    try:
        assert check.execute("SELECT name FROM sqlite_master WHERE name='restored'").fetchone()
    finally:
        check.close()


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

