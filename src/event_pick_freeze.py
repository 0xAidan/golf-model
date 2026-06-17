"""Ensure completed events have picks captured and graded."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.market_row_backfill import backfill_completed_market_rows_into_picks
from src.official_pick_record import filter_positive_ev

logger = logging.getLogger(__name__)


def _ensure_tournament(
    conn,
    *,
    event_id: str,
    year: int,
    event_name: str | None,
) -> int:
    row = conn.execute(
        "SELECT id FROM tournaments WHERE event_id = ? AND year = ? ORDER BY id DESC LIMIT 1",
        (event_id, year),
    ).fetchone()
    if row:
        return int(row["id"])
    name = event_name or f"Event {event_id}"
    cur = conn.execute(
        "INSERT INTO tournaments (name, year, event_id) VALUES (?, ?, ?)",
        (name, year, event_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def _ungraded_positive_ev_count(conn, tournament_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM picks p
        LEFT JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE p.tournament_id = ?
          AND p.ev IS NOT NULL AND p.ev > 0
          AND po.id IS NULL
        """,
        (tournament_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def _event_has_results(conn, tournament_id: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM results WHERE tournament_id = ?",
        (tournament_id,),
    ).fetchone()
    return bool(row and int(row["c"] or 0) > 0)


def _inventory_exists(event_id: str) -> tuple[int, int]:
    conn = db.get_conn()
    try:
        ledger = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM pick_ledger WHERE event_id = ? AND is_value = 1",
                (event_id,),
            ).fetchone()["c"]
            or 0
        )
        mpr = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM market_prediction_rows WHERE event_id = ?",
                (event_id,),
            ).fetchone()["c"]
            or 0
        )
        return ledger, mpr
    finally:
        conn.close()


def capture_pre_teeoff_picks(
    event_id: str,
    *,
    year: int,
    event_name: str | None,
    section_payload: dict[str, Any],
) -> int:
    """Persist +EV lines from a frozen pre-teeoff board into gradeable picks."""
    if not event_id or not section_payload:
        return 0
    db.ensure_initialized()
    conn = db.get_conn()
    tournament_id = _ensure_tournament(conn, event_id=event_id, year=year, event_name=event_name)
    conn.close()

    rows = db._market_rows_from_snapshot_payload(
        section_payload,
        event_id=event_id,
        section="frozen",
        limit=10000,
    )
    if not rows:
        matchups = section_payload.get("matchup_bets") or section_payload.get("matchups") or []
        for row in matchups:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "event_id": event_id,
                    "section": "frozen",
                    "market_family": "matchup",
                    "market_type": row.get("market_type") or "tournament_matchups",
                    "player_key": row.get("player_key"),
                    "player_display": row.get("player") or row.get("pick"),
                    "opponent_key": row.get("opponent_key"),
                    "opponent_display": row.get("opponent"),
                    "book": row.get("bookmaker") or row.get("book"),
                    "odds": row.get("market_odds") or row.get("odds"),
                    "model_prob": row.get("model_prob"),
                    "ev": row.get("ev"),
                    "payload": row,
                }
            )

    positive = filter_positive_ev(rows)
    if not positive:
        return 0

    conn = db.get_conn()
    try:
        before_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM picks WHERE tournament_id = ? AND source = 'cockpit'",
                (tournament_id,),
            ).fetchone()[0]
            or 0
        )
    finally:
        conn.close()

    from src.market_row_backfill import _row_to_pick

    pick_rows = [
        _row_to_pick(row, tournament_id=tournament_id, source="cockpit", default_model_variant="baseline")
        for row in positive
        if row.get("player_key") or row.get("player_display")
    ]
    pick_rows = [row for row in pick_rows if row.get("ev") is not None and row.get("ev") > 0]
    if not pick_rows:
        return 0
    db.store_picks(pick_rows)

    conn = db.get_conn()
    try:
        after_count = conn.execute(
            "SELECT COUNT(*) FROM picks WHERE tournament_id = ? AND source = 'cockpit'",
            (tournament_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    return max(0, int(after_count) - int(before_count))


def _backfill_ledger_tournament_id(
    conn,
    *,
    event_id: str,
    tournament_id: int,
    year: int,
) -> int:
    cur = conn.execute(
        """
        UPDATE pick_ledger
        SET tournament_id = ?, year = COALESCE(year, ?)
        WHERE event_id = ? AND (tournament_id IS NULL OR tournament_id = 0)
        """,
        (tournament_id, year, event_id),
    )
    conn.commit()
    return int(cur.rowcount or 0)


def _write_canonical_ledger_rows(
    event_id: str,
    *,
    tournament_id: int,
    year: int,
    event_name: str | None,
) -> int:
    from src.official_pick_record import dedupe_inventory_rows, filter_positive_ev
    from src.pick_ledger import persist_pick_ledger_from_market_rows

    written = 0
    for source in ("dashboard", "lab"):
        rows = db.get_completed_market_prediction_rows_for_event(event_id, source=source)
        matchups = [row for row in rows if str(row.get("market_family") or "").lower() == "matchup"]
        deduped = dedupe_inventory_rows(matchups, lane=source)
        positive = filter_positive_ev(deduped)
        for row in positive:
            row["event_name"] = event_name
            row["year"] = year
        written += persist_pick_ledger_from_market_rows(
            positive,
            lifecycle="canonical",
            source_origin="event_freeze",
            tournament_id=tournament_id,
            year=year,
        )
    return written


def freeze_completed_event_picks(
    event_id: str,
    *,
    year: int,
    event_name: str | None = None,
) -> dict[str, Any]:
    """Backfill dashboard + lab lanes and grade when inventory exists."""
    db.ensure_initialized()
    conn = db.get_conn()
    tournament_id = _ensure_tournament(conn, event_id=event_id, year=year, event_name=event_name)
    has_results = _event_has_results(conn, tournament_id)
    conn.close()

    ledger_count, mpr_count = _inventory_exists(event_id)
    if ledger_count == 0 and mpr_count == 0:
        return {
            "status": "skipped",
            "reason": "no_inventory",
            "event_id": event_id,
            "year": year,
        }

    dash_inserted = backfill_completed_market_rows_into_picks(event_id, tournament_id, source="dashboard")
    lab_inserted = backfill_completed_market_rows_into_picks(event_id, tournament_id, source="lab")

    conn = db.get_conn()
    ledger_linked = _backfill_ledger_tournament_id(
        conn,
        event_id=event_id,
        tournament_id=tournament_id,
        year=year,
    )
    canonical_ledger = _write_canonical_ledger_rows(
        event_id,
        tournament_id=tournament_id,
        year=year,
        event_name=event_name,
    )
    ungraded = _ungraded_positive_ev_count(conn, tournament_id)
    conn.close()

    if not has_results:
        return {
            "status": "captured",
            "reason": "awaiting_results",
            "event_id": event_id,
            "year": year,
            "tournament_id": tournament_id,
            "dashboard_backfilled": dash_inserted,
            "lab_backfilled": lab_inserted,
            "ledger_tournament_linked": ledger_linked,
            "canonical_ledger_rows": canonical_ledger,
            "ungraded_positive_ev": ungraded,
        }

    if ungraded == 0 and dash_inserted == 0 and lab_inserted == 0:
        return {
            "status": "skipped",
            "reason": "already_graded",
            "event_id": event_id,
            "year": year,
            "tournament_id": tournament_id,
            "ledger_tournament_linked": ledger_linked,
            "canonical_ledger_rows": canonical_ledger,
        }

    from scripts.grade_tournament import grade_tournament

    report = grade_tournament(
        event_id,
        year,
        tournament_id=tournament_id,
        event_name=event_name,
        unscored_only=True,
    )
    return {
        "status": report.get("status", "unknown"),
        "event_id": event_id,
        "year": year,
        "tournament_id": tournament_id,
        "dashboard_backfilled": dash_inserted,
        "lab_backfilled": lab_inserted,
        "ledger_tournament_linked": ledger_linked,
        "canonical_ledger_rows": canonical_ledger,
        "grade_report": report,
    }


def ensure_all_completed_pga_events_graded(*, year: int | None = None) -> dict[str, Any]:
    """Backfill + grade every completed PGA event that still has ungraded +EV picks."""
    db.ensure_initialized()
    conn = db.get_conn()
    current_year = year or __import__("datetime").datetime.now().year
    rows = conn.execute(
        """
        SELECT r.event_id, r.event_name, r.year
        FROM rounds r
        WHERE r.year = ?
          AND LOWER(COALESCE(r.tour, 'pga')) = 'pga'
          AND r.event_id IS NOT NULL AND TRIM(r.event_id) != ''
          AND r.event_completed IS NOT NULL
        GROUP BY r.event_id, r.event_name, r.year
        ORDER BY MIN(r.event_completed) ASC, r.event_name ASC
        """,
        (current_year,),
    ).fetchall()
    conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        event_id = str(row["event_id"])
        event_year = int(row["year"] or current_year)
        result = freeze_completed_event_picks(
            event_id,
            year=event_year,
            event_name=str(row["event_name"] or ""),
        )
        if result.get("status") not in {"skipped"} or result.get("reason") != "no_inventory":
            results.append(result)

    failures = [r for r in results if r.get("status") not in {"ok", "captured", "skipped", "success"}]
    return {
        "year": current_year,
        "events_processed": len(results),
        "results": results,
        "ok": len(failures) == 0,
    }
