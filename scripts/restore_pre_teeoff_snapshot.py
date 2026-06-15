#!/usr/bin/env python3
"""Retro-freeze pre-teeoff snapshot from earliest recoverable market rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import db


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore pre-teeoff frozen snapshot")
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--source", default="earliest_market_rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    db.ensure_initialized()
    event_id = str(args.event_id).strip()
    rows = db.get_completed_market_prediction_rows_for_event(event_id, source="dashboard")
    if not rows:
        print(f"No recoverable rows for event {event_id}")
        return 1

    tier = rows[0].get("recovery_tier", args.source)
    snap = {
        "source_event_id": event_id,
        "event_id": event_id,
        "event_name": rows[0].get("event_name"),
        "rankings": [],
        "matchup_bets": [],
        "matchup_bets_all_books": [],
        "ranking_source": f"recovered_{tier}",
        "recovered_pre_teeoff": True,
    }
    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        snap["matchup_bets_all_books"].append(payload or row)

    snapshot_id = str(rows[0].get("snapshot_id") or "recovered")
    if args.dry_run:
        print(f"Would freeze {len(rows)} rows for event {event_id} (tier={tier})")
        return 0

    inserted = db.insert_pre_teeoff_frozen(
        event_id,
        tour="pga",
        event_name=snap.get("event_name"),
        section_payload=snap,
        source_snapshot_id=snapshot_id,
    )
    from src.pick_ledger import persist_pick_ledger_from_market_rows

    n = persist_pick_ledger_from_market_rows(
        rows,
        lifecycle="frozen_pre_teeoff",
        source_origin="restore",
    )
    print(f"Frozen inserted={inserted}, ledger_rows={n}, tier={tier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
