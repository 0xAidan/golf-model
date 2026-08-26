"""Tests for persisted health reports used by responsive API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def test_cached_health_round_trip_labels_expired_entry_stale(monkeypatch) -> None:
    from src import cached_health

    stored: dict[str, object] = {}
    monkeypatch.setattr(cached_health, "set_app_metadata", lambda key, value: stored.__setitem__(key, value))
    monkeypatch.setattr(cached_health, "get_app_metadata", lambda key: stored.get(key))

    generated_at = (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat()
    cached_health.write_cached_data_health({"status": "green"}, generated_at=generated_at)

    entry = cached_health.read_cached_data_health(ttl_seconds=60)

    assert entry is not None
    assert entry["report"] == {"status": "green"}
    assert entry["generated_at"] == generated_at
    assert entry["stale"] is True
    assert entry["ttl_seconds"] == 60


def test_ops_health_uses_cached_grading_without_reconciliation(monkeypatch) -> None:
    import app as app_module
    from src import cached_health

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        cached_health,
        "read_cached_ops_grading_health",
        lambda: {
            "report": {
                "grading": {"status": "ok"},
                "tracks": {"active": {}},
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "ttl_seconds": 900,
        },
    )
    monkeypatch.setattr(
        "src.grading_reconciliation.reconcile_grading",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("GET must not reconcile")),
    )

    client = TestClient(app_module.app)
    response = client.get("/api/ops/health")

    assert response.status_code == 200
    assert response.json()["grading"]["status"] == "ok"
    assert response.json()["grading_cache"]["stale"] is False


def test_data_health_uses_cached_report_without_rebuild(monkeypatch) -> None:
    import app as app_module
    from src import cached_health

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        cached_health,
        "read_cached_data_health",
        lambda year: {
            "report": {"status": "green", "retention_classifications": {}},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "ttl_seconds": 21600,
        },
    )
    monkeypatch.setattr(
        "src.data_health.build_data_health_report",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("GET must not rebuild")),
    )
    monkeypatch.setattr(
        "src.data_views.ensure_analytics_views",
        lambda: (_ for _ in ()).throw(AssertionError("GET must not build views")),
    )

    client = TestClient(app_module.app)
    response = client.get("/api/data-health?year=2026")

    assert response.status_code == 200
    assert response.json()["status"] == "green"
    assert response.json()["stale"] is False


def test_refresh_data_health_enqueues_cleanup_when_red(monkeypatch) -> None:
    from src import cached_health

    stored: dict[str, object] = {}
    monkeypatch.setattr(cached_health, "set_app_metadata", lambda key, value: stored.__setitem__(key, value))
    monkeypatch.setattr(cached_health, "get_app_metadata", lambda key: stored.get(key))
    monkeypatch.setattr("src.data_views.ensure_analytics_views", lambda: None)
    monkeypatch.setattr(
        "src.data_health.build_data_health_report",
        lambda **kwargs: {
            "status": "red",
            "storage_red_reasons": ["next backup cannot fit"],
        },
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        cached_health,
        "maybe_enqueue_storage_cleanup",
        lambda **kwargs: enqueued.append(kwargs["reason"]) or {"started": True},
    )

    report = cached_health.refresh_data_health_cache(2026)

    assert report["status"] == "red"
    assert enqueued == ["next backup cannot fit"]
    assert report["auto_cleanup"] == {"started": True}
