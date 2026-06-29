"""Season-wide grading API with Dashboard vs Lab lane comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from src import db
from src.db import ensure_initialized, get_conn
from src.grading_record import (
    build_lane_comparison,
    build_record_summary,
    dedupe_record_picks,
    format_graded_pick_rows,
    pick_lane_sql,
)
from src.official_pick_record import dedupe_inventory_rows, filter_positive_ev

router = APIRouter(tags=["grading"])

TRACK_RECORD_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "data" / "trackRecord.json"


def _load_track_record_events() -> list[dict]:
    if not TRACK_RECORD_PATH.is_file():
        return []
    with open(TRACK_RECORD_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    return list(data.get("events") or [])


def _resolve_event_id(conn, event_name: str, year: int) -> str | None:
    needle = event_name.strip().lower()
    rows = conn.execute(
        """
        SELECT DISTINCT event_id, event_name FROM rounds
        WHERE year = ? AND event_id IS NOT NULL AND TRIM(event_id) != ''
          AND LOWER(event_name) LIKE ?
        """,
        (year, f"%{needle}%"),
    ).fetchall()
    for row in rows:
        if str(row["event_name"] or "").strip().lower() == needle:
            return str(row["event_id"])
    if len(rows) == 1:
        return str(rows[0]["event_id"])
    for row in rows:
        if needle in str(row["event_name"] or "").strip().lower():
            return str(row["event_id"])
    return None


def _discover_season_events(conn, year: int, *, tour: str | None = "pga") -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    tour_norm = (tour or "pga").strip().lower()

    if tour_norm == "all":
        schedule_rows = conn.execute(
            """
            SELECT event_id, event_name, MIN(event_completed) AS event_date
            FROM rounds
            WHERE year = ?
              AND event_id IS NOT NULL AND TRIM(event_id) != ''
            GROUP BY event_id, event_name
            ORDER BY event_date ASC, event_name ASC
            """,
            (year,),
        ).fetchall()
    else:
        schedule_rows = conn.execute(
            """
            SELECT event_id, event_name, MIN(event_completed) AS event_date
            FROM rounds
            WHERE year = ?
              AND event_id IS NOT NULL AND TRIM(event_id) != ''
              AND LOWER(COALESCE(tour, 'pga')) = ?
            GROUP BY event_id, event_name
            ORDER BY event_date ASC, event_name ASC
            """,
            (year, tour_norm),
        ).fetchall()
    for row in schedule_rows:
        eid = str(row["event_id"])
        events[eid] = {
            "event_id": eid,
            "name": row["event_name"] or f"Event {eid}",
            "year": year,
            "event_date": row["event_date"],
            "inventory_count": 0,
            "positive_ev_inventory": 0,
            "authority_tier": "no_data",
        }

    ledger_rows = conn.execute(
        """
        SELECT
            pl.event_id,
            MAX(pl.event_name) AS name,
            MAX(COALESCE(pl.year, t.year)) AS year,
            MAX(t.course) AS course,
            MAX(t.id) AS tournament_id,
            COUNT(*) AS inventory_count,
            SUM(CASE WHEN pl.is_value = 1 THEN 1 ELSE 0 END) AS positive_ev_count
        FROM pick_ledger pl
        LEFT JOIN tournaments t ON t.id = pl.tournament_id
        WHERE COALESCE(pl.year, t.year) = ?
          AND pl.event_id IS NOT NULL AND TRIM(pl.event_id) != ''
        GROUP BY pl.event_id
        """,
        (year,),
    ).fetchall()
    for row in ledger_rows:
        eid = str(row["event_id"])
        existing = events.get(eid, {})
        events[eid] = {
            **existing,
            "event_id": eid,
            "name": row["name"] or existing.get("name") or f"Event {eid}",
            "year": int(row["year"] or year),
            "course": row["course"],
            "tournament_id": row["tournament_id"],
            "inventory_count": int(row["inventory_count"] or 0),
            "positive_ev_inventory": int(row["positive_ev_count"] or 0),
            "authority_tier": "inventory",
        }

    tournament_rows = conn.execute(
        """
        SELECT t.id, t.name, t.course, t.year, t.event_id
        FROM tournaments t
        WHERE t.year = ? AND t.event_id IS NOT NULL AND TRIM(t.event_id) != ''
        """,
        (year,),
    ).fetchall()
    for row in tournament_rows:
        eid = str(row["event_id"])
        existing = events.get(eid, {})
        events[eid] = {
            **existing,
            "event_id": eid,
            "name": existing.get("name") or row["name"],
            "year": int(row["year"] or year),
            "course": existing.get("course") or row["course"],
            "tournament_id": existing.get("tournament_id") or row["id"],
            "inventory_count": int(existing.get("inventory_count") or 0),
            "positive_ev_inventory": int(existing.get("positive_ev_inventory") or 0),
            "authority_tier": existing.get("authority_tier") or "graded",
        }

    for static_event in _load_track_record_events():
        name = str(static_event.get("name") or "")
        if not name:
            continue
        eid = _resolve_event_id(conn, name, year)
        if not eid:
            continue
        record = static_event.get("record") or {}
        picks = static_event.get("picks") or []
        existing = events.get(eid, {})
        authority = "locked" if picks else "rollup_only"
        if existing.get("authority_tier") == "locked":
            authority = "locked"
        elif existing.get("authority_tier") == "graded" and picks:
            authority = "locked"
        elif not picks and not existing:
            authority = "rollup_only"
        elif existing:
            authority = existing.get("authority_tier") or authority

        events[eid] = {
            **existing,
            "event_id": eid,
            "name": name,
            "year": year,
            "course": static_event.get("course") or existing.get("course"),
            "tournament_id": existing.get("tournament_id"),
            "inventory_count": int(existing.get("inventory_count") or 0),
            "positive_ev_inventory": int(existing.get("positive_ev_inventory") or 0),
            "authority_tier": authority,
            "picks_detail_missing": len(picks) == 0,
            "rollup_record": {
                "wins": int(record.get("wins") or 0),
                "losses": int(record.get("losses") or 0),
                "pushes": int(record.get("pushes") or 0),
                "profit": float(static_event.get("profit_units") or 0),
            } if not picks else None,
        }

    return events


def _past_replay_positive_count(event_id: str, lane: str = "dashboard") -> int:
    rows = db.get_completed_market_prediction_rows_for_event(event_id, source=lane)
    deduped = dedupe_inventory_rows(rows, lane=lane)
    return len(filter_positive_ev(deduped))


def _event_reconciliation(
    conn,
    *,
    event_id: str,
    tournament_id: int | None,
    dashboard_lane: dict[str, Any],
    include_past_replay: bool = False,
) -> dict[str, Any]:
    graded_count = int(dashboard_lane.get("graded_pick_count") or 0)
    if not include_past_replay:
        positive_inventory = int(dashboard_lane.get("ungraded_positive_ev_count") or 0) + graded_count
        gap = positive_inventory - graded_count
        return {
            "past_replay_positive_matchups": positive_inventory,
            "graded_deduped_count": graded_count,
            "gap_past_vs_graded": gap,
            "reconciliation_ok": gap == 0 or tournament_id is None,
        }

    past_replay = _past_replay_positive_count(event_id, "dashboard")
    gap = past_replay - graded_count
    return {
        "past_replay_positive_matchups": past_replay,
        "graded_deduped_count": graded_count,
        "gap_past_vs_graded": gap,
        "reconciliation_ok": gap == 0 or tournament_id is None,
    }


def _lane_has_card_import(conn, tournament_id: int | None, lane: str) -> bool:
    if not tournament_id:
        return False
    lane_sql = pick_lane_sql(lane)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM picks p
        WHERE p.tournament_id = ? {lane_sql}
          AND COALESCE(p.reasoning, '') LIKE 'card_import:%'
        """,
        (int(tournament_id),),
    ).fetchone()
    return bool(row and int(row["c"] or 0) > 0)


def _fetch_lane_picks(conn, tournament_id: int | None, lane: str) -> list[dict]:
    if not tournament_id:
        return []
    lane_sql = pick_lane_sql(lane)
    rows = conn.execute(
        f"""
        SELECT
            p.id,
            p.model_variant,
            p.source,
            p.bet_type,
            p.market_type,
            p.player_key,
            p.player_display,
            p.opponent_key,
            p.opponent_display,
            p.market_odds,
            p.market_book,
            p.model_prob,
            p.ev,
            p.reasoning,
            po.hit AS hit,
            po.hit AS bet_hit,
            po.model_hit,
            po.actual_finish,
            po.odds_decimal,
            po.stake,
            ROUND(COALESCE(po.profit, 0), 2) AS profit,
            po.entered_at AS graded_at,
            po.outcome_locked,
            po.grading_authority
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE p.tournament_id = ? {lane_sql}
        ORDER BY po.entered_at, p.id
        """,
        (int(tournament_id),),
    ).fetchall()
    return format_graded_pick_rows([dict(row) for row in rows])


def _lane_inventory_counts(
    conn,
    event_id: str,
    lane: str,
    *,
    tournament_id: int | None = None,
) -> tuple[int, int]:
    """Fast inventory counts — avoid loading the full pick_ledger into memory."""
    ledger_lane = "cockpit" if lane in {"cockpit", "dashboard"} else "lab"
    inventory_row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM pick_ledger
        WHERE event_id = ? AND lane = ?
        """,
        (event_id, ledger_lane),
    ).fetchone()
    inventory_count = int(inventory_row["c"] or 0) if inventory_row else 0

    positive_ev_inventory = 0
    if tournament_id:
        lane_sql = pick_lane_sql(lane)
        pick_row = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM picks p
            WHERE p.tournament_id = ? {lane_sql}
              AND COALESCE(p.ev, 0) > 0
            """,
            (int(tournament_id),),
        ).fetchone()
        positive_ev_inventory = int(pick_row["c"] or 0) if pick_row else 0

    if positive_ev_inventory > 0:
        return inventory_count, positive_ev_inventory

    if inventory_count == 0:
        return 0, 0

    # Fallback for events without durable picks yet: dedupe completed MPR rows only.
    source = "dashboard" if ledger_lane == "cockpit" else "lab"
    rows = db.get_completed_market_prediction_rows_for_event(event_id, source=source)
    deduped = dedupe_inventory_rows(rows, lane=source)
    return inventory_count, len(filter_positive_ev(deduped))


def _build_lane_payload(
    conn,
    *,
    event_id: str,
    tournament_id: int | None,
    lane: str,
    rollup_record: dict | None,
    has_results: bool = True,
) -> dict[str, Any]:
    inventory_count, positive_ev_inventory = _lane_inventory_counts(
        conn,
        event_id,
        lane,
        tournament_id=tournament_id,
    )
    picks = _fetch_lane_picks(conn, tournament_id, lane)
    summary = build_record_summary(picks)
    combined = summary["combined"]
    graded_pick_count = combined["picks"]
    # Only completed events (results present) can have "ungraded +EV" gaps.
    ungraded = (
        max(0, positive_ev_inventory - graded_pick_count)
        if positive_ev_inventory and has_results
        else 0
    )

    record = {
        "wins": combined["wins"],
        "losses": combined["losses"],
        "pushes": combined["pushes"],
        "profit": combined["profit"],
        "hit_rate": combined["hit_rate"],
    }
    if graded_pick_count == 0 and rollup_record and lane in {"cockpit", "dashboard"}:
        record = {
            "wins": rollup_record.get("wins", 0),
            "losses": rollup_record.get("losses", 0),
            "pushes": rollup_record.get("pushes", 0),
            "profit": rollup_record.get("profit", 0),
            "hit_rate": None,
        }

    status = "graded"
    if not graded_pick_count and not inventory_count and not rollup_record:
        status = "no_data"
    elif graded_pick_count == 0 and rollup_record and lane in {"cockpit", "dashboard"}:
        status = "rollup_only"
    elif ungraded > 0:
        status = "partial"
    elif graded_pick_count == 0 and inventory_count > 0 and has_results:
        status = "inventory_only"
    elif graded_pick_count > 0 and _lane_has_card_import(conn, tournament_id, lane):
        status = "card_recovered"
    elif graded_pick_count == 0 and inventory_count > 0:
        status = "partial"

    return {
        "inventory_count": inventory_count,
        "graded_pick_count": graded_pick_count,
        "ungraded_positive_ev_count": ungraded,
        "status": status,
        "record": record,
        "market_stats": summary,
        "picks": picks,
        "hits": combined["wins"],
        "total_profit": combined["profit"],
    }


@router.get("/api/grading/season")
async def get_grading_season(
    year: int = Query(2026, ge=2000, le=2100),
    lane: str = Query("all", pattern="^(all|cockpit|dashboard|lab)$"),
    include_picks: bool = Query(True),
    include_reconciliation: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    tour: str = Query("pga", pattern="^(pga|liv|all)$"),
):
    ensure_initialized()
    conn = get_conn()
    discovered = _discover_season_events(conn, year, tour=None if tour == "all" else tour)

    events_out: list[dict[str, Any]] = []
    all_dashboard_picks: list[dict] = []
    all_lab_picks: list[dict] = []

    def _chronological_key(item: dict[str, Any]) -> tuple:
        raw_date = item.get("event_date") or ""
        return (str(raw_date), str(item.get("name") or ""))

    sorted_events = sorted(discovered.values(), key=_chronological_key)

    for meta in sorted_events[:limit]:
        tournament_id = meta.get("tournament_id")
        if tournament_id is None and meta.get("event_id"):
            row = conn.execute(
                "SELECT id FROM tournaments WHERE event_id = ? AND year = ? LIMIT 1",
                (meta["event_id"], year),
            ).fetchone()
            tournament_id = row["id"] if row else None

        last_graded_at = None
        if tournament_id:
            lg = conn.execute(
                """
                SELECT MAX(po.entered_at) AS last_graded_at
                FROM pick_outcomes po
                JOIN picks p ON p.id = po.pick_id
                WHERE p.tournament_id = ?
                """,
                (tournament_id,),
            ).fetchone()
            last_graded_at = lg["last_graded_at"] if lg else None

        has_results = False
        if tournament_id:
            rc = conn.execute(
                "SELECT COUNT(*) AS c FROM results WHERE tournament_id = ?",
                (tournament_id,),
            ).fetchone()
            has_results = bool(rc and int(rc["c"] or 0) > 0)

        rollup = meta.get("rollup_record")
        dashboard_lane = _build_lane_payload(
            conn,
            event_id=str(meta["event_id"]),
            tournament_id=tournament_id,
            lane="cockpit",
            rollup_record=rollup,
            has_results=has_results,
        )
        lab_lane = _build_lane_payload(
            conn,
            event_id=str(meta["event_id"]),
            tournament_id=tournament_id,
            lane="lab",
            rollup_record=None,
            has_results=has_results,
        )
        reconciliation = _event_reconciliation(
            conn,
            event_id=str(meta["event_id"]),
            tournament_id=tournament_id,
            dashboard_lane=dashboard_lane,
            include_past_replay=include_reconciliation,
        )
        comparison = build_lane_comparison(dashboard_lane["picks"], lab_lane["picks"])
        all_dashboard_picks.extend(dashboard_lane["picks"])
        all_lab_picks.extend(lab_lane["picks"])

        if not include_picks:
            dashboard_lane = {**dashboard_lane, "picks": []}
            lab_lane = {**lab_lane, "picks": []}

        event_payload = {
            "event_id": meta["event_id"],
            "name": meta["name"],
            "course": meta.get("course"),
            "year": meta.get("year", year),
            "event_date": meta.get("event_date"),
            "tournament_id": tournament_id,
            "authority_tier": meta.get("authority_tier"),
            "picks_detail_missing": bool(meta.get("picks_detail_missing")),
            "inventory_count": int(meta.get("inventory_count") or 0),
            "has_results": has_results,
            "last_graded_at": last_graded_at,
            "lanes": {
                "dashboard": dashboard_lane,
                "lab": lab_lane,
            },
            "comparison": comparison,
            "reconciliation": reconciliation,
        }

        if not has_results and dashboard_lane["graded_pick_count"] == 0 and lab_lane["graded_pick_count"] == 0:
            if dashboard_lane["status"] == "no_data":
                event_payload["status"] = "no_data"
            else:
                event_payload["status"] = "in_progress"
        elif lane in {"cockpit", "dashboard"}:
            event_payload["graded_pick_count"] = dashboard_lane["graded_pick_count"]
            event_payload["hits"] = dashboard_lane["hits"]
            event_payload["total_profit"] = dashboard_lane["total_profit"]
            event_payload["picks"] = dashboard_lane["picks"]
            event_payload["status"] = dashboard_lane["status"]
        elif lane == "lab":
            event_payload["graded_pick_count"] = lab_lane["graded_pick_count"]
            event_payload["hits"] = lab_lane["hits"]
            event_payload["total_profit"] = lab_lane["total_profit"]
            event_payload["picks"] = lab_lane["picks"]
            event_payload["status"] = lab_lane["status"]
        else:
            event_payload["graded_pick_count"] = dashboard_lane["graded_pick_count"] + lab_lane["graded_pick_count"]
            event_payload["hits"] = dashboard_lane["hits"] + lab_lane["hits"]
            event_payload["total_profit"] = round(
                float(dashboard_lane["total_profit"] or 0) + float(lab_lane["total_profit"] or 0),
                2,
            )
            event_payload["picks"] = dashboard_lane["picks"] + lab_lane["picks"]
            event_payload["status"] = dashboard_lane["status"] if dashboard_lane["status"] != "graded" else lab_lane["status"]

        events_out.append(event_payload)

    conn.close()

    normalized_lane = "dashboard" if lane in {"cockpit", "dashboard"} else lane
    summary = {
        "dashboard": build_record_summary(all_dashboard_picks)["combined"],
        "lab": build_record_summary(all_lab_picks)["combined"],
        "comparison": build_lane_comparison(
            format_graded_pick_rows(all_dashboard_picks),
            format_graded_pick_rows(all_lab_picks),
        ),
    }

    return {
        "year": year,
        "lane": normalized_lane,
        "events": events_out,
        "tournaments": events_out,
        "summary": summary,
    }


@router.get("/api/grading/event-picks")
async def get_grading_event_picks(
    event_id: str = Query(..., min_length=1),
    year: int = Query(2026, ge=2000, le=2100),
    lane: str = Query("cockpit", pattern="^(cockpit|dashboard|lab)$"),
):
    """Graded picks and record for a single completed event (Past replay)."""
    ensure_initialized()
    conn = get_conn()
    discovered = _discover_season_events(conn, year)
    meta = discovered.get(str(event_id))
    tournament_id = meta.get("tournament_id") if meta else None
    if tournament_id is None:
        row = conn.execute(
            "SELECT id FROM tournaments WHERE event_id = ? AND year = ? LIMIT 1",
            (event_id, year),
        ).fetchone()
        tournament_id = row["id"] if row else None

    has_results = False
    if tournament_id:
        rc = conn.execute(
            "SELECT COUNT(*) AS c FROM results WHERE tournament_id = ?",
            (tournament_id,),
        ).fetchone()
        has_results = bool(rc and int(rc["c"] or 0) > 0)

    rollup = meta.get("rollup_record") if meta else None
    lane_key = "cockpit" if lane == "dashboard" else lane
    payload = _build_lane_payload(
        conn,
        event_id=str(event_id),
        tournament_id=tournament_id,
        lane=lane_key,
        rollup_record=rollup,
        has_results=has_results,
    )
    conn.close()
    return {
        "ok": True,
        "event_id": str(event_id),
        "year": year,
        "lane": lane_key,
        "name": meta.get("name") if meta else None,
        **payload,
    }
