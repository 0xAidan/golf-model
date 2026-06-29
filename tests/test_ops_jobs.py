"""Ops background jobs."""

from __future__ import annotations

from src.db import get_conn
from src.ops_jobs import create_job, get_job, update_job


def test_ops_job_lifecycle(tmp_db):
    conn = get_conn()
    job_id = create_job(conn, "grade", {"event_id": "1"})
    update_job(conn, job_id, progress_pct=50, message="halfway")
    update_job(conn, job_id, status="complete", progress_pct=100, result={"status": "ok"})
    job = get_job(conn, job_id)
    conn.close()
    assert job is not None
    assert job["status"] == "complete"
    assert job["progress_pct"] == 100
    assert job.get("result", {}).get("status") == "ok"
