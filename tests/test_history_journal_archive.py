"""History journal archive: rows leave the database only after a verified archive holds them."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("zstd") is None, reason="zstd binary not installed")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


arch = _load("history_journal_archive")
compact = _load("build_compact_db")


def _make_db(path: Path, n: int = 300, *, days_old_for_first: int = 0) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
    conn.execute(arch.TABLE_SQL)
    conn.execute("CREATE TABLE metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, player TEXT, value REAL)")
    conn.execute("CREATE INDEX idx_metrics_player ON metrics(player)")
    conn.execute("CREATE VIEW v_metrics AS SELECT player, value FROM metrics")
    now = dt.datetime.now(dt.timezone.utc)
    for i in range(1, n + 1):
        payload = json.dumps({"id": i, "player": f"p{i % 7}", "value": i / 3}, sort_keys=True, separators=(",", ":"))
        at = now - dt.timedelta(days=days_old_for_first) + dt.timedelta(minutes=i)
        conn.execute(
            f"INSERT INTO {arch.TABLE} (id, source_table, source_row_id, payload_sha256, payload_json, reason, preserved_at)"
            " VALUES (?, 'metrics', ?, ?, ?, 'store_metrics_update', ?)",
            (i, str(i), hashlib.sha256(payload.encode()).hexdigest(), payload, at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")),
        )
        conn.execute("INSERT INTO metrics (player, value) VALUES (?, ?)", (f"p{i}", float(i)))
    conn.commit()
    conn.close()


def _ids(path: Path) -> list[int]:
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute(f"SELECT id FROM {arch.TABLE} ORDER BY id")]
    finally:
        conn.close()


def test_export_verify_prune_restore_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "golf.db"
    archive = tmp_path / "archive"
    _make_db(db)
    manifest = arch.export(str(db), archive, 200)
    assert manifest["rows"] == 200 and manifest["first_id"] == 1 and manifest["last_id"] == 200
    assert arch.export(str(db), archive, 200) is None  # nothing new to archive

    [result] = arch.verify(archive, str(db))
    assert result["ok"] and result["db_status"] == "identical"

    arch.prune(str(db), archive)
    assert _ids(db) == list(range(201, 301))
    [after] = arch.verify(archive, str(db))
    assert after["ok"] and after["db_status"] == "range already pruned from this database"

    restored = tmp_path / "restored.db"
    assert arch.restore(archive, str(restored)) == 200
    [check] = arch.verify(archive, str(restored))
    assert check["ok"] and check["db_status"] == "identical"


def test_prune_refuses_when_database_row_differs_from_archive(tmp_path: Path) -> None:
    db = tmp_path / "golf.db"
    archive = tmp_path / "archive"
    _make_db(db)
    arch.export(str(db), archive, 100)
    conn = sqlite3.connect(db)
    conn.execute(f"UPDATE {arch.TABLE} SET reason = 'changed' WHERE id = 50")
    conn.commit()
    conn.close()
    with pytest.raises(arch.ArchiveError):
        arch.prune(str(db), archive)
    assert len(_ids(db)) == 300


def test_prune_refuses_when_archive_file_is_damaged(tmp_path: Path) -> None:
    db = tmp_path / "golf.db"
    archive = tmp_path / "archive"
    _make_db(db)
    manifest = arch.export(str(db), archive, 100)
    with open(archive / manifest["file"], "ab") as fh:
        fh.write(b"garbage")
    with pytest.raises(arch.ArchiveError):
        arch.prune(str(db), archive)
    assert len(_ids(db)) == 300


def test_older_than_days_always_keeps_newest_row(tmp_path: Path) -> None:
    db = tmp_path / "golf.db"
    _make_db(db, n=50, days_old_for_first=400)  # every row is far older than the cutoff
    through = arch.resolve_through_id(str(db), through_id=None, older_than_days=30)
    assert through == 49


def test_compact_copy_drops_only_archived_journal_rows(tmp_path: Path) -> None:
    db = tmp_path / "golf.db"
    _make_db(db)
    dest = tmp_path / "golf.db.compact"
    report = compact.build(str(db), str(dest), keep_after_id=200)
    assert report["integrity_check"] == "ok"
    assert report["journal_rows_kept"] == 100
    conn = sqlite3.connect(dest)
    try:
        assert conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 300
        assert conn.execute("SELECT COUNT(*) FROM v_metrics").fetchone()[0] == 300
        seq = dict(conn.execute("SELECT name, seq FROM sqlite_sequence").fetchall())
        assert seq[arch.TABLE] == 300 and seq["metrics"] == 300
        assert conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()
    assert _ids(dest) == list(range(201, 301))
