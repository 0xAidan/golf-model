"""Read-only, lightweight API projections for the operator UI."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from backtester import dashboard_runtime
from src import db, runtime_paths
from src.autoresearch_settings import get_settings
from src.live_refresh_policy import resolve_cadence
from src.operator_contract import SCHEMA_VERSION
from src.operator_read_model import build_board, build_bootstrap

router = APIRouter(tags=["operator"])


def _snapshot_stale_after_seconds() -> int:
    settings = get_settings().get("live_refresh") or {}
    cadence = resolve_cadence(settings)
    return max(900, int(cadence.recompute_seconds) + 120)


def _runtime_state() -> tuple[list[str], bool]:
    status = dashboard_runtime.get_live_refresh_status() or {}
    split = runtime_paths.detect_split_brain()
    reasons = list(status.get("split_brain_reasons") or []) + list(split.get("reasons") or [])
    if status.get("split_brain_suspected") and not reasons:
        reasons.append("live_refresh_status_reported_split_brain")
    refresh_state = str(
        status.get("refresh_state") or (status.get("progress") or {}).get("refresh_state") or ""
    ).lower()
    return list(dict.fromkeys(reasons)), refresh_state in {"queued", "running", "refreshing"}


def _etag(
    *,
    track: str,
    mode: str,
    event_id: str | None,
    snapshot_id: str | None,
) -> str:
    identity = "|".join((SCHEMA_VERSION, track, mode, event_id or "", snapshot_id or ""))
    return f'"{hashlib.sha256(identity.encode("utf-8")).hexdigest()}"'


def _conditional_json(request: Request, payload: dict[str, Any], *, etag: str) -> Response:
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(payload, headers={"ETag": etag})


def _past_projection_snapshot(track: str, event_id: str) -> dict[str, Any] | None:
    db.ensure_initialized()
    source = "dashboard" if track == "champion" else "lab"
    section = db.build_completed_snapshot_section(event_id, source=source)
    if not section:
        return None
    return {
        "snapshot_id": section.get("source_snapshot_id") or section.get("snapshot_id"),
        "generated_at": section.get("generated_at"),
        "completed": section,
    }


@router.get("/api/operator/bootstrap")
async def get_operator_bootstrap(request: Request):
    """Return small, fail-closed track availability metadata; never runs a model."""
    snapshot = dashboard_runtime.read_snapshot()
    split_brain_reasons, refreshing = _runtime_state()
    payload = build_bootstrap(
        snapshot,
        stale_after_seconds=_snapshot_stale_after_seconds(),
        split_brain_reasons=split_brain_reasons,
        refreshing=refreshing,
    )
    return _conditional_json(
        request,
        payload,
        etag=_etag(
            track="bootstrap",
            mode="bootstrap",
            event_id=None,
            snapshot_id=payload["source"].get("snapshot_id"),
        ),
    )


@router.get("/api/operator/board")
async def get_operator_board(
    request: Request,
    track: str = Query(..., pattern="^(champion|challenger)$"),
    mode: str = Query(..., pattern="^(live|upcoming|past)$"),
    event_id: str | None = Query(default=None, min_length=1),
):
    """Return exactly one normalized track board; Challenger never reads Champion rows."""
    if mode == "past" and not event_id:
        return JSONResponse(
            {
                "schema_version": SCHEMA_VERSION,
                "state": "error",
                "reason": {
                    "code": "event_id_required",
                    "message": "event_id is required when requesting a past board.",
                },
            },
            status_code=400,
        )

    if mode == "past":
        snapshot = _past_projection_snapshot(track, event_id or "")
        split_brain_reasons: list[str] = []
        refreshing = False
    else:
        snapshot = dashboard_runtime.read_snapshot()
        split_brain_reasons, refreshing = _runtime_state()

    payload = build_board(
        snapshot,
        track=track,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        event_id=event_id,
        stale_after_seconds=_snapshot_stale_after_seconds(),
        split_brain_reasons=split_brain_reasons,
        refreshing=refreshing,
    )
    return _conditional_json(
        request,
        payload,
        etag=_etag(
            track=track,
            mode=mode,
            event_id=event_id,
            snapshot_id=payload["source"].get("snapshot_id"),
        ),
    )
