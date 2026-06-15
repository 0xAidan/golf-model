#!/usr/bin/env python3
"""Hydrate and grade the full 2026 season — both Dashboard and Lab lanes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import db
from src.market_row_backfill import backfill_completed_market_rows_into_picks

TRACK_RECORD = ROOT / "frontend" / "src" / "data" / "trackRecord.json"


def _events_with_inventory(conn, year: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(pl.event_id, t.event_id) AS event_id,
            MAX(COALESCE(pl.event_name, t.name)) AS name,
            MAX(COALESCE(pl.year, t.year)) AS year,
            MAX(t.id) AS tournament_id,
            MAX(t.course) AS course,
            COUNT(pl.id) AS ledger_rows
        FROM pick_ledger pl
        LEFT JOIN tournaments t ON t.id = pl.tournament_id
        WHERE COALESCE(pl.year, t.year) = ?
          AND COALESCE(pl.event_id, t.event_id) IS NOT NULL
          AND TRIM(COALESCE(pl.event_id, t.event_id)) != ''
        GROUP BY COALESCE(pl.event_id, t.event_id)
        """,
        (year,),
    ).fetchall()

    mpr_rows = conn.execute(
        """
        SELECT event_id, MAX(event_name) AS name, COUNT(*) AS mpr_rows
        FROM market_prediction_rows
        WHERE event_id IN (
            SELECT DISTINCT event_id FROM rounds WHERE year = ?
        )
        GROUP BY event_id
        HAVING COUNT(*) > 0
        """,
        (year,),
    ).fetchall()
    mpr_by_id = {str(row["event_id"]): dict(row) for row in mpr_rows}

    events: dict[str, dict] = {}
    for row in rows:
        eid = str(row["event_id"])
        events[eid] = dict(row)

    for eid, row in mpr_by_id.items():
        if eid in events:
            events[eid]["mpr_rows"] = int(row["mpr_rows"] or 0)
            continue
        t_row = conn.execute(
            "SELECT id, name, course, year FROM tournaments WHERE event_id = ? AND year = ? LIMIT 1",
            (eid, year),
        ).fetchone()
        events[eid] = {
            "event_id": eid,
            "name": row.get("name") or (t_row["name"] if t_row else f"Event {eid}"),
            "year": year,
            "tournament_id": t_row["id"] if t_row else None,
            "course": t_row["course"] if t_row else None,
            "ledger_rows": 0,
            "mpr_rows": int(row["mpr_rows"] or 0),
        }

    return list(events.values())


def _ensure_tournament(conn, *, name: str, event_id: str, year: int, course: str | None) -> int:
    row = conn.execute(
        "SELECT id FROM tournaments WHERE event_id = ? AND year = ?",
        (event_id, year),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO tournaments (name, course, year, event_id) VALUES (?, ?, ?, ?)",
        (name, course, year, event_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def hydrate_event(
    event_id: str,
    *,
    year: int,
    name: str,
    tournament_id: int | None,
    course: str | None,
    dry_run: bool,
) -> dict:
    stats = {
        "event_id": event_id,
        "name": name,
        "dashboard_backfilled": 0,
        "lab_backfilled": 0,
        "graded": False,
        "grade_status": None,
    }
    if dry_run:
        dash_rows = db.get_completed_market_prediction_rows_for_event(event_id, source="dashboard")
        lab_rows = db.get_completed_market_prediction_rows_for_event(event_id, source="lab")
        stats["dashboard_candidates"] = len([r for r in dash_rows if (r.get("ev") or 0) > 0])
        stats["lab_candidates"] = len([r for r in lab_rows if (r.get("ev") or 0) > 0])
        return stats

    conn = db.get_conn()
    tid = tournament_id or _ensure_tournament(
        conn,
        name=name,
        event_id=event_id,
        year=year,
        course=course,
    )
    conn.close()

    stats["dashboard_backfilled"] = backfill_completed_market_rows_into_picks(
        event_id,
        tid,
        source="dashboard",
    )
    stats["lab_backfilled"] = backfill_completed_market_rows_into_picks(
        event_id,
        tid,
        source="lab",
    )

    from scripts.grade_tournament import grade_tournament

    report = grade_tournament(
        event_id,
        year,
        tournament_id=tid,
        event_name=name,
        unscored_only=True,
    )
    stats["graded"] = True
    stats["grade_status"] = report.get("status")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Hydrate and grade 2026 season inventory")
    parser.add_argument("--apply", action="store_true", help="Write to DB and grade (default dry-run)")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--event-id", action="append", dest="event_ids", help="Limit to specific event id(s)")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    db.ensure_initialized()
    dry_run = not args.apply
    conn = db.get_conn()
    events = _events_with_inventory(conn, args.year)
    conn.close()

    if args.event_ids:
        allowed = {str(eid) for eid in args.event_ids}
        events = [event for event in events if str(event["event_id"]) in allowed]

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "year": args.year,
        "dry_run": dry_run,
        "events": [],
    }

    for event in events:
        print(f"{'[dry-run] ' if dry_run else ''}Hydrating {event['name']} ({event['event_id']})...")
        try:
            result = hydrate_event(
                str(event["event_id"]),
                year=int(event.get("year") or args.year),
                name=str(event.get("name") or f"Event {event['event_id']}"),
                tournament_id=event.get("tournament_id"),
                course=event.get("course"),
                dry_run=dry_run,
            )
            manifest["events"].append(result)
            print(json.dumps(result, indent=2))
        except Exception as exc:
            err = {"event_id": event["event_id"], "name": event.get("name"), "error": str(exc)}
            manifest["events"].append(err)
            print(f"ERROR: {event.get('name')}: {exc}", file=sys.stderr)

    out_path = ROOT / "output" / "audits" / f"hydrate_season_{args.year}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest written to {out_path}")

    if args.apply and TRACK_RECORD.is_file():
        from scripts.verify_season_record import verify

        report = verify(TRACK_RECORD)
        print("Verification:", json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
