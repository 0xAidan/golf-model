"""Operator API for autoresearch Tier 2 hypothesis pipeline.

Endpoints are read-only or require explicit operator action:
- GET  /api/autoresearch/tier2/signals   — current detected signals (from dossiers)
- POST /api/autoresearch/tier2/create-pr — operator-initiated draft PR creation
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("golf.routes.autoresearch_tier2")

router = APIRouter(prefix="/api/autoresearch/tier2", tags=["autoresearch"])

TIER2_DIR = Path("output") / "research" / "tier2"


class CreatePRRequest(BaseModel):
    segment: str


@router.get("/signals")
def list_signals() -> dict:
    """Return stored tier2 hypothesis dossiers (read-only)."""
    if not TIER2_DIR.exists():
        return {"signals": []}
    signals = []
    for path in sorted(TIER2_DIR.glob("hypothesis_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["dossier"] = str(path)
        except (json.JSONDecodeError, OSError):
            continue
        signals.append(payload)
    return {"signals": signals}


@router.post("/detect")
def detect_now() -> dict:
    """Run a detection pass now (writes dossiers; never creates PRs)."""
    from backtester.tier2 import run_detection

    try:
        return run_detection()
    except Exception as exc:
        logger.exception("tier2 detection failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/create-pr")
def create_pr(request: CreatePRRequest) -> dict:
    """EXPLICIT operator action: create a draft PR from a stored dossier."""
    from backtester.tier2 import create_hypothesis_draft_pr

    result = create_hypothesis_draft_pr(request.segment)
    if not result.get("created"):
        raise HTTPException(status_code=400, detail=result.get("error") or "PR creation failed")
    return result
