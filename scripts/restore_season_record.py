#!/usr/bin/env python3
"""Restore 2026 season record into pick_ledger + picks + locked pick_outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import db
from src.pick_ledger import (
    compute_pick_key,
    insert_authoritative_pick_outcome,
    normalize_american_odds,
    persist_pick_ledger_rows,
    persist_pick_ledger_from_market_rows,
    result_to_hit,
)
from src.player_normalizer import display_name, normalize_name

TRACK_RECORD = ROOT / "frontend" / "src" / "data" / "trackRecord.json"
SNAPSHOT_ID = "trackRecord_json"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _resolve_event_id(conn, event_name: str, year: int = 2026) -> str | None:
    needle = event_name.strip().lower()
    rows = conn.execute(
        """
        SELECT DISTINCT event_id, event_name FROM rounds
        WHERE year = ? AND LOWER(event_name) LIKE ?
        """,
        (year, f"%{needle}%"),
    ).fetchall()
    if not rows:
        return None
    for row in rows:
        if str(row["event_name"] or "").strip().lower() == needle:
            return str(row["event_id"])
    if len(rows) == 1:
        return str(rows[0]["event_id"])
    return None


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


def import_track_record(*, dry_run: bool = True) -> dict:
    db.ensure_initialized()
    with open(TRACK_RECORD, encoding="utf-8") as f:
        data = json.load(f)

    source_hash = _file_hash(TRACK_RECORD)
    stats = {"events": 0, "picks_imported": 0, "skipped": 0, "errors": []}
    conn = db.get_conn()

    for event in data.get("events") or []:
        picks = event.get("picks") or []
        if not picks:
            continue
        name = str(event.get("name") or "")
        event_id = _resolve_event_id(conn, name)
        if not event_id:
            stats["errors"].append({"event": name, "error": "unresolved_event_id"})
            continue
        tid = _ensure_tournament(
            conn,
            name=name,
            event_id=event_id,
            year=2026,
            course=event.get("course"),
        )
        stats["events"] += 1

        for p in picks:
            player_key = normalize_name(str(p.get("pick") or ""))
            opponent_key = normalize_name(str(p.get("opponent") or ""))
            odds = normalize_american_odds(p.get("odds"))
            pick_key = compute_pick_key(
                event_id=event_id,
                lane="cockpit",
                section="upcoming",
                phase="pre_tournament",
                bet_type="matchup",
                player_key=player_key,
                opponent_key=opponent_key,
                book="",
                odds=odds,
                snapshot_id=SNAPSHOT_ID,
            )
            pick_row = {
                "tournament_id": tid,
                "model_variant": "baseline",
                "source": "cockpit",
                "bet_type": "matchup",
                "player_key": player_key,
                "player_display": str(p.get("pick") or ""),
                "opponent_key": opponent_key,
                "opponent_display": str(p.get("opponent") or ""),
                "market_odds": odds,
                "market_book": "",
                "ev": 0.01,
                "reasoning": f"recovered_from:trackRecord.json;hash={source_hash}",
            }
            ledger_row = {
                "pick_key": pick_key,
                "event_id": event_id,
                "event_name": name,
                "tournament_id": tid,
                "year": 2026,
                "phase": "pre_tournament",
                "section": "upcoming",
                "lane": "cockpit",
                "lifecycle": "recovered",
                "bet_type": "matchup",
                "market_family": "matchup",
                "market_type": "matchup",
                "player_key": player_key,
                "player_display": pick_row["player_display"],
                "opponent_key": opponent_key,
                "opponent_display": pick_row["opponent_display"],
                "book": "",
                "odds": odds,
                "model_prob": None,
                "implied_prob": None,
                "ev": 0.01,
                "is_value": 1,
                "model_variant": "baseline",
                "model_config_hash": None,
                "snapshot_id": SNAPSHOT_ID,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "source_origin": "restore",
                "payload_json": json.dumps(p),
            }
            if dry_run:
                stats["picks_imported"] += 1
                continue
            insert_authoritative_pick_outcome(
                tournament_id=tid,
                pick_row=pick_row,
                ledger_row=ledger_row,
                result=str(p.get("result") or ""),
                profit=float(p.get("pl") or 0),
                grading_authority="trackRecord_json",
                notes=f"recovered_from:trackRecord.json;hash={source_hash}",
            )
            stats["picks_imported"] += 1

    conn.close()
    return stats


def import_market_ticks(*, dry_run: bool = True, limit: int = 10000) -> dict:
    """Tier B: import tick inventory into ledger only (no grading)."""
    db.ensure_initialized()
    conn = db.get_conn()
    event_ids = [
        str(r["event_id"])
        for r in conn.execute(
            "SELECT DISTINCT event_id FROM market_prediction_rows WHERE event_id IS NOT NULL"
        ).fetchall()
    ]
    conn.close()
    total = 0
    for eid in event_ids:
        rows = db.get_completed_market_prediction_rows_for_event(eid, source="dashboard", limit=limit)
        if dry_run:
            total += len(rows)
            continue
        total += persist_pick_ledger_from_market_rows(
            rows,
            lifecycle="recovered",
            source_origin="restore",
        )
    return {"events": len(event_ids), "ledger_rows": total}


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore season grading record")
    parser.add_argument("--apply", action="store_true", help="Write to DB (default is dry-run)")
    parser.add_argument("--skip-ticks", action="store_true")
    parser.add_argument("--grade-unscored", action="store_true", help="Run grade_tournament for unscored events")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    dry_run = not args.apply
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")

    tr_stats = import_track_record(dry_run=dry_run)
    print("trackRecord import:", json.dumps(tr_stats, indent=2))

    tick_stats = {"skipped": True}
    if not args.skip_ticks:
        tick_stats = import_market_ticks(dry_run=dry_run)
        print("tick import:", json.dumps(tick_stats, indent=2))

    if args.grade_unscored and args.apply:
        from scripts.grade_tournament import grade_tournament

        conn = db.get_conn()
        events = conn.execute(
            """
            SELECT DISTINCT t.event_id, t.year, t.id, t.name
            FROM tournaments t
            WHERE t.year = 2026 AND t.event_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM pick_outcomes po
                JOIN picks p ON p.id = po.pick_id
                WHERE p.tournament_id = t.id AND COALESCE(po.outcome_locked, 0) = 1
              )
            """
        ).fetchall()
        conn.close()
        for ev in events:
            print(f"Grading unscored event {ev['name']} ({ev['event_id']})")
            grade_tournament(
                str(ev["event_id"]),
                int(ev["year"] or 2026),
                tournament_id=int(ev["id"]),
                event_name=ev["name"],
                unscored_only=True,
            )

    if args.apply:
        from scripts.verify_season_record import verify

        report = verify(TRACK_RECORD)
        print("Verification:", json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
