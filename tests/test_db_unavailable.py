"""A corrupt SQLite file must not kill the process on import or init."""

from __future__ import annotations

import pytest

import src.db as db


@pytest.fixture(autouse=True)
def _reset_db_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "golf.db"))
    db._DB_INITIALIZED = False
    db.reset_db_availability()
    yield
    db.reset_db_availability()
    db._DB_INITIALIZED = False


def test_ensure_initialized_survives_malformed_file(tmp_path, monkeypatch):
    bad = tmp_path / "golf.db"
    bad.write_bytes(b"this is not a sqlite database")
    monkeypatch.setattr(db, "DB_PATH", str(bad))
    db.ensure_initialized()
    assert db.is_db_unavailable()
    with pytest.raises(db.DatabaseUnavailable):
        db.get_conn()


def test_healthy_db_still_initializes(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "healthy.db"))
    db.ensure_initialized()
    assert db.is_db_unavailable() is False
    conn = db.get_conn()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tournaments'"
        ).fetchone()
        assert tables is not None
    finally:
        conn.close()


def test_reset_clears_unavailable_flag():
    db.mark_db_unavailable("malformed")
    assert db.is_db_unavailable()
    db.reset_db_availability()
    assert db.is_db_unavailable() is False
