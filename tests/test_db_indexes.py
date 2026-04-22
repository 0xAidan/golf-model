"""Tests for Q4: composite indexes on hot-path query columns.

Validates that init_db creates the three composite indexes expected by
hot-path queries, and that the idempotent migration helper produces the
same indexes on a pre-existing DB that is missing them.
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.db as db


EXPECTED_INDEXES = {
    "idx_rounds_player_event": ("rounds", ["player_key", "event_completed"]),
    "idx_metrics_tourn_player_cat": (
        "metrics",
        ["tournament_id", "player_key", "metric_category"],
    ),
    "idx_historical_odds_event_book_ts": (
        "historical_odds",
        ["event_id", "book", "year"],
    ),
}


def _fresh_db_path():
    return tempfile.mktemp(suffix=".db")


def _index_columns(conn: sqlite3.Connection, index_name: str):
    rows = conn.execute(f"PRAGMA index_info('{index_name}')").fetchall()
    # PRAGMA index_info returns rows ordered by seqno; each row: (seqno, cid, name)
    return [row[2] for row in sorted(rows, key=lambda r: r[0])]


def _with_init_db(path):
    original_path = db.DB_PATH
    db.DB_PATH = path
    db._DB_INITIALIZED = False
    try:
        db.init_db()
    finally:
        db.DB_PATH = original_path
        db._DB_INITIALIZED = False


def test_hot_path_indexes_created_on_fresh_db():
    path = _fresh_db_path()
    try:
        _with_init_db(path)
        conn = sqlite3.connect(path)
        try:
            for name, (table, expected_cols) in EXPECTED_INDEXES.items():
                row = conn.execute(
                    "SELECT tbl_name FROM sqlite_master "
                    "WHERE type='index' AND name=?",
                    (name,),
                ).fetchone()
                assert row is not None, f"missing index {name}"
                assert row[0] == table, f"{name} on wrong table: {row[0]}"
                cols = _index_columns(conn, name)
                assert cols == expected_cols, (
                    f"{name} columns mismatch: {cols} != {expected_cols}"
                )
        finally:
            conn.close()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_ensure_hot_path_indexes_is_idempotent_on_existing_db():
    """Simulate an older DB missing the Q4 indexes and verify the migration
    helper adds them without touching data and can run repeatedly."""
    path = _fresh_db_path()
    try:
        _with_init_db(path)
        conn = sqlite3.connect(path)
        try:
            for name in EXPECTED_INDEXES:
                conn.execute(f"DROP INDEX IF EXISTS {name}")
            conn.commit()
            for name in EXPECTED_INDEXES:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                    (name,),
                ).fetchone()
                assert row is None, f"precondition: {name} should be dropped"

            db._ensure_hot_path_indexes(conn)
            db._ensure_hot_path_indexes(conn)

            for name, (table, expected_cols) in EXPECTED_INDEXES.items():
                row = conn.execute(
                    "SELECT tbl_name FROM sqlite_master "
                    "WHERE type='index' AND name=?",
                    (name,),
                ).fetchone()
                assert row is not None, f"{name} not recreated"
                assert row[0] == table
                assert _index_columns(conn, name) == expected_cols
        finally:
            conn.close()
    finally:
        if os.path.exists(path):
            os.unlink(path)
