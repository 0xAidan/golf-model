"""Composable analytics API for pick ledger."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from src.data_views import ensure_analytics_views
from src.db import ensure_initialized, get_conn

router = APIRouter(tags=["analytics"])

PICKS_FROM = """
FROM pick_ledger pl
LEFT JOIN pick_outcomes po ON po.pick_key = pl.pick_key
LEFT JOIN tournaments t ON t.id = pl.tournament_id
LEFT JOIN picks p ON p.tournament_id = pl.tournament_id
  AND p.player_key = pl.player_key
  AND LOWER(COALESCE(p.bet_type, '')) = LOWER(COALESCE(pl.bet_type, ''))
"""


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


def _build_picks_where(
    *,
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
    player: str | None = None,
    confidence: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_reconstructed: bool = False,
) -> tuple[str, list[Any]]:
    clauses: list[str] = ["1=1"]
    params: list[Any] = []

    if not include_reconstructed:
        clauses.append("pl.lifecycle != 'pit_reconstructed'")
        clauses.append("COALESCE(pl.source_origin, '') != 'pit_reconstructed'")

    if event_id:
        clauses.append("pl.event_id = ?")
        params.append(str(event_id).strip())
    target_year = season if season is not None else year
    if target_year is not None:
        clauses.append("COALESCE(pl.year, t.year) = ?")
        params.append(int(target_year))
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
    if player:
        clauses.append("(pl.player_key = ? OR LOWER(pl.player_display) LIKE ?)")
        key = player.strip().lower()
        params.extend([key, f"%{key}%"])
    if confidence:
        clauses.append("LOWER(COALESCE(p.confidence, '')) = ?")
        params.append(confidence.strip().lower())
    if date_from:
        clauses.append("pl.generated_at >= ?")
        params.append(date_from.strip())
    if date_to:
        clauses.append("pl.generated_at <= ?")
        params.append(date_to.strip())

    outcome_sql, outcome_params = _outcome_filter_sql(outcome)
    if outcome_sql:
        clauses.append(outcome_sql.lstrip(" AND "))
    params.extend(outcome_params)

    return " AND ".join(clauses), params


@router.get("/api/analytics/summary")
async def analytics_summary(
    event_id: str | None = None,
    year: int | None = None,
    season: int | None = None,
    phase: str | None = None,
    lane: str | None = None,
    bet_type: str | None = None,
    ev_min: float | None = None,
    ev_max: float | None = None,
    outcome: str | None = None,
    book: str | None = None,
    player: str | None = None,
    confidence: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_reconstructed: bool = False,
):
    ensure_initialized()
    ensure_analytics_views()
    where, params = _build_picks_where(
        event_id=event_id,
        year=year,
        season=season,
        phase=phase,
        lane=lane,
        bet_type=bet_type,
        ev_min=ev_min,
        ev_max=ev_max,
        outcome=outcome,
        book=book,
        player=player,
        confidence=confidence,
        date_from=date_from,
        date_to=date_to,
        include_reconstructed=include_reconstructed,
    )
    conn = get_conn()
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS pick_count,
            SUM(CASE WHEN po.hit = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN po.id IS NOT NULL AND po.hit = 0 AND COALESCE(po.profit, 0) != 0 THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN po.id IS NOT NULL AND po.hit = 0 AND COALESCE(po.profit, 0) = 0 THEN 1 ELSE 0 END) AS pushes,
            SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END) AS graded_count,
            ROUND(SUM(COALESCE(po.profit, 0)), 2) AS profit_units,
            ROUND(
                CASE WHEN SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END) > 0
                THEN 100.0 * SUM(CASE WHEN po.hit = 1 THEN 1 ELSE 0 END)
                     / SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END)
                ELSE 0 END, 1
            ) AS win_rate_pct,
            ROUND(
                CASE WHEN SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END) > 0
                THEN 100.0 * SUM(COALESCE(po.profit, 0)) / SUM(CASE WHEN po.id IS NOT NULL THEN 1 ELSE 0 END)
                ELSE 0 END, 2
            ) AS roi_pct
        {PICKS_FROM}
        WHERE {where}
        """,
        params,
    ).fetchone()
    conn.close()
    data = dict(row) if row else {}
    return {
        "pick_count": int(data.get("pick_count") or 0),
        "wins": int(data.get("wins") or 0),
        "losses": int(data.get("losses") or 0),
        "pushes": int(data.get("pushes") or 0),
        "graded_count": int(data.get("graded_count") or 0),
        "profit_units": float(data.get("profit_units") or 0),
        "win_rate_pct": float(data.get("win_rate_pct") or 0),
        "roi_pct": float(data.get("roi_pct") or 0),
    }


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
    player: str | None = None,
    confidence: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    include_reconstructed: bool = False,
    format: str = Query("json", pattern="^(json|csv)$"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    ensure_initialized()
    ensure_analytics_views()
    where, params = _build_picks_where(
        event_id=event_id,
        year=year,
        season=season,
        phase=phase,
        lane=lane,
        bet_type=bet_type,
        ev_min=ev_min,
        ev_max=ev_max,
        outcome=outcome,
        lifecycle=lifecycle,
        book=book,
        model_variant=model_variant,
        player=player,
        confidence=confidence,
        date_from=from_date,
        date_to=to_date,
        include_reconstructed=include_reconstructed,
    )
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT pl.*, po.hit, po.model_hit, po.profit, po.grading_authority, po.outcome_locked,
               po.entered_at AS graded_at, t.name AS tournament_name, t.date AS tournament_date,
               p.confidence AS pick_confidence
        {PICKS_FROM}
        WHERE {where}
        ORDER BY pl.generated_at DESC, pl.id DESC
        LIMIT ? OFFSET ?
        """,
        (*params, int(limit), int(offset)),
    ).fetchall()
    picks = [dict(r) for r in rows]

    if format == "csv":
        conn.close()
        buf = io.StringIO()
        if picks:
            writer = csv.DictWriter(buf, fieldnames=list(picks[0].keys()))
            writer.writeheader()
            writer.writerows(picks)
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    total = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        {PICKS_FROM}
        WHERE {where}
        """,
        params,
    ).fetchone()
    conn.close()

    return {
        "total": int(total["c"] if total else 0),
        "limit": limit,
        "offset": offset,
        "picks": picks,
    }


@router.get("/api/analytics/picks/rollup")
async def rollup_analytics_picks(
    group_by: str = Query("event", pattern="^(event|bet_type|book|phase|month|lane|player)$"),
    season: int | None = None,
    year: int | None = None,
    lane: str | None = None,
    book: str | None = None,
    bet_type: str | None = None,
    ev_min: float | None = None,
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
        "player": "pl.player_display",
    }[group_by]

    where, params = _build_picks_where(
        season=season,
        year=year,
        lane=lane,
        book=book,
        bet_type=bet_type,
        ev_min=ev_min,
        include_reconstructed=include_reconstructed,
    )
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
        {PICKS_FROM}
        WHERE {where}
        GROUP BY group_key
        ORDER BY profit DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return {"group_by": group_by, "rows": [dict(r) for r in rows]}
