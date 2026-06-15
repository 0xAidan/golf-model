#!/usr/bin/env python3
"""Reconcile DB season record against trackRecord.json baseline (accuracy gate)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import db
from src.pick_ledger import normalize_american_odds
from src.player_normalizer import normalize_name

DEFAULT_BASELINE = ROOT / "frontend" / "src" / "data" / "trackRecord.json"
TOLERANCE = 0.01


def _resolve_event_id(event_name: str, year: int = 2026) -> str | None:
    conn = db.get_conn()
    needle = event_name.strip().lower()
    rows = conn.execute(
        """
        SELECT DISTINCT event_id, event_name FROM rounds
        WHERE year = ? AND LOWER(event_name) LIKE ?
        ORDER BY event_completed DESC
        LIMIT 5
        """,
        (year, f"%{needle}%"),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    if len(rows) == 1:
        return str(rows[0]["event_id"])
    for row in rows:
        if str(row["event_name"] or "").strip().lower() == needle:
            return str(row["event_id"])
    return str(rows[0]["event_id"])


def _pick_identity(pick: str, opponent: str, odds: str) -> tuple[str, str, str]:
    return (
        normalize_name(pick),
        normalize_name(opponent),
        normalize_american_odds(odds),
    )


def _db_picks_for_event(tournament_id: int) -> list[dict]:
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT p.player_display, p.opponent_display, p.player_key, p.opponent_key,
               p.market_odds, po.hit, po.profit, po.grading_authority, po.outcome_locked
        FROM picks p
        LEFT JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE p.tournament_id = ? AND p.bet_type = 'matchup'
        ORDER BY p.id ASC
        """,
        (tournament_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _result_from_db_row(row: dict) -> str:
    if row.get("hit") == 1:
        return "win"
    profit = float(row.get("profit") or 0)
    if row.get("hit") == 0 and abs(profit) < TOLERANCE:
        return "push"
    if row.get("hit") is not None:
        return "loss"
    return "ungraded"


def verify(baseline_path: Path) -> dict:
    db.ensure_initialized()
    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)

    headline = baseline.get("headline") or {}
    detail_events = [e for e in (baseline.get("events") or []) if e.get("picks")]
    rollup_only = [e for e in (baseline.get("events") or []) if not e.get("picks")]
    expected_detail_staked = sum(len(e.get("picks") or []) for e in detail_events)

    mismatches: list[dict] = []
    events_checked = 0
    picks_checked = 0

    wins = losses = pushes = 0
    profit_total = 0.0
    staked = 0

    for event in detail_events:
        name = str(event.get("name") or "")
        picks = event.get("picks") or []
        events_checked += 1
        event_id = _resolve_event_id(name)
        if not event_id:
            mismatches.append({"event": name, "error": "event_id_not_resolved"})
            continue
        conn = db.get_conn()
        t_row = conn.execute(
            "SELECT id FROM tournaments WHERE event_id = ? AND year = 2026",
            (event_id,),
        ).fetchone()
        conn.close()
        if not t_row:
            mismatches.append({"event": name, "error": "tournament_not_in_db", "event_id": event_id})
            continue
        tid = int(t_row["id"])
        db_rows = _db_picks_for_event(tid)

        baseline_by_key: dict[tuple, dict] = {}
        for p in picks:
            key = _pick_identity(p.get("pick", ""), p.get("opponent", ""), p.get("odds", ""))
            baseline_by_key[key] = p

        db_by_key: dict[tuple, dict] = {}
        for row in db_rows:
            key = (
                str(row.get("player_key") or ""),
                str(row.get("opponent_key") or ""),
                normalize_american_odds(row.get("market_odds")),
            )
            db_by_key[key] = row

        if len(baseline_by_key) != len(db_by_key):
            mismatches.append({
                "event": name,
                "error": "pick_count_mismatch",
                "expected": len(baseline_by_key),
                "actual": len(db_by_key),
            })

        for key, bp in baseline_by_key.items():
            picks_checked += 1
            row = db_by_key.get(key)
            if not row:
                mismatches.append({"event": name, "error": "missing_pick", "pick": bp})
                continue
            result = _result_from_db_row(row)
            expected_result = str(bp.get("result") or "").strip().lower()
            if result != expected_result:
                mismatches.append({
                    "event": name,
                    "error": "result_mismatch",
                    "pick": bp,
                    "expected": expected_result,
                    "actual": result,
                })
            expected_pl = float(bp.get("pl") or 0)
            actual_pl = float(row.get("profit") or 0)
            if abs(expected_pl - actual_pl) > TOLERANCE:
                mismatches.append({
                    "event": name,
                    "error": "pl_mismatch",
                    "pick": bp,
                    "expected_pl": expected_pl,
                    "actual_pl": actual_pl,
                })
            if expected_result == "win":
                wins += 1
            elif expected_result == "loss":
                losses += 1
            elif expected_result == "push":
                pushes += 1
            profit_total += expected_pl
            staked += 1

    expected_w = int(headline.get("wins") or 0)
    expected_l = int(headline.get("losses") or 0)
    expected_p = int(headline.get("pushes") or 0)
    _ = (expected_w, expected_l, expected_p)

    if picks_checked != expected_detail_staked:
        mismatches.append({
            "error": "detail_staked_mismatch",
            "expected": expected_detail_staked,
            "actual": picks_checked,
        })

    return {
        "ok": len(mismatches) == 0,
        "baseline": str(baseline_path),
        "events_checked": events_checked,
        "picks_checked": picks_checked,
        "rollup_only_events": [str(e.get("name")) for e in rollup_only],
        "rollup": {
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "profit_units": round(profit_total, 2),
            "detail_staked_expected": expected_detail_staked,
            "full_season_headline": headline,
        },
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify season record vs trackRecord.json")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    db.ensure_initialized()
    report = verify(Path(args.baseline))
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
