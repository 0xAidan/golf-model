"""Append-only backup checks use private SQLite fixtures, never app initialization."""

from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import snapshot_backup as backup


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE history (id INTEGER PRIMARY KEY, result TEXT)")
    conn.execute("INSERT INTO history VALUES (1, 'original result')")
    conn.commit()
    destination = tmp_path / "backups"
    destination.mkdir()
    yield path, destination, conn
    conn.close()


def _backup(source, **kwargs):
    path, destination, _ = source
    return backup.create_snapshot_backup(path, destination, reserve_mib=0, min_free_mib=0, **kwargs)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wal_consistent_backup_is_verified_and_leaves_source_unchanged(source, tmp_path):
    path, destination, writer = source
    writer.execute("INSERT INTO history VALUES (2, 'committed in WAL')")
    writer.commit()
    wal = Path(str(path) + "-wal")
    before = {p: _hash(p) for p in (path, wal)}
    manifest = _backup(source)
    artifact = Path(manifest["path"])
    assert artifact.parent == destination
    assert artifact.match("golf_model_*.db.gz")
    assert manifest["ok"] is True
    assert manifest["quick_check"] == manifest["integrity_check"] == "ok"
    assert manifest["source_read_only"] is True
    assert manifest["compression_round_trip_verified"] is True
    assert _hash(artifact) == manifest["sha256"]
    restored = gzip.decompress(artifact.read_bytes())
    assert hashlib.sha256(restored).hexdigest() == manifest["sqlite_sha256"]
    assert len(restored) == manifest["uncompressed_bytes"]
    restored_path = tmp_path / "restored-test.sqlite"
    restored_path.write_bytes(restored)
    with sqlite3.connect(restored_path.as_uri() + "?mode=ro", uri=True) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert conn.execute("SELECT * FROM history ORDER BY id").fetchall() == [(1, "original result"), (2, "committed in WAL")]
    assert before == {p: _hash(p) for p in before}
    assert json.loads(Path(str(artifact) + ".integrity.json").read_text()) == manifest
    assert not list(destination.glob(".golf_snapshot_*"))


def test_repeated_backups_append_without_removing_or_replacing_history(source):
    _, directory, _ = source
    sentinel = directory / "old-backup.db.gz"
    sentinel.write_bytes(b"preserve old evidence")
    first = _backup(source)
    first_path = Path(first["path"])
    before = _hash(first_path)
    second = _backup(source)
    assert second["path"] != first["path"]
    assert first_path.is_file() and _hash(first_path) == before
    assert sentinel.read_bytes() == b"preserve old evidence"
    assert len(list(directory.glob("golf_model_*.db.gz"))) == 2


def test_missing_source_never_creates_a_database(tmp_path):
    path = tmp_path / "missing.sqlite"
    with pytest.raises(backup.BackupError, match="no database was created"):
        backup.create_snapshot_backup(path, tmp_path, reserve_mib=0, min_free_mib=0)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_corrupt_source_is_unchanged_and_publishes_nothing(tmp_path):
    path = tmp_path / "corrupt.sqlite"
    path.write_bytes(b"This is not a SQLite database.")
    directory = tmp_path / "backups"
    directory.mkdir()
    before = _hash(path)
    with pytest.raises(sqlite3.DatabaseError):
        backup.create_snapshot_backup(path, directory, reserve_mib=0, min_free_mib=0)
    assert _hash(path) == before
    assert list(directory.iterdir()) == []


def test_staged_and_published_artifacts_are_private_even_with_permissive_umask(source, monkeypatch):
    publish = backup._publish_new
    checked_paths = []

    def check_private_then_publish(source_path, destination):
        assert stat.S_IMODE(source_path.stat().st_mode) == 0o600
        publish(source_path, destination)
        checked_paths.append(destination)

    monkeypatch.setattr(backup, "_publish_new", check_private_then_publish)
    original_umask = os.umask(0)
    try:
        _backup(source)
    finally:
        os.umask(original_umask)
    assert len(checked_paths) == 2
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in checked_paths)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_time_limits_are_rejected(source, timeout):
    with pytest.raises(backup.BackupError, match="Invalid"):
        _backup(source, timeout_seconds=timeout)
    assert list(source[1].iterdir()) == []


@pytest.mark.parametrize("free_bytes", [1, backup.MIB])
def test_insufficient_footprint_or_reserve_is_rejected_before_copy(source, monkeypatch, free_bytes):
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda path: SimpleNamespace(free=free_bytes))
    with pytest.raises(backup.BackupError, match="insufficient free space"):
        _backup(source)
    assert list(source[1].iterdir()) == []


def test_initial_disk_floor_is_retained(source, monkeypatch):
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda path: SimpleNamespace(free=4 * backup.MIB))
    with pytest.raises(backup.BackupError, match="initial hard floor"):
        backup.create_snapshot_backup(source[0], source[1], min_free_mib=5, reserve_mib=0)
    assert list(source[1].iterdir()) == []


def test_time_limit_is_bounded_and_cleans_only_private_temporary_files(source):
    old = source[1] / "existing-file"
    old.write_text("keep")
    with pytest.raises(backup.BackupError, match="time limit"):
        _backup(source, timeout_seconds=1e-12)
    assert list(source[1].iterdir()) == [old]


@pytest.mark.parametrize("phase", ["integrity", "compression"])
def test_failure_cleanup_never_touches_other_backups_or_source(source, monkeypatch, phase):
    path, directory, _ = source
    sentinel = directory / "golf_model_old.db.gz"
    sentinel.write_bytes(b"old backup")
    before = _hash(path)

    def fail(*args):
        if phase == "compression":
            args[1].write_bytes(b"partial gzip owned by this invocation")
        raise backup.BackupError("Injected verification failure.")

    monkeypatch.setattr(backup, "_verify_database" if phase == "integrity" else "_compress_and_verify", fail)
    with pytest.raises(backup.BackupError, match="verification failure"):
        _backup(source)
    assert list(directory.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"old backup"
    assert _hash(path) == before


def test_publication_collision_cannot_replace_existing_backup(source, monkeypatch):
    class FixedTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 14, 3, tzinfo=timezone.utc)

    monkeypatch.setattr(backup, "datetime", FixedTime)
    monkeypatch.setattr(backup.uuid, "uuid4", lambda: SimpleNamespace(hex="1" * 32))
    manifest = _backup(source)
    paths = [Path(manifest["path"]), Path(manifest["path"] + ".integrity.json")]
    before = {path: _hash(path) for path in paths}
    with pytest.raises(FileExistsError):
        _backup(source)
    assert before == {path: _hash(path) for path in paths}
    assert not list(source[1].glob(".golf_snapshot_*"))


def test_sidecar_failure_retains_already_verified_published_gzip(source, monkeypatch):
    publish = backup._publish_new

    def fail_manifest(source_path, destination):
        if destination.name.endswith(".integrity.json"):
            raise OSError("Injected manifest publication failure")
        publish(source_path, destination)

    monkeypatch.setattr(backup, "_publish_new", fail_manifest)
    with pytest.raises(OSError, match="manifest publication failure"):
        _backup(source)
    artifacts = list(source[1].glob("*.db.gz"))
    assert len(artifacts) == 1
    assert gzip.decompress(artifacts[0].read_bytes()).startswith(b"SQLite format 3")
    assert not list(source[1].glob(".golf_snapshot_*"))


def test_script_is_stdlib_only_and_does_not_import_application():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([
        sys.executable, "-I", "-S", "-B", "-c",
        "import runpy,sys; runpy.run_path(sys.argv[1],run_name='backup_import_test'); "
        "assert not any(n == 'app' or n.startswith(('src', 'backtester')) for n in sys.modules)",
        str(root / "scripts/snapshot_backup.py"),
    ], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
