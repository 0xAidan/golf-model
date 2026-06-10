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


def test_promote_and_rollback_round_trip(tmp_db):
    """Promotion writes an auditable dashboard row with a parent; rollback restores it."""
    track_registry.seed_default_tracks()
    from src import db

    # Promote with gates bypassed (gates require live graded data we don't have in the fixture).
    result = track_registry.promote_track(from_track="lab", reason="unit test", require_gates=False)
    assert result["ok"] is True
    new_id = result["new_dashboard_id"]
    parent_id = result["rolled_back_to_id_on_revert"]
    assert parent_id is not None

    conn = db.get_conn()
    active = conn.execute(
        "SELECT id, parent_id, activation_reason FROM track_configs WHERE track='dashboard' AND status='active'"
    ).fetchone()
    conn.close()
    assert active["id"] == new_id
    assert active["parent_id"] == parent_id
    assert active["activation_reason"] == "unit test"

    rollback = track_registry.rollback_track("dashboard")
    assert rollback["ok"] is True
    assert rollback["restored_id"] == parent_id

    conn = db.get_conn()
    active2 = conn.execute(
        "SELECT id FROM track_configs WHERE track='dashboard' AND status='active'"
    ).fetchone()
    conn.close()
    assert active2["id"] == parent_id


def test_promote_endpoint_disabled_by_default(tmp_db, monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.config.TRACK_PROMOTION_ENABLED", False)
    client = TestClient(app_module.app)
    resp = client.post("/api/tracks/promote", json={"reason": "x"})
    assert resp.status_code == 403


def test_promotion_readiness_endpoint(tmp_db):
    import app as app_module

    client = TestClient(app_module.app)
    resp = client.get("/api/tracks/promotion-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert "gates" in body
    assert "promotion_enabled" in body
    assert body["passed"] is False  # no live/lab graded data in the fixture
