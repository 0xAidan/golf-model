#!/usr/bin/env python3
"""
Automated Tournament Grading

Fetches final results and matchup outcomes from the Data Golf API,
stores them in the DB, and runs the full post-tournament learning pipeline.

Usage:
    python scripts/grade_tournament.py --event-id 14 --year 2026
    python scripts/grade_tournament.py --event-name "The Players Championship" --year 2026
    python scripts/grade_tournament.py --latest
"""

import os
import sys
import argparse
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import db
from src.event_results import fetch_event_results
from src.datagolf import _call_api

logger = logging.getLogger("grade_tournament")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def build_grading_report(score_result: dict, reconciliation: dict) -> dict:
    """Summarize a grading run for UI/ops surfaces."""
    scored = int(score_result.get("scored_count") or score_result.get("scored") or 0)
    voided = int(score_result.get("voided_count") or score_result.get("voided") or 0)
    events = reconciliation.get("events") or []
    event_row = events[0] if events else {}
    ungraded = int(event_row.get("ungraded_positive_ev_picks") or 0)
    recon_status = reconciliation.get("status", "ok")
    status = "complete" if ungraded == 0 and recon_status == "ok" else "partial"
    message = None
    if status == "partial":
        if ungraded > 0:
            message = f"{ungraded} +EV pick(s) still ungraded after scoring"
        elif recon_status != "ok":
            message = "Grading reconciliation reported discrepancies"
    return {
        "status": status,
        "scored_count": scored,
        "voided_count": voided,
        "skipped_count": ungraded,
        "ungraded_positive_ev": ungraded,
        "voided_picks": score_result.get("voided_picks") or [],
        "message": message,
    }


def fetch_matchup_outcomes(event_id: str, year: int, book: str = "bet365") -> list[dict]:
    """Fetch matchup outcomes from DG historical-odds/matchups."""
    try:
        raw = _call_api("historical-odds/matchups", {
            "tour": "pga",
            "event_id": event_id,
            "year": year,
            "book": book,
            "odds_format": "american",
        })
    except Exception as e:
        logger.warning("Failed to fetch matchup outcomes: %s", e)
        return []

    if not raw:
        return []

    matchups = raw if isinstance(raw, list) else raw.get("odds", [])
    return matchups


def resolve_tournament(event_name: str = None, event_id: str = None, year: int = None) -> dict | None:
    """Find a tournament in the DB by name or event_id."""
    if year is None:
        year = datetime.now().year

    conn = db.get_conn()

    if event_id:
        row = conn.execute(
            "SELECT id, name, event_id, year FROM tournaments WHERE event_id = ? AND year = ?",
            (str(event_id), year),
        ).fetchone()
        if row:
            conn.close()
            return dict(row)

    if event_name:
        row = conn.execute(
            "SELECT id, name, event_id, year FROM tournaments WHERE name LIKE ? AND year = ?",
            (f"%{event_name}%", year),
        ).fetchone()
        if row:
            conn.close()
            return dict(row)

    conn.close()
    return None


def find_latest_completed_event() -> dict | None:
    """Find the most recently completed PGA event from DG schedule."""
    from src.datagolf import get_latest_completed_event_info

    info = get_latest_completed_event_info("pga")
    if not info:
        return None
    year_raw = info.get("year") or info.get("season")
    if year_raw is None:
        end_date = info.get("end_date")
        year_raw = str(end_date)[:4] if end_date else datetime.now().strftime("%Y")
    return {
        "event_id": str(info.get("event_id", "")),
        "event_name": info.get("event_name", ""),
        "year": int(str(year_raw)[:4]),
    }


def grade_tournament(
    event_id: str,
    year: int,
    tournament_id: int = None,
    event_name: str = None,
    *,
    unscored_only: bool = True,
    force_audit: bool = False,
    audit_reason: str | None = None,
    skip_backfill_if_locked: bool = True,
) -> dict:
    """
    Run the full grading pipeline for a completed tournament.

    1. Fetch results from DG
    2. Store results in DB
    3. Fetch matchup outcomes
    4. Score picks
    5. Run full post-tournament learning
    """
    db.ensure_initialized()
    report = {
        "event_id": event_id,
        "year": year,
        "timestamp": datetime.now().isoformat(),
        "steps": {},
    }

    # 1. Fetch results
    print(f"  Fetching results for event {event_id} / {year}...")
    results = fetch_event_results(event_id, year)
    report["steps"]["fetch_results"] = {"count": len(results)}
    if not results:
        report["status"] = "error"
        report["message"] = "No results returned from DG API"
        print("  ERROR: No results found")
        return report
    print(f"  Found {len(results)} players")

    # 2. Resolve or create tournament
    if tournament_id is None:
        t = resolve_tournament(event_name=event_name, event_id=event_id, year=year)
        if t:
            tournament_id = t["id"]
            print(f"  Matched to tournament ID {tournament_id}: {t['name']}")
        else:
            name = event_name or f"Event {event_id}"
            tournament_id = db.get_or_create_tournament(
                name, date=None, year=year, event_id=event_id,
            )
            print(f"  Created tournament ID {tournament_id}: {name}")

    report["tournament_id"] = tournament_id

    # 3. Store results
    print(f"  Storing {len(results)} results...")
    db.store_results(tournament_id, results)
    report["steps"]["store_results"] = {"stored": len(results)}

    # 4. Fetch matchup outcomes for grading
    print("  Fetching matchup outcomes...")
    matchup_outcomes = fetch_matchup_outcomes(event_id, year)
    from src.matchup_outcome_store import store_matchup_outcomes

    stored_matchup_outcomes = store_matchup_outcomes(
        tournament_id,
        event_id,
        year,
        matchup_outcomes,
    )
    report["steps"]["matchup_outcomes"] = {
        "count": len(matchup_outcomes),
        "stored": stored_matchup_outcomes,
    }
    if matchup_outcomes:
        print(f"  Found {len(matchup_outcomes)} matchup records ({stored_matchup_outcomes} stored)")
    else:
        print("  No matchup outcomes available (normal for some events)")

    # 5. Backfill durable displayed rows before scoring (skip if authoritative outcomes exist)
    from src.pick_ledger import tournament_has_locked_outcomes
    from src.official_pick_record import consolidate_duplicate_picks

    dashboard_backfilled = 0
    lab_backfilled = 0
    has_locked = skip_backfill_if_locked and tournament_has_locked_outcomes(tournament_id)
    if has_locked:
        print("  Skipping market-row backfill — tournament has locked authoritative outcomes")
        report["steps"]["market_row_pick_backfill"] = {
            "dashboard_inserted": 0,
            "lab_inserted": 0,
            "skipped": "locked_outcomes",
        }
    else:
        print("  Backfilling completed market rows into gradeable picks...")
        from src.market_row_backfill import backfill_completed_market_rows_into_picks

        dashboard_backfilled = backfill_completed_market_rows_into_picks(
            event_id,
            tournament_id,
            source="dashboard",
        )
        lab_backfilled = backfill_completed_market_rows_into_picks(
            event_id,
            tournament_id,
            source="lab",
        )
        report["steps"]["market_row_pick_backfill"] = {
            "dashboard_inserted": dashboard_backfilled,
            "lab_inserted": lab_backfilled,
        }
        print(f"  Backfilled picks: dashboard={dashboard_backfilled}, lab={lab_backfilled}")

    # 5b. Collapse duplicate pick rows (same player/market, different snapshot odds)
    dedupe_result = consolidate_duplicate_picks(tournament_id)
    report["steps"]["pick_dedupe"] = dedupe_result
    if dedupe_result.get("removed"):
        print(f"  Removed {dedupe_result['removed']} duplicate pick row(s); kept {dedupe_result['kept']}")

    # Clear unlocked outcomes so scoring reflects deduped pick rows.
    conn = db.get_conn()
    conn.execute(
        """
        DELETE FROM pick_outcomes
        WHERE COALESCE(outcome_locked, 0) = 0
          AND pick_id IN (SELECT id FROM picks WHERE tournament_id = ?)
        """,
        (tournament_id,),
    )
    conn.commit()
    conn.close()

    # 6. Score picks (respect locked outcomes unless force_audit)
    print("  Scoring picks...")
    from src.learning import score_picks_for_tournament
    if unscored_only and not force_audit:
        score_result = score_picks_for_tournament(tournament_id)
    else:
        score_result = score_picks_for_tournament(
            tournament_id,
            force_audit=force_audit,
            audit_reason=audit_reason,
        )
    report["steps"]["scoring"] = score_result
    print(f"  Scoring: {score_result.get('status', 'done')}")

    # 7. Run full post-tournament learning
    print("  Running post-tournament learning pipeline...")
    from src.learning import post_tournament_learn
    learn_result = post_tournament_learn(
        tournament_id,
        event_id=event_id,
        year=year,
    )
    report["steps"]["learning"] = {
        k: v for k, v in learn_result.get("steps", {}).items()
    }
    report["calibration"] = learn_result.get("calibration", {})

    from src.grading_reconciliation import reconcile_grading

    reconciliation = reconcile_grading(tournament_id=tournament_id)
    report["steps"]["reconciliation"] = reconciliation
    grading_report = build_grading_report(score_result, reconciliation)
    report["grading_report"] = grading_report
    report["status"] = grading_report["status"]

    # 8. Cold archive tournament tables (includes pick_ledger)
    try:
        import os
        import subprocess

        export_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts",
            "export_tournament_archive.py",
        )
        proc = subprocess.run(
            [sys.executable, export_script, "--tournament-id", str(tournament_id)],
            capture_output=True,
            text=True,
            check=False,
        )
        report["steps"]["tournament_archive"] = {
            "ok": proc.returncode == 0,
            "stdout": (proc.stdout or "").strip()[-500:],
            "stderr": (proc.stderr or "").strip()[-500:],
        }
    except Exception as exc:
        report["steps"]["tournament_archive"] = {"ok": False, "error": str(exc)}

    report["status"] = "complete"
    print(f"  Grading complete for tournament {tournament_id} ({report['status']})")
    return report


def main():
    parser = argparse.ArgumentParser(description="Grade a completed PGA tournament")
    parser.add_argument("--event-id", type=str, help="DG event ID")
    parser.add_argument("--event-name", type=str, help="Tournament name (fuzzy match)")
    parser.add_argument("--year", type=int, default=datetime.now().year, help="Year")
    parser.add_argument("--latest", action="store_true", help="Grade the most recent event")
    parser.add_argument(
        "--force-audit",
        action="store_true",
        help="Re-grade locked picks (writes grading_audit_log; requires --audit-reason)",
    )
    parser.add_argument("--audit-reason", type=str, default="", help="Reason for --force-audit")
    parser.add_argument(
        "--allow-backfill-on-locked",
        action="store_true",
        help="Run market-row backfill even when locked outcomes exist",
    )
    args = parser.parse_args()

    db.ensure_initialized()

    if args.latest:
        info = find_latest_completed_event()
        if not info:
            print("Could not determine latest event from DG schedule")
            sys.exit(1)
        event_id = info["event_id"]
        year = info["year"]
        event_name = info.get("event_name")
        print(f"Grading latest event: {event_name} ({event_id}/{year})")
    elif args.event_id:
        event_id = args.event_id
        year = args.year
        event_name = args.event_name
    elif args.event_name:
        t = resolve_tournament(event_name=args.event_name, year=args.year)
        if t:
            event_id = t.get("event_id")
            if not event_id:
                print(f"Tournament found (ID {t['id']}) but no event_id stored. Provide --event-id.")
                sys.exit(1)
            year = args.year
            event_name = t["name"]
        else:
            print(f"No tournament found matching '{args.event_name}' for {args.year}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    print("=" * 50)
    print("  Tournament Grading Pipeline")
    print("=" * 50)

    report = grade_tournament(
        event_id,
        year,
        event_name=event_name,
        force_audit=args.force_audit,
        audit_reason=args.audit_reason or None,
        skip_backfill_if_locked=not args.allow_backfill_on_locked,
    )

    print()
    print("=" * 50)
    if report["status"] == "complete":
        scoring = report["steps"].get("scoring", {})
        print("  Status: COMPLETE")
        print(f"  Picks scored: {scoring.get('scored', 0)}")
        print(f"  Wins: {scoring.get('bet_hits', scoring.get('hits', 0))}")
        print(f"  Losses: {scoring.get('misses', 0)}")
        profit = scoring.get("total_profit", 0)
        print(f"  Profit: {'+' if profit >= 0 else ''}{profit:.2f}u")
    else:
        print(f"  Status: {report['status']}")
        print(f"  Message: {report.get('message', 'Unknown error')}")
    print("=" * 50)


if __name__ == "__main__":
    main()
