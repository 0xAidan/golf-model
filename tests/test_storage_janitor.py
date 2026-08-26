"""Disposable leftover sweeps — never touch the live database."""

from __future__ import annotations

import os
import time

from src.storage_janitor import sweep_disposable_storage, sweep_os_tmp_leftovers


def test_janitor_removes_old_tmp_db_and_skips_live_db(tmp_path) -> None:
    leftover = tmp_path / "tmplwd_zutb.db"
    leftover.write_bytes(b"leftover-copy")
    live = tmp_path / "tmpkeepme1.db"
    live.write_bytes(b"live-database")
    young = tmp_path / "tmpyoung99.db"
    young.write_bytes(b"too-new")

    old = time.time() - 3 * 60 * 60
    os.utime(leftover, (old, old))
    os.utime(live, (old, old))

    report = sweep_os_tmp_leftovers(
        tmp_dir=tmp_path,
        db_path=str(live),
        min_age_seconds=2 * 60 * 60,
    )

    assert leftover.exists() is False
    assert live.exists() is True
    assert young.exists() is True
    assert report["bytes_freed"] >= len(b"leftover-copy")
    assert any(item["path"] == str(leftover) for item in report["removed"])


def test_janitor_removes_old_golf_backup_test_dir(tmp_path) -> None:
    junk = tmp_path / "golf_backup_integrity_abc123"
    junk.mkdir()
    payload = junk / "scratch.db"
    payload.write_bytes(b"scratch")
    old = time.time() - 2 * 24 * 60 * 60
    os.utime(payload, (old, old))
    os.utime(junk, (old, old))

    pidfile = tmp_path / "golf_live_refresh.pid"
    pidfile.write_text("1234")

    report = sweep_os_tmp_leftovers(
        tmp_dir=tmp_path,
        db_path=str(tmp_path / "golf.db"),
        dir_min_age_seconds=24 * 60 * 60,
    )

    assert junk.exists() is False
    assert pidfile.exists() is True
    assert report["count"] == 1


def test_sweep_disposable_storage_cleans_managed_backup_tmp(tmp_path, tmp_db) -> None:
    backup_tmp = tmp_path / "backup-tmp"
    backup_tmp.mkdir()
    stale = backup_tmp / "golf_integrity_old.db"
    stale.write_bytes(b"decompressed-copy")
    old = time.time() - 3 * 60 * 60
    os.utime(stale, (old, old))

    report = sweep_disposable_storage(
        tmp_dir=tmp_path / "os-tmp",
        backup_tmp_dir=backup_tmp,
        db_path=tmp_db.DB_PATH,
        min_age_seconds=2 * 60 * 60,
    )

    assert stale.exists() is False
    assert os.path.exists(tmp_db.DB_PATH) is True
    assert report["ok"] is True
    assert report["bytes_freed"] >= len(b"decompressed-copy")
