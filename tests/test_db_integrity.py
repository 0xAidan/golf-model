"""Tests for cheap SQLite smoke probes and corrupt classification."""

from __future__ import annotations

import sqlite3

from src.db_integrity import (
    classify_sqlite_error,
    is_busy_error,
    is_corrupt_error,
    live_db_status_fields,
    probe_sqlite_file,
)


def test_is_corrupt_error_matches_malformed() -> None:
    assert is_corrupt_error(sqlite3.DatabaseError("database disk image is malformed"))
    assert is_corrupt_error(Exception("file is not a database"))
    assert not is_corrupt_error(sqlite3.OperationalError("database is locked"))


def test_classify_busy_and_timeout() -> None:
    assert classify_sqlite_error(sqlite3.OperationalError("database is locked")) == "busy"
    assert is_busy_error(sqlite3.OperationalError("database is locked"))
    assert classify_sqlite_error(TimeoutError("timed out")) == "timeout"


def test_probe_sqlite_file_ok(tmp_path) -> None:
    path = tmp_path / "ok.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.close()
    result = probe_sqlite_file(str(path))
    assert result["ok"] is True
    assert result["state"] == "ok"
    assert result["table_count"] >= 1


def test_probe_sqlite_file_corrupt(tmp_path) -> None:
    path = tmp_path / "bad.db"
    path.write_bytes(b"not a sqlite database")
    result = probe_sqlite_file(str(path))
    assert result["ok"] is False
    assert result["state"] == "corrupt"


def test_probe_sqlite_file_missing(tmp_path) -> None:
    result = probe_sqlite_file(str(tmp_path / "missing.db"))
    assert result["ok"] is False
    assert result["state"] == "missing"


def test_live_db_status_rebuilding_until_event_matches(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "golf.db"
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.close()
    snapshot = tmp_path / "live_refresh_snapshot.json"
    snapshot.write_text(
        '{"live_tournament": {"event_id": "old", "event_name": "Last week"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GOLF_DB_PATH", str(db_path))
    monkeypatch.setenv("GOLF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "src.db_integrity.read_heartbeat",
        lambda: {"phase": "idle", "target_event_id": "new"},
    )
    monkeypatch.setattr("src.db_integrity.get_db_path", lambda: db_path)
    monkeypatch.setattr("src.db_integrity.get_snapshot_path", lambda: snapshot)
    fields = live_db_status_fields()
    assert fields["db_ok"] is True
    assert fields["rebuild_state"] == "rebuilding"
    assert fields["target_event_id"] == "new"
    assert fields["snapshot_event_id"] == "old"
