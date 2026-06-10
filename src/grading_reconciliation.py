"""Grading reconciliation: prove the grading pipeline actually graded what it showed.

The 2026-05 value-bet audit (`output/audits/value_bet_audit_20260531.md`) found
`pick_outcomes` empty and `prediction_log` regrade mismatches — "monitoring broken,
cannot trust live dashboards". The eval/validity platform is only as trustworthy as
the graded data feeding it, so this module gives a committed, testable check that:

1. every event that has results graded its displayed +EV picks (no silently ungraded
   +EV picks once an event has completed), and
2. there are no orphan `pick_outcomes` rows pointing at deleted picks.

Per the +EV-only grading trust contract, only picks with ``ev > 0`` are expected to be
graded; non-positive-EV lines live in diagnostics and are intentionally never graded.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _conn(conn: sqlite3.Connection | None) -> tuple[sqlite3.Connection, bool]:
    if conn is not None:
        return conn, False
    from src import db

    db.ensure_initialized()
    return db.get_conn(), True


def reconcile_grading(
    conn: sqlite3.Connection | None = None,
    *,
    source: str | None = None,
    limit_events: int | None = None,
) -> dict[str, Any]:
    """Reconcile displayed +EV picks against graded outcomes per event.

    Args:
        conn: optional open connection (test injection).
        source: optional pick-source filter (e.g. ``"cockpit"``, ``"lab_sandbox"``).
        limit_events: cap the number of most-recent events inspected.

    Returns a dict with overall ``status`` (``ok`` | ``discrepancies``), per-event rows,
    and orphan-outcome count.
    """
    connection, close = _conn(conn)
    try:
        source_clause = ""
        params: list[Any] = []
        if source:
            source_clause = " AND p.source = ?"
            params.append(source)

        # Per-event +EV pick counts vs graded counts, only for events that have results.
        rows = connection.execute(
            f"""
            SELECT
                t.id AS tournament_id,
                t.name AS tournament_name,
                t.year AS tournament_year,
                (SELECT COUNT(*) FROM results r WHERE r.tournament_id = t.id) AS results_count,
                (SELECT COUNT(*) FROM picks p
                   WHERE p.tournament_id = t.id AND p.ev > 0{source_clause}) AS positive_ev_picks,
                (SELECT COUNT(*) FROM picks p
                   JOIN pick_outcomes po ON po.pick_id = p.id
                   WHERE p.tournament_id = t.id AND p.ev > 0{source_clause}) AS graded_positive_ev_picks
            FROM tournaments t
            ORDER BY t.id DESC
            """,
            params * 2,
        ).fetchall()

        event_reports: list[dict[str, Any]] = []
        events_with_ungraded = 0
        for row in rows:
            results_count = row["results_count"] or 0
            positive_ev = row["positive_ev_picks"] or 0
            graded = row["graded_positive_ev_picks"] or 0
            # Only events that have completed (results present) AND showed +EV picks can be
            # "ungraded". Pre-results events are legitimately ungraded.
            ungraded = max(0, positive_ev - graded) if results_count > 0 else 0
            has_discrepancy = results_count > 0 and positive_ev > 0 and graded < positive_ev
            if has_discrepancy:
                events_with_ungraded += 1
            event_reports.append({
                "tournament_id": row["tournament_id"],
                "tournament_name": row["tournament_name"],
                "tournament_year": row["tournament_year"],
                "results_count": results_count,
                "positive_ev_picks": positive_ev,
                "graded_positive_ev_picks": graded,
                "ungraded_positive_ev_picks": ungraded,
                "has_discrepancy": has_discrepancy,
            })

        # Surface events with discrepancies first; honor limit.
        event_reports.sort(key=lambda e: (not e["has_discrepancy"], -(e["tournament_id"] or 0)))
        if limit_events is not None:
            event_reports = event_reports[: int(limit_events)]

        orphan_outcomes = connection.execute(
            """
            SELECT COUNT(*) FROM pick_outcomes po
            LEFT JOIN picks p ON p.id = po.pick_id
            WHERE p.id IS NULL
            """,
        ).fetchone()[0]

        status = "ok" if (events_with_ungraded == 0 and orphan_outcomes == 0) else "discrepancies"
        return {
            "status": status,
            "source": source or "all",
            "events_with_ungraded_positive_ev": events_with_ungraded,
            "orphan_outcomes": orphan_outcomes,
            "events": event_reports,
        }
    finally:
        if close:
            connection.close()


def render_markdown(report: dict[str, Any]) -> str:
    """Render a reconciliation report dict as a committable markdown summary."""
    lines = [
        "# Grading reconciliation report",
        "",
        f"- **Status:** {report['status']}",
        f"- **Pick source:** {report['source']}",
        f"- **Events with ungraded +EV picks (post-results):** {report['events_with_ungraded_positive_ev']}",
        f"- **Orphan pick_outcomes rows:** {report['orphan_outcomes']}",
        "",
        "| Event | Year | Results | +EV picks | Graded | Ungraded | OK |",
        "|-------|------|---------|-----------|--------|----------|----|",
    ]
    for e in report["events"]:
        lines.append(
            f"| {e['tournament_name']} | {e['tournament_year']} | {e['results_count']} | "
            f"{e['positive_ev_picks']} | {e['graded_positive_ev_picks']} | "
            f"{e['ungraded_positive_ev_picks']} | {'—' if e['has_discrepancy'] else 'ok'} |"
        )
    lines.append("")
    return "\n".join(lines)
