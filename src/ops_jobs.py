"""Durable operator job queue (grade, cleanup) for background UI progress."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from src.db import get_conn

_logger = logging.getLogger(__name__)

CLEANUP_AUTO_COOLDOWN_SECONDS = 6 * 60 * 60


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
    if status in {"complete", "partial", "error", "failed"}:
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


def remove_stale_db_recovery_copies(db_path: str) -> list[str]:
    """Remove leftover reclaim/restore temp files when the live DB passes quick_check."""
    if not os.path.isfile(db_path):
        return []

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
            if not row or str(row[0]) != "ok":
                return []
        finally:
            conn.close()
    except sqlite3.Error as exc:
        _logger.warning("refusing stale DB copy cleanup; quick_check failed: %s", exc)
        return []

    removed: list[str] = []
    for suffix in (".pre_reclaim", ".pre_restore", ".vacuum_into"):
        path = db_path + suffix
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError as exc:
            _logger.warning("could not remove stale DB copy %s: %s", path, exc)
    return removed


def _auto_cleanup_enabled() -> bool:
    raw = (os.environ.get("STORAGE_AUTO_CLEANUP") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return not bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _parse_job_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def run_storage_cleanup(
    *,
    vacuum: bool = True,
    retain_days: int | None = None,
) -> dict[str, Any]:
    """Idempotent storage maintenance for operator cleanup jobs."""
    from src import db
    from src.backup import sweep_orphan_sidecars
    from src.pick_ledger import prune_generated_pick_ledger
    from src.storage_janitor import sweep_disposable_storage

    report: dict[str, Any] = {
        "ok": True,
        "steps": {},
    }

    janitor = sweep_disposable_storage(db_path=db.DB_PATH)
    report["steps"]["janitor"] = janitor
    if not janitor.get("ok", True):
        report["ok"] = False

    sidecars_removed = sweep_orphan_sidecars()
    report["steps"]["sidecar_sweep"] = {"removed": sidecars_removed, "count": len(sidecars_removed)}

    generated_prune = prune_generated_pick_ledger()
    report["steps"]["generated_ledger_prune"] = generated_prune

    stale_removed = remove_stale_db_recovery_copies(db.DB_PATH)
    report["steps"]["stale_db_copies"] = {"removed": stale_removed, "count": len(stale_removed)}

    conn = db.get_conn()
    try:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
            wal_ok = True
            wal_error = None
        except sqlite3.OperationalError as exc:
            wal_ok = False
            wal_error = str(exc)
    finally:
        conn.close()
    report["steps"]["wal_checkpoint"] = {"ok": wal_ok, "error": wal_error}

    from scripts.run_retention_cycle import run_retention_cycle

    retention = run_retention_cycle(
        retain_days=retain_days,
        dry_run=False,
        vacuum=False,
    )
    report["steps"]["retention"] = retention
    if not retention.get("ok", False) and not retention.get("skipped"):
        report["ok"] = False

    if vacuum:
        reclaim = db.reclaim_database_disk()
        report["steps"]["reclaim"] = reclaim
        if reclaim.get("skipped"):
            report["steps"]["incremental_reclaim"] = db.incremental_reclaim()
        elif not reclaim.get("ok", False):
            report["ok"] = False
    else:
        report["steps"]["reclaim"] = {"skipped": True, "reason": "vacuum disabled"}
        report["steps"]["incremental_reclaim"] = db.incremental_reclaim()

    return report


def execute_cleanup_job(job_id: str, vacuum: bool, retain_days: int | None) -> None:
    """Run a cleanup job and persist progress on ``ops_jobs``."""
    conn = get_conn()
    try:
        update_job(conn, job_id, progress_pct=10, message="Sweeping leftover temp copies…")
        update_job(conn, job_id, progress_pct=35, message="Running retention cycle…")
        report = run_storage_cleanup(vacuum=vacuum, retain_days=retain_days)
        if report.get("ok"):
            update_job(
                conn,
                job_id,
                status="complete",
                progress_pct=100,
                message="Cleanup complete",
                result=report,
            )
        else:
            update_job(
                conn,
                job_id,
                status="error",
                progress_pct=100,
                message="Cleanup finished with errors",
                result=report,
                error="One or more cleanup steps failed; see result.steps",
            )
    except Exception as exc:
        update_job(
            conn,
            job_id,
            status="error",
            progress_pct=100,
            message="Cleanup failed",
            error=str(exc),
        )
    finally:
        conn.close()


def maybe_enqueue_storage_cleanup(*, reason: str, vacuum: bool = True) -> dict[str, Any]:
    """Start one cleanup job when storage is red, with a 6-hour cooldown."""
    if not _auto_cleanup_enabled():
        return {"started": False, "reason": "disabled"}

    conn = get_conn()
    try:
        latest = latest_job_by_type(conn, "cleanup")
        if latest:
            status = str(latest.get("status") or "").lower()
            if status in {"running", "pending"}:
                return {
                    "started": False,
                    "reason": "already_running",
                    "job_id": latest.get("id"),
                }
            stamped = _parse_job_timestamp(latest.get("created_at") or latest.get("updated_at"))
            if stamped is not None:
                if stamped.tzinfo is None:
                    stamped = stamped.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - stamped.astimezone(timezone.utc)).total_seconds()
                if age < CLEANUP_AUTO_COOLDOWN_SECONDS:
                    return {
                        "started": False,
                        "reason": "cooldown",
                        "job_id": latest.get("id"),
                        "age_seconds": int(age),
                    }
        job_id = create_job(
            conn,
            "cleanup",
            {"vacuum": bool(vacuum), "auto": True, "trigger": reason},
        )
    finally:
        conn.close()

    thread = threading.Thread(
        target=execute_cleanup_job,
        args=(job_id, bool(vacuum), None),
        name=f"storage-cleanup-{job_id}",
        daemon=True,
    )
    thread.start()
    _logger.info("auto storage cleanup started job_id=%s trigger=%s", job_id, reason)
    return {"started": True, "job_id": job_id, "trigger": reason}


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
