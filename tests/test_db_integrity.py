from __future__ import annotations

import sqlite3

import src.db as db
from src import db_integrity


def test_probe_ok(tmp_path):
    path = tmp_path / "ok.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    result = db_integrity.probe_sqlite_file(str(path))
    assert result["ok"] is True
    assert result["classification"] == "ok"


def test_probe_not_a_database(tmp_path):
    path = tmp_path / "bad.db"
    path.write_bytes(b"nope")
    result = db_integrity.probe_sqlite_file(str(path))
    assert result["ok"] is False
    assert result["classification"] == "not_a_database"


def test_maybe_auto_restore_skips_when_disabled(tmp_path, monkeypatch):
    path = tmp_path / "bad.db"
    path.write_bytes(b"nope")
    monkeypatch.setenv("AUTO_RESTORE_ON_CORRUPT", "0")
    monkeypatch.setattr(db_integrity, "get_data_dir", lambda: tmp_path)
    report = db_integrity.maybe_auto_restore(str(path))
    assert report["restored"] is False
    assert report["skip_reason"] == "auto_restore_disabled"


def test_maybe_auto_restore_skips_locked_classification(tmp_path, monkeypatch):
    path = tmp_path / "ok.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        db_integrity,
        "probe_sqlite_file",
        lambda _p: {
            "ok": False,
            "classification": "locked",
            "error": "database is locked",
            "checked_at": "now",
        },
    )
    monkeypatch.setattr(db_integrity, "get_data_dir", lambda: tmp_path)
    report = db_integrity.maybe_auto_restore(str(path))
    assert report["restored"] is False
    assert report["skip_reason"] == "classification=locked"


def test_maybe_auto_restore_moves_corrupt_file(tmp_path, monkeypatch):
    live = tmp_path / "golf.db"
    live.write_bytes(b"not a database")
    good = tmp_path / "good.db"
    conn = sqlite3.connect(good)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("AUTO_RESTORE_ON_CORRUPT", "1")
    monkeypatch.setattr(db_integrity, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(db_integrity, "latest_good_backup", lambda: str(good))
    monkeypatch.setattr(db, "DB_PATH", str(live))
    monkeypatch.setattr("src.backup.DB_PATH", str(live))
    db.reset_db_availability()

    sent: list[str] = []
    monkeypatch.setattr(
        "src.ops_alerts.send_ops_alert",
        lambda title, body: sent.append(title),
    )

    report = db_integrity.maybe_auto_restore(str(live))
    assert report["restored"] is True
    assert live.is_file()
    check = sqlite3.connect(f"file:{live}?mode=ro", uri=True)
    try:
        assert check.execute("SELECT name FROM sqlite_master WHERE name='t'").fetchone()
    finally:
        check.close()
    asides = list(tmp_path.glob("golf.db.malformed_*"))
    assert asides
    assert sent
