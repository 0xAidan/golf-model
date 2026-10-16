"""Authenticated future-generation controls; reads are public and never mutate."""

import hmac
import os

from fastapi import APIRouter, Body, HTTPException, Request

from src.market_generation_policy import (
    PolicyRevisionConflict,
    PolicyUnavailableError,
    PolicyValidationError,
    get_market_generation_policy,
    update_market_generation_policy,
)

router = APIRouter(tags=["market-generation"])


@router.get("/api/market-generation-policy")
async def read_policy():
    return get_market_generation_policy()


@router.patch("/api/market-generation-policy")
async def write_policy(request: Request, payload: dict = Body(...)):
    # Existing middleware protects mutating API requests when configured. This
    # endpoint additionally refuses anonymous writes on an unconfigured server.
    expected = (
        os.environ.get("MARKET_GENERATION_API_KEY", "").strip()
        or os.environ.get("DASHBOARD_API_KEY", "").strip()
    )
    if not expected:
        raise HTTPException(503, detail={"code": "write_auth_unconfigured", "message": "Server write authentication is not configured."})
    provided = request.headers.get("x-api-key", "").strip()
    authorization = request.headers.get("authorization", "")
    if not provided and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, detail={"code": "unauthorized", "message": "Provide the market generation API key."})
    if set(payload) != {"enabled_markets", "expected_revision"}:
        raise HTTPException(422, detail={"code": "invalid_policy", "message": "Provide enabled_markets and expected_revision only."})
    try:
        return update_market_generation_policy(**payload)
    except PolicyValidationError as exc:
        raise HTTPException(422, detail={"code": "invalid_policy", "message": str(exc)}) from exc
    except PolicyRevisionConflict as exc:
        raise HTTPException(409, detail={"code": "revision_conflict", "message": str(exc), "current": exc.current}) from exc
    except PolicyUnavailableError as exc:
        raise HTTPException(503, detail={"code": "policy_unavailable", "message": str(exc)}) from exc
    except OSError as exc:
        raise HTTPException(503, detail={"code": "policy_unavailable", "message": "The market policy could not be saved."}) from exc
