"""Composable analytics API for pick ledger."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from src.data_views import ensure_analytics_views
from src.db import ensure_initialized, get_conn

router = APIRouter(tags=["analytics"])


def _outcome_filter_sql(outcome: str | None) -> tuple[str, list[Any]]:
    if not outcome:
        return "", []
    o = outcome.strip().lower()
    if o == "ungraded":
        return " AND po.id IS NULL", []
    if o == "win":
        return " AND po.hit = 1", []
    if o == "loss":
        return " AND po.id IS NOT NULL AND po.hit = 0 AND COALESCE(po.profit, 0) != 0", []
    if o == "push":
        return " AND po.id IS NOT NULL AND po.hit = 0 AND COALESCE(po.profit, 0) = 0", []
    return "", []


@router.get("/api/analytics/picks")
async def list_analytics_picks(
    event_id: str | None = None,
    year: int | None = None,
    season: int | None = None,
    phase: str | None = None,
    lane: str | None = None,
    bet_type: str | None = None,
    ev_min: float | None = None,
    ev_max: float | None = None,
    outcome: str | None = None,
    lifecycle: str | None = None,
    book: str | None = None,
    model_variant: str | None = None,
    include_reconstructed: bool = False,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    ensure_initialized()
    ensure_analytics_views()
    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    if not include_reconstructed:
        clauses.append("pl.lifecycle != 'pit_reconstructed'")
        clauses.append("COALESCE(pl.source_origin, '') != 'pit_reconstructed'")

    if event_id:
        clauses.append("pl.event_id = ?")
        params.append(str(event_id).strip())
    if year is not None:
        clauses.append("COALESCE(pl.year, t.year) = ?")
        params.append(int(year))
    if season is not None:
        clauses.append("COALESCE(pl.year, t.year) = ?")
        params.append(int(season))
    if phase:
        clauses.append("pl.phase = ?")
        params.append(phase.strip().lower())
    if lane:
        clauses.append("pl.lane = ?")
        params.append(lane.strip().lower())
    if bet_type:
        clauses.append("pl.bet_type = ?")
        params.append(bet_type.strip().lower())
    if ev_min is not None:
        clauses.append("pl.ev >= ?")
        params.append(float(ev_min))
    if ev_max is not None:
        clauses.append("pl.ev <= ?")
        params.append(float(ev_max))
    if lifecycle:
        clauses.append("pl.lifecycle = ?")
        params.append(lifecycle.strip().lower())
    if book:
        clauses.append("LOWER(pl.book) = ?")
        params.append(book.strip().lower())
    if model_variant:
        clauses.append("pl.model_variant = ?")
        params.append(model_variant.strip().lower())

    outcome_sql, outcome_params = _outcome_filter_sql(outcome)
    clauses.append(outcome_sql.lstrip(" AND ") if outcome_sql else "1=1")
    params.extend(outcome_params)

    where = " AND ".join(clauses)
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT pl.*, po.hit, po.model_hit, po.profit, po.grading_authority, po.outcome_locked,
               po.entered_at AS graded_at, t.name AS tournament_name, t.date AS tournament_date
        FROM pick_ledger pl
        LEFT JOIN pick_outcomes po ON po.pick_key = pl.pick_key
        LEFT JOIN tournaments t ON t.id = pl.tournament_id
        WHERE {where}
        ORDER BY pl.generated_at DESC, pl.id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, int(limit), int(offset)),
    ).fetchall()
    total = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM pick_ledger pl
        LEFT JOIN pick_outcomes po ON po.pick_key = pl.pick_key
        LEFT JOIN tournaments t ON t.id = pl.tournament_id
        WHERE {where}
        """,
        params,
    ).fetchone()
    conn.close()

    return {
        "total": int(total["c"] if total else 0),
        "limit": limit,
        "offset": offset,
        "picks": [dict(r) for r in rows],
    }


@router.get("/api/analytics/picks/rollup")
async def rollup_analytics_picks(
    group_by: str = Query("event", pattern="^(event|bet_type|book|phase|month|lane)$"),
    season: int | None = None,
    year: int | None = None,
    include_reconstructed: bool = False,
):
    ensure_initialized()
    ensure_analytics_views()
    group_col = {
        "event": "pl.event_id",
        "bet_type": "pl.bet_type",
        "book": "pl.book",
        "phase": "pl.phase",
        "month": "strftime('%Y-%m', COALESCE(pl.generated_at, t.date))",
        "lane": "pl.lane",
    }[group_by]

    clauses = ["1=1"]
    params: list[Any] = []
    if not include_reconstructed:
        clauses.append("pl.lifecycle != 'pit_reconstructed'")
    target_year = season or year
    if target_year is not None:
        clauses.append("COALESCE(pl.year, t.year) = ?")
        params.append(int(target_year))

    where = " AND ".join(clauses)
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT
            {group_col} AS group_key,
            COUNT(*) AS count,
            SUM(CASE WHEN po.hit = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN po.id IS NOT NULL AND po.hit = 0 AND COALESCE(po.profit, 0) != 0 THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN po.id IS NOT NULL AND po.hit = 0 AND COALESCE(po.profit, 0) = 0 THEN 1 ELSE 0 END) AS pushes,
            SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END) AS graded_count,
            ROUND(SUM(COALESCE(po.profit, 0)), 2) AS profit,
            ROUND(
                CASE WHEN SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END) > 0
                THEN 100.0 * SUM(COALESCE(po.profit, 0)) / SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END)
                ELSE 0 END, 2
            ) AS roi_pct
        FROM pick_ledger pl
        LEFT JOIN pick_outcomes po ON po.pick_key = pl.pick_key
        LEFT JOIN tournaments t ON t.id = pl.tournament_id
        WHERE {where}
        GROUP BY group_key
        ORDER BY profit DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return {"group_by": group_by, "rows": [dict(r) for r in rows]}
