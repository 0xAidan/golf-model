"""Model registry routes — /api/model-registry/*, /api/baseline/*"""

import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.db import get_conn

router = APIRouter(tags=["model-registry"])


@router.get("/api/model-registry")
async def get_model_registry():
    """Return the current research champion and live weekly model."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.model_registry import get_live_weekly_model_record, get_research_champion_record

    return {
        "live_weekly_model": get_live_weekly_model_record("global"),
        "research_champion": get_research_champion_record("global"),
    }


@router.post("/api/baseline/select")
async def select_best_baseline(request: Request):
    """Select best evaluated proposal by blended score; optionally set research champion."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.weighted_walkforward import compute_blended_score
    from backtester.strategy import StrategyConfig
    from backtester.model_registry import set_research_champion

    payload = await request.json() if request.headers.get("content-type") == "application/json" else {}
    scope = payload.get("scope", "global")
    limit = int(payload.get("limit", 200))
    set_champion = bool(payload.get("set_research_champion", False))

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, name, source, strategy_config_json, summary_metrics_json, guardrail_results_json
        FROM research_proposals
        WHERE scope = ?
          AND status IN ('evaluated', 'approved', 'converted')
          AND summary_metrics_json IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (scope, limit),
    ).fetchall()
    conn.close()

    candidates = []
    for row in rows:
        try:
            strategy = StrategyConfig.from_json(row["strategy_config_json"])
            summary = json.loads(row["summary_metrics_json"] or "{}")
            guardrails = json.loads(row["guardrail_results_json"] or "{}")
            score = compute_blended_score(summary, guardrails)
        except Exception:
            continue
        candidates.append(
            {
                "proposal_id": row["id"],
                "candidate_name": row["name"],
                "strategy_name": strategy.name,
                "strategy_source": row["source"],
                "summary_metrics": summary,
                "guardrail_results": guardrails,
                "blended_score": score,
                "strategy": strategy,
            }
        )

    if not candidates:
        return JSONResponse({"ok": False, "error": "No evaluated proposals found."}, status_code=404)

    candidates.sort(
        key=lambda item: (
            item["blended_score"],
            item["summary_metrics"].get("weighted_roi_pct", -999),
            item["summary_metrics"].get("weighted_clv_avg", -999),
        ),
        reverse=True,
    )
    winner = candidates[0]
    if set_champion:
        set_research_champion(
            winner["strategy"],
            scope=scope,
            source="manual_baseline_selector_ui",
            proposal_id=winner["proposal_id"],
            notes=f"Selected from /api/baseline/select at {datetime.now().isoformat()}",
        )
    winner.pop("strategy", None)
    for item in candidates:
        item.pop("strategy", None)
    return {
        "ok": True,
        "scope": scope,
        "decision": "kept",
        "winner": winner,
        "top_candidates": candidates[:10],
    }


@router.post("/api/model-registry/promote-research-to-live")
async def promote_research_to_live(request: Request):
    """Manually promote the current research champion into the live lane."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.model_registry import (
        HoldoutGateError,
        PromotionGateError,
        evaluate_live_promotion_gates,
        promote_research_champion_to_live,
    )

    payload = await request.json()
    scope = payload.get("scope", "global")
    try:
        promoted = promote_research_champion_to_live(
            scope=scope,
            promoted_by=payload.get("reviewer", "manual"),
            notes=payload.get("notes"),
            enforce_gates=bool(payload.get("enforce_gates", True)),
            enforce_holdout=bool(payload.get("enforce_holdout", False)),
            holdout_artifact_path=payload.get("holdout_artifact_path"),
        )
        return {
            "ok": True,
            "decision": "kept",
            "strategy_source": "research_champion",
            "live_weekly_model": promoted["strategy"].__dict__,
        }
    except HoldoutGateError as exc:
        return JSONResponse(
            {"ok": False, "decision": "failed_holdout", "error": str(exc), "strategy_source": "research_champion"},
            status_code=200,
        )
    except PromotionGateError as exc:
        return JSONResponse(
            {
                "ok": False,
                "decision": "blocked_by_guardrails",
                "blocked_reason": exc.result.reasons,
                "guardrail_metrics": exc.result.metrics,
                "strategy_source": "research_champion",
            },
            status_code=200,
        )
    except Exception as exc:
        gate_state = evaluate_live_promotion_gates(scope)
        return JSONResponse(
            {
                "ok": False,
                "decision": "error",
                "error": str(exc),
                "blocked_reason": gate_state.reasons if not gate_state.passed else [],
                "guardrail_metrics": gate_state.metrics,
                "strategy_source": "research_champion",
            },
            status_code=400,
        )


@router.post("/api/model-registry/promote-proposal-to-live")
async def promote_proposal_to_live(request: Request):
    """Set the given proposal as research champion and promote it to live in one shot."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.model_registry import (
        HoldoutGateError,
        PromotionGateError,
        evaluate_live_promotion_gates,
        promote_research_champion_to_live,
        set_research_champion,
    )
    from backtester.proposals import get_proposal
    from backtester.strategy import StrategyConfig

    payload = await request.json()
    proposal_id = payload.get("proposal_id")
    scope = payload.get("scope", "global")
    if proposal_id is None:
        return JSONResponse({"ok": False, "error": "proposal_id required"}, status_code=400)

    try:
        proposal = get_proposal(proposal_id)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=404)

    strategy = StrategyConfig.from_json(proposal["strategy_config_json"])
    theory_metadata = json.loads(proposal.get("theory_metadata_json") or "{}")

    set_research_champion(
        strategy,
        scope=scope,
        source=payload.get("reviewer", "dashboard"),
        proposal_id=proposal_id,
        theory_metadata=theory_metadata,
        notes=payload.get("notes") or f"Promoted proposal {proposal_id} to live via dashboard",
    )

    try:
        promoted = promote_research_champion_to_live(
            scope=scope,
            promoted_by=payload.get("reviewer", "dashboard"),
            notes=payload.get("notes"),
            enforce_gates=bool(payload.get("enforce_gates", True)),
            enforce_holdout=bool(payload.get("enforce_holdout", False)),
            holdout_artifact_path=payload.get("holdout_artifact_path"),
        )
        return {
            "ok": True,
            "decision": "kept",
            "strategy_source": "proposal",
            "live_weekly_model": promoted["strategy"].__dict__,
        }
    except HoldoutGateError as exc:
        return JSONResponse(
            {"ok": False, "decision": "failed_holdout", "error": str(exc), "strategy_source": "proposal"},
            status_code=200,
        )
    except PromotionGateError as exc:
        return JSONResponse(
            {
                "ok": False,
                "decision": "blocked_by_guardrails",
                "blocked_reason": exc.result.reasons,
                "guardrail_metrics": exc.result.metrics,
                "strategy_source": "proposal",
            },
            status_code=200,
        )
    except Exception as exc:
        gate_state = evaluate_live_promotion_gates(scope)
        return JSONResponse(
            {
                "ok": False,
                "decision": "error",
                "error": str(exc),
                "blocked_reason": gate_state.reasons if not gate_state.passed else [],
                "guardrail_metrics": gate_state.metrics,
                "strategy_source": "proposal",
            },
            status_code=400,
        )


@router.get("/api/model-registry/gates")
async def get_live_promotion_gates(scope: str = "global"):
    """Return charter gate status for live promotion decisions."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.model_registry import evaluate_live_promotion_gates

    result = evaluate_live_promotion_gates(scope)
    return {
        "passed": result.passed,
        "blocked_reason": result.reasons,
        "metrics": result.metrics,
    }


@router.post("/api/model-registry/rollback-live")
async def rollback_live_model(request: Request):
    """Manually roll back the live weekly model to the previous one."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.model_registry import rollback_live_weekly_model

    payload = await request.json()
    rolled_back = rollback_live_weekly_model(
        scope=payload.get("scope", "global"),
        promoted_by=payload.get("reviewer", "manual"),
        notes=payload.get("notes"),
    )
    return {"ok": True, "live_weekly_model": rolled_back["strategy"].__dict__}
