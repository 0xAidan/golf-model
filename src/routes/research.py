"""Research proposal routes — /api/research/*"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/research", tags=["research"])


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
