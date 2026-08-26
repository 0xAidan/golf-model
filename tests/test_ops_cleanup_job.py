"""Storage cleanup ops job."""

from __future__ import annotations

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.ops_jobs import (
    create_job,
    get_job,
    maybe_enqueue_storage_cleanup,
    remove_stale_db_recovery_copies,
    run_storage_cleanup,
    update_job,
)


def test_remove_stale_db_recovery_copies_when_db_ok(tmp_db, tmp_path) -> None:
    stale = tmp_db.DB_PATH + ".pre_reclaim"
    with open(stale, "wb") as fh:
        fh.write(b"leftover")

    removed = remove_stale_db_recovery_copies(tmp_db.DB_PATH)

    assert stale in removed
    assert os.path.exists(stale) is False


def test_remove_stale_db_recovery_copies_skips_when_db_bad(tmp_db) -> None:
    stale = tmp_db.DB_PATH + ".pre_restore"
    with open(stale, "wb") as fh:
        fh.write(b"leftover")
    with open(tmp_db.DB_PATH, "wb") as fh:
        fh.write(b"not sqlite")

    removed = remove_stale_db_recovery_copies(tmp_db.DB_PATH)

    assert removed == []
    assert os.path.exists(stale) is True


def test_run_storage_cleanup_idempotent(tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("SNAPSHOT_HISTORY_RETAIN_DAYS", "365")
    monkeypatch.setattr(
        "src.runtime_paths.get_runtime_identity",
        lambda: {"db_path": tmp_db.DB_PATH},
    )
    monkeypatch.setattr(
        "src.backup.sweep_orphan_sidecars",
        lambda: [],
    )

    first = run_storage_cleanup(vacuum=False)
    second = run_storage_cleanup(vacuum=False)

    assert first["ok"] is True
    assert second["ok"] is True
    assert "janitor" in first["steps"]
    assert first["steps"]["janitor"]["ok"] is True
    assert "sidecar_sweep" in first["steps"]
    assert "generated_ledger_prune" in first["steps"]
    assert first["steps"]["generated_ledger_prune"]["ok"] is True
    assert "retention" in first["steps"]
    assert first["steps"]["reclaim"]["skipped"] is True
    assert "incremental_reclaim" in first["steps"]


def test_cleanup_job_lifecycle(tmp_db) -> None:
    import src.db as db

    conn = db.get_conn()
    job_id = create_job(conn, "cleanup", {"vacuum": False})
    conn.close()

    report = {
        "ok": True,
        "steps": {
            "sidecar_sweep": {"removed": [], "count": 0},
            "retention": {"ok": True, "skipped": True},
            "reclaim": {"skipped": True},
        },
    }

    conn = db.get_conn()
    from src.ops_jobs import update_job

    update_job(conn, job_id, status="complete", progress_pct=100, result=report)
    job = get_job(conn, job_id)
    conn.close()

    assert job is not None
    assert job["status"] == "complete"
    assert job.get("result", {}).get("ok") is True


def test_post_cleanup_job_returns_202(monkeypatch, tmp_db) -> None:
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)

    class _NoopTask:
        def cancel(self) -> None:
            return None

    monkeypatch.setattr("asyncio.create_task", lambda _coro: _NoopTask())

    client = TestClient(app_module.app)
    response = client.post("/api/ops/jobs/cleanup", json={"vacuum": False})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    assert "job_id" in body


def test_maybe_enqueue_storage_cleanup_respects_cooldown(tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_AUTO_CLEANUP", "1")
    started: list[str] = []
    monkeypatch.setattr(
        "src.ops_jobs.execute_cleanup_job",
        lambda *args, **kwargs: started.append("ran"),
    )

    conn = tmp_db.get_conn()
    job_id = create_job(conn, "cleanup", {"vacuum": False})
    update_job(conn, job_id, status="complete", progress_pct=100, message="done")
    conn.close()

    first = maybe_enqueue_storage_cleanup(reason="next backup cannot fit")
    assert first["started"] is False
    assert first["reason"] == "cooldown"
    assert started == []


def test_maybe_enqueue_storage_cleanup_starts_when_enabled(tmp_db, monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_AUTO_CLEANUP", "1")
    monkeypatch.setattr("src.ops_jobs.execute_cleanup_job", lambda *args, **kwargs: None)

    result = maybe_enqueue_storage_cleanup(reason="latest backup older than 36h")
    assert result["started"] is True
    assert result["job_id"]

    conn = tmp_db.get_conn()
    job = get_job(conn, result["job_id"])
    conn.close()
    assert job is not None
    assert job["job_type"] == "cleanup"
