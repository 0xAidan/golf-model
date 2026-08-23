"""Operator API routes for the autoresearch view (PR9)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from src import autoresearch_operator as operator

logger = logging.getLogger("golf.routes.autoresearch_view")

router = APIRouter(prefix="/api/autoresearch", tags=["autoresearch"])


class EffortRequest(BaseModel):
    effort: str


class PromoteRequest(BaseModel):
    config_hash: str
    reason: str
    activated_by: str = "operator"


@router.get("/view/status")
def view_status() -> dict:
    """Cycle status + next-cycle ETA + effort dial (read-only)."""
    return operator.get_cycle_status()


@router.get("/view/ledger")
def view_ledger(limit: int = 100, kind: str | None = None, decision: str | None = None) -> dict:
    """Read-only ledger browser."""
    kinds = [kind] if kind else None
    return operator.browse_ledger(limit=limit, kinds=kinds, decision=decision)


@router.get("/view/promotion-ready")
def view_promotion_ready() -> dict:
    """Staged promotion-ready dossiers awaiting operator review."""
    return {"dossiers": operator.list_promotion_ready()}


@router.post("/view/effort")
def update_effort(payload: EffortRequest) -> dict:
    """Set the orchestrator effort dial (light/standard/max)."""
    result = operator.set_effort(payload.effort)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/view/promote-to-lab")
def promote_to_lab(payload: PromoteRequest = Body(default_factory=PromoteRequest)) -> dict:
    """Human click: swap the LAB track to a staged candidate. Dashboard untouched."""
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required (audit trail).")
    result = operator.promote_candidate_to_lab(
        payload.config_hash.strip(), reason=payload.reason.strip(), activated_by=payload.activated_by
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/view/rollback-lab")
def rollback_lab() -> dict:
    """One action: restore the previous lab config."""
    result = operator.rollback_lab()
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.get("/view/eras")
def view_eras(window_days: int | None = None) -> dict:
    """Algorithm eras: per-config graded ROI/W-L from activation + all-time."""
    return operator.get_algorithm_eras(window_days=window_days)
