"""Freeze canonical +EV picks when an event completes."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.market_row_backfill import backfill_completed_market_rows_into_picks
from src.official_pick_record import filter_positive_ev

logger = logging.getLogger(__name__)


def freeze_completed_event_picks(
    event_id: str,
    *,
    year: int,
    event_name: str | None = None,
) -> dict[str, Any]:
    """Backfill dashboard + lab lanes and grade if inventory exists."""
    db.ensure_initialized()
    conn = db.get_conn()
    tournament = conn.execute(
        "SELECT id, name FROM tournaments WHERE event_id = ? AND year = ? ORDER BY id DESC LIMIT 1",
        (event_id, year),
    ).fetchone()
    if not tournament:
        name = event_name or f"Event {event_id}"
        cur = conn.execute(
            "INSERT INTO tournaments (name, year, event_id) VALUES (?, ?, ?)",
            (name, year, event_id),
        )
        conn.commit()
        tournament_id = int(cur.lastrowid)
    else:
        tournament_id = int(tournament["id"])
    conn.close()

    dash_rows = db.get_completed_market_prediction_rows_for_event(event_id, source="dashboard")
    lab_rows = db.get_completed_market_prediction_rows_for_event(event_id, source="lab")
    dash_positive = filter_positive_ev(dash_rows)
    lab_positive = filter_positive_ev(lab_rows)

    if not dash_positive and not lab_positive:
        return {
            "status": "skipped",
            "reason": "no_positive_ev_inventory",
            "event_id": event_id,
            "year": year,
        }

    dash_inserted = backfill_completed_market_rows_into_picks(event_id, tournament_id, source="dashboard")
    lab_inserted = backfill_completed_market_rows_into_picks(event_id, tournament_id, source="lab")

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
        "grade_report": report,
    }
