"""Tests for the model-track registry (engine-scale Wave 1, read-only provenance)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from src import track_registry


def test_compute_config_hash_is_stable_and_order_independent():
    a = track_registry.compute_config_hash("v5", {"b": 2, "a": 1})
    b = track_registry.compute_config_hash("v5", {"a": 1, "b": 2})
    assert a == b
    assert len(a) == 16
    # Different variant or pipeline => different hash.
    assert a != track_registry.compute_config_hash("baseline", {"a": 1, "b": 2})
    assert a != track_registry.compute_config_hash("v5", {"a": 1})


def test_seed_and_list_tracks(tmp_db):
    track_registry.seed_default_tracks()
    listed = track_registry.list_tracks()
    assert "tracks" in listed
    # At least the dashboard track should seed in any environment; lab depends on the
    # champion file being present (it is, in-repo).
    dashboard = listed["tracks"].get("dashboard")
    assert dashboard is not None
    assert dashboard["track"] == "dashboard"
    assert dashboard["config_hash"]
    assert dashboard["strategy_bundle"]["track"] == "dashboard"
    # effective hash should match the seeded active hash (no drift right after seeding).
    assert listed["effective_config_hash"]["dashboard"] == dashboard["config_hash"]


def test_seed_is_idempotent(tmp_db):
    track_registry.seed_default_tracks()
    track_registry.seed_default_tracks()
    from src import db

    conn = db.get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM track_configs WHERE track = 'dashboard' AND status = 'active'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_get_tracks_endpoint(tmp_db):
    import app as app_module

    client = TestClient(app_module.app)
    response = client.get("/api/tracks")
    assert response.status_code == 200
    body = response.json()
    assert "tracks" in body
    assert "effective_config_hash" in body
    assert "history" in body
