#!/usr/bin/env python3
"""Scan pick sources and emit recovery manifest with authority tiers."""

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

TRACK_RECORD = ROOT / "frontend" / "src" / "data" / "trackRecord.json"


def _count_table(conn, table: str, where: str = "", params: tuple = ()) -> int:
    try:
        sql = f"SELECT COUNT(*) AS c FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = conn.execute(sql, params).fetchone()
        return int(row["c"] or 0)
    except Exception:
        return 0


def build_manifest() -> dict:
    db.ensure_initialized()
    conn = db.get_conn()

    track = {}
    if TRACK_RECORD.is_file():
        with open(TRACK_RECORD, encoding="utf-8") as f:
            track = json.load(f)

    events: list[dict] = []
    for ev in track.get("events") or []:
        name = str(ev.get("name") or "")
        picks = ev.get("picks") or []
        tier = "A_authoritative" if picks else "A_rollup_only"
        events.append({
            "name": name,
            "authority_tier": tier,
            "trackRecord_picks": len(picks),
            "trackRecord_record": ev.get("record"),
            "profit_units": ev.get("profit_units"),
            "picks_detail_missing": len(picks) == 0,
        })

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            "picks": _count_table(conn, "picks"),
            "pick_outcomes": _count_table(conn, "pick_outcomes"),
            "pick_ledger": _count_table(conn, "pick_ledger"),
            "market_prediction_rows": _count_table(conn, "market_prediction_rows"),
            "live_snapshot_history": _count_table(conn, "live_snapshot_history"),
            "pre_teeoff_frozen": _count_table(conn, "pre_teeoff_frozen"),
        },
        "trackRecord_headline": track.get("headline"),
        "events": events,
    }

    try:
        rows = conn.execute(
            """
            SELECT event_id, COUNT(*) AS c, MIN(generated_at) AS first_at, MAX(generated_at) AS last_at
            FROM market_prediction_rows
            GROUP BY event_id
            ORDER BY last_at DESC
            """
        ).fetchall()
        manifest["market_prediction_rows_by_event"] = [dict(r) for r in rows]
    except Exception:
        manifest["market_prediction_rows_by_event"] = []

    conn.close()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory pick sources for recovery")
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs" / "recovery" / f"pick_inventory_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"),
    )
    args = parser.parse_args()

    manifest = build_manifest()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
