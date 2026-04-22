"""Research proposal routes — /api/research/*"""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/pair-matchups")
async def list_pair_matchup_predictions(event_id: str | None = None, limit: int = 500):
    """T3 Phase 1 (issue #47) research endpoint — shadow pair predictions only.

    Gated behind the same ``PAIR_MATCHUP_V1`` flag as the logging path. When
    the flag is off this returns 404 so no trace of the feature leaks into
    production API surfaces. When the flag is on it returns the latest shadow
    rows for post-hoc inspection. **Nothing here is wired to the card.**
    """
    from src import config

    if not config.PAIR_MATCHUP_V1:
        raise HTTPException(status_code=404, detail="pair matchup v1 not enabled")

    from src.db import ensure_initialized, get_conn
    from src.models.pair_matchup_v1 import fetch_shadow_predictions

    ensure_initialized()
    conn = get_conn()
    try:
        rows = fetch_shadow_predictions(conn, event_id=event_id, limit=int(limit))
    finally:
        conn.close()
    return {"ok": True, "event_id": event_id, "count": len(rows), "predictions": rows}


@router.get("/proposals")
async def list_research_proposals(status: str | None = None, limit: int = 100):
    """List research proposals for lightweight review."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import list_proposals
    return list_proposals(status=status, limit=limit)


@router.get("/proposals/{proposal_id}")
async def get_research_proposal(proposal_id: int):
    """Return one research proposal."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import get_proposal
    return get_proposal(proposal_id)


@router.post("/run")
async def run_research_cycle_api(request: Request):
    """Run one bounded manual research cycle."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.research_cycle import run_research_cycle

    payload = await request.json()
    kwargs = dict(
        max_candidates=payload.get("max_candidates", 5),
        scope=payload.get("scope", "global"),
        source="manual",
    )
    if payload.get("years") is not None:
        kwargs["years"] = payload["years"]
    return run_research_cycle(**kwargs)


@router.post("/proposals/{proposal_id}/approve")
async def approve_research_proposal(proposal_id: int, request: Request):
    """Approve a proposal without promoting it."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import approve_proposal

    payload = await request.json()
    approve_proposal(
        proposal_id,
        reviewer=payload.get("reviewer", "manual"),
        notes=payload.get("notes"),
    )
    return {"ok": True, "proposal_id": proposal_id, "status": "approved"}


@router.post("/proposals/{proposal_id}/reject")
async def reject_research_proposal(proposal_id: int, request: Request):
    """Reject a proposal without deleting it."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import reject_proposal

    payload = await request.json()
    reject_proposal(
        proposal_id,
        reviewer=payload.get("reviewer", "manual"),
        notes=payload.get("notes"),
    )
    return {"ok": True, "proposal_id": proposal_id, "status": "rejected"}


@router.post("/proposals/{proposal_id}/convert")
async def convert_research_proposal(proposal_id: int):
    """Convert an approved proposal into an experiment."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.proposals import convert_proposal_to_experiment

    experiment_id = convert_proposal_to_experiment(proposal_id)
    return {"ok": True, "proposal_id": proposal_id, "experiment_id": experiment_id}


@router.get("/inplay-shadow")
async def inplay_shadow_predictions(event_id: str):
    """
    Admin-only research endpoint: dump in-play round matchup shadow
    predictions for an event, joined with settled outcomes when available.
    Returns CSV-style JSON (list of rows). SHADOW ONLY — no bets are
    placed off this market in this PR.
    """
    from src.db import ensure_initialized
    ensure_initialized()

    from src.evaluation.inplay import load_predictions_for_event

    rows = load_predictions_for_event(event_id)
    # Outcome join is best-effort: settled round results may or may not
    # be present yet; when absent we return `outcome_p1: null`.
    return {
        "event_id": event_id,
        "count": len(rows),
        "rows": rows,
    }
