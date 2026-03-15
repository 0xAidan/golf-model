"""Shared pytest fixtures for the golf model test suite."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_db():
    """Provide a temporary SQLite database initialized with the full schema.

    Yields the db module with DB_PATH pointed at a temp file.
    Restores original path after the test.
    """
    import src.db as db

    original_path = db.DB_PATH
    original_init = db._DB_INITIALIZED

    tmp = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp
    db._DB_INITIALIZED = False
    db.ensure_initialized()

    yield db

    if os.path.exists(tmp):
        os.unlink(tmp)
    db.DB_PATH = original_path
    db._DB_INITIALIZED = original_init


@pytest.fixture
def sample_tournament(tmp_db):
    """Create a sample tournament and return (db_module, tournament_id)."""
    tid = tmp_db.get_or_create_tournament("Test Tournament", year=2026)
    return tmp_db, tid


@pytest.fixture
def sample_metrics(sample_tournament):
    """Store sample player metrics and return (db_module, tournament_id, player_keys)."""
    db_mod, tid = sample_tournament
    players = [
        ("scottie_scheffler", "Scottie Scheffler"),
        ("rory_mcilroy", "Rory McIlroy"),
        ("xander_schauffele", "Xander Schauffele"),
    ]
    rows = []
    for pk, display in players:
        for metric_name, value in [("sg_total", 1.5), ("sg_ott", 0.5), ("sg_app", 0.6)]:
            rows.append({
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": pk,
                "player_display": display,
                "metric_category": "dg",
                "data_mode": "pre_tournament",
                "round_window": "all",
                "metric_name": metric_name,
                "metric_value": value,
                "metric_text": None,
            })
    db_mod.store_metrics(rows)
    return db_mod, tid, [pk for pk, _ in players]
