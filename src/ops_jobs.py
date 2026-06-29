"""Durable operator job queue (grade, refresh) for background UI progress."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_ops_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            progress_pct INTEGER NOT NULL DEFAULT 0,
            message TEXT,
            payload_json TEXT,
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ops_jobs_status ON ops_jobs(status, created_at DESC)"
    )


def create_job(conn: sqlite3.Connection, job_type: str, payload: dict[str, Any] | None = None) -> str:
    ensure_ops_jobs_table(conn)
    job_id = str(uuid.uuid4())
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO ops_jobs (id, job_type, status, progress_pct, message, payload_json, created_at, updated_at)
        VALUES (?, ?, 'running', 0, ?, ?, ?, ?)
        """,
        (
            job_id,
            job_type,
            f"{job_type} started",
            json.dumps(payload or {}),
            now,
            now,
        ),
    )
    conn.commit()
    return job_id


def update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    status: str | None = None,
    progress_pct: int | None = None,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    ensure_ops_jobs_table(conn)
    fields: list[str] = ["updated_at = ?"]
    params: list[Any] = [_now_iso()]
    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if progress_pct is not None:
        fields.append("progress_pct = ?")
        params.append(int(progress_pct))
    if message is not None:
        fields.append("message = ?")
        params.append(message)
    if result is not None:
        fields.append("result_json = ?")
        params.append(json.dumps(result))
    if error is not None:
        fields.append("error = ?")
        params.append(error)
    if status in {"complete", "error", "failed"}:
        fields.append("completed_at = ?")
        params.append(_now_iso())
    params.append(job_id)
    conn.execute(f"UPDATE ops_jobs SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()


def get_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    ensure_ops_jobs_table(conn)
    row = conn.execute("SELECT * FROM ops_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    for key in ("payload_json", "result_json"):
        if data.get(key):
            try:
                data[key.replace("_json", "")] = json.loads(data[key])
            except json.JSONDecodeError:
                data[key.replace("_json", "")] = None
    return data


def latest_job_by_type(conn: sqlite3.Connection, job_type: str) -> dict[str, Any] | None:
    ensure_ops_jobs_table(conn)
    row = conn.execute(
        """
        SELECT * FROM ops_jobs WHERE job_type = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (job_type,),
    ).fetchone()
    if not row:
        return None
    return dict(row)
