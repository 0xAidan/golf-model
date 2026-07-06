"""Operator background job API."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from src.db import ensure_initialized, get_conn
from src.ops_jobs import create_job, get_job, update_job

router = APIRouter(tags=["ops-jobs"])


@router.get("/api/ops/jobs/{job_id}")
async def get_ops_job(job_id: str):
    ensure_initialized()
    conn = get_conn()
    try:
        job = get_job(conn, job_id)
    finally:
        conn.close()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job["id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "progress_pct": job.get("progress_pct", 0),
        "message": job.get("message"),
        "result": job.get("result"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "completed_at": job.get("completed_at"),
    }


@router.get("/api/ops/jobs/latest/{job_type}")
async def get_latest_ops_job(job_type: str):
    from src.ops_jobs import latest_job_by_type

    ensure_initialized()
    conn = get_conn()
    try:
        job = latest_job_by_type(conn, job_type)
    finally:
        conn.close()
    if not job:
        return {"job": None}
    return {"job": dict(job)}


def _run_grade_job(job_id: str, event_id: str, year: int, event_name: str | None) -> None:
    from scripts.grade_tournament import grade_tournament

    conn = get_conn()
    try:
        update_job(conn, job_id, progress_pct=10, message="Grading tournament…")
        report = grade_tournament(event_id, year, event_name=event_name)
        status = str(report.get("status", "")).lower()
        grading_report = report.get("grading_report") or {}
        if status == "error" or report.get("error"):
            update_job(
                conn,
                job_id,
                status="error",
                progress_pct=100,
                message="Grading failed",
                result=report,
                error=str(report.get("error") or report.get("message") or "Grading failed"),
            )
        elif status == "partial":
            update_job(
                conn,
                job_id,
                status="partial",
                progress_pct=100,
                message=grading_report.get("message") or "Grading partial",
                result=report,
            )
        else:
            update_job(
                conn,
                job_id,
                status="complete",
                progress_pct=100,
                message="Grading complete",
                result=report,
            )
    except Exception as exc:
        update_job(
            conn,
            job_id,
            status="error",
            progress_pct=100,
            message="Grading failed",
            error=str(exc),
        )
    finally:
        conn.close()


@router.post("/api/ops/jobs/grade")
async def start_grade_job(request: Request):
    """Queue grade tournament as background job; returns immediately."""
    payload = await request.json()
    ensure_initialized()

    from scripts.grade_tournament import find_latest_completed_event

    event_id = payload.get("event_id")
    event_name = payload.get("event_name")
    year = payload.get("year")

    if not event_id:
        info = find_latest_completed_event()
        if info:
            event_id = info["event_id"]
            year = year or info["year"]
            event_name = event_name or info.get("event_name")
        else:
            return JSONResponse(
                {"status": "error", "error": "Could not determine latest event"},
                status_code=422,
            )

    if not year:
        from datetime import datetime as _dt

        year = _dt.now().year

    conn = get_conn()
    try:
        job_id = create_job(
            conn,
            "grade",
            {"event_id": event_id, "year": year, "event_name": event_name},
        )
    finally:
        conn.close()

    asyncio.create_task(
        asyncio.to_thread(_run_grade_job, job_id, str(event_id), int(year), event_name)
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "running",
            "message": "Grading started in background",
        },
    )


def _run_cleanup_job(job_id: str, vacuum: bool, retain_days: int | None) -> None:
    from src.ops_jobs import run_storage_cleanup

    conn = get_conn()
    try:
        update_job(conn, job_id, progress_pct=10, message="Sweeping backup sidecars…")
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


@router.post("/api/ops/jobs/cleanup")
async def start_cleanup_job(request: Request):
    """Queue storage cleanup as a background job; returns immediately."""
    payload: dict[str, Any] = {}
    try:
        body = await request.body()
        if body:
            payload = await request.json()
    except Exception:
        payload = {}

    ensure_initialized()

    vacuum = payload.get("vacuum", True)
    if isinstance(vacuum, str):
        vacuum = vacuum.strip().lower() not in {"0", "false", "no", "off"}
    retain_days = payload.get("retain_days")
    if retain_days is not None:
        retain_days = int(retain_days)

    conn = get_conn()
    try:
        job_id = create_job(
            conn,
            "cleanup",
            {"vacuum": bool(vacuum), "retain_days": retain_days},
        )
    finally:
        conn.close()

    asyncio.create_task(
        asyncio.to_thread(_run_cleanup_job, job_id, bool(vacuum), retain_days)
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "running",
            "message": "Cleanup started in background",
        },
    )
