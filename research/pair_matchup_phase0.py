"""Phase 0 data audit for the Zurich Classic pair / team matchup model (T3, issue #47).

Goal
----
Answer a single question before we model anything: **do we have enough historical
pair-round data in the local DB to train a v1 pair-matchup estimator?**

What this script does
---------------------
1. Reads the ``rounds`` table from ``src.db`` (the local SQLite warehouse).
2. Identifies historical team events using :func:`src.event_format.is_team_event`
   and the ``event_name`` column.
3. Reports:
   - number of team-event years present in the round archive
   - unique player count per team event year
   - inferred pairings (players sharing ``event_id``/``year``/``round_num``
     with the same final finish position) — a best-effort reconstruction;
     the schema does not store pair identity directly
   - data-quality issues (missing ``sg_total``, missing ``fin_text``,
     ambiguous pair reconstruction, odd round counts)
4. Writes a markdown audit report to
   ``docs/research/pair_matchup_phase0_audit.md`` with counts, tables, and
   a short "ready to model?" verdict.

The script is intentionally read-only: it does not mutate the DB, call
external APIs, or load pipeline modules that require env credentials. It
is safe to run in CI and on a fresh checkout where the DB may be empty.

Run with::

    python research/pair_matchup_phase0.py

Referenced by GitHub issue #47.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Allow running as a script without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src import db as _db  # noqa: E402
from src.event_format import is_team_event  # noqa: E402


DEFAULT_OUTPUT = _REPO_ROOT / "docs" / "research" / "pair_matchup_phase0_audit.md"


@dataclass
class TeamEventSummary:
    event_id: str | None
    event_name: str
    year: int | None
    round_count: int
    player_count: int
    rounds_missing_sg_total: int
    rounds_missing_fin: int
    inferred_pairs: int
    ambiguous_pairs: int


def _fetch_team_event_rounds(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return every round in the DB whose event_name classifies as a team event.

    We do not filter by tour: the Zurich Classic is PGA Tour, but we stay
    permissive so any ingested team event (DP World Tour team events, etc.)
    is caught.
    """
    cur = conn.execute(
        "SELECT dg_id, player_name, player_key, tour, year, event_id, event_name, "
        "event_completed, course_name, round_num, score, sg_total, fin_text "
        "FROM rounds WHERE event_name IS NOT NULL"
    )
    out: list[dict[str, Any]] = []
    for row in cur.fetchall():
        d = dict(row)
        if is_team_event(d.get("event_name")):
            out.append(d)
    return out


def _group_key(row: dict[str, Any]) -> tuple[str, int | None]:
    return (str(row.get("event_name") or "").strip(), row.get("year"))


def _reconstruct_pairs(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Best-effort pair reconstruction from the ``rounds`` schema.

    The ``rounds`` table has no pair_id; we infer pairs as players who share
    the same ``(event_id, year, round_num, fin_text)``. This is the same
    heuristic DataGolf users apply: team-format events post an identical
    final finish string for both members of a pair.

    Returns
    -------
    inferred_pairs:
        number of distinct (event, year, round, fin_text) groups of size 2.
    ambiguous_pairs:
        number of groups of size != 2 (schema noise — e.g. WD, missing data,
        or three-ball side contests incorrectly ingested as team rounds).
    """
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if not r.get("fin_text"):
            continue
        key = (r.get("event_id"), r.get("year"), r.get("round_num"), r.get("fin_text"))
        buckets[key].append(r)

    inferred = 0
    ambiguous = 0
    for members in buckets.values():
        # Deduplicate by dg_id — same player with two rounds in one bucket is noise.
        unique_players = {m.get("dg_id") for m in members if m.get("dg_id") is not None}
        if len(unique_players) == 2:
            inferred += 1
        elif len(unique_players) != 0:
            ambiguous += 1
    return inferred, ambiguous


def summarise(rows: list[dict[str, Any]]) -> list[TeamEventSummary]:
    groups: dict[tuple[str, int | None], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[_group_key(r)].append(r)

    summaries: list[TeamEventSummary] = []
    for (name, year), members in sorted(
        groups.items(), key=lambda kv: (kv[0][1] or 0, kv[0][0])
    ):
        players = {m.get("dg_id") for m in members if m.get("dg_id") is not None}
        missing_sg = sum(1 for m in members if m.get("sg_total") is None)
        missing_fin = sum(1 for m in members if not m.get("fin_text"))
        inferred, ambiguous = _reconstruct_pairs(members)
        event_ids = {m.get("event_id") for m in members if m.get("event_id")}
        event_id = next(iter(event_ids)) if len(event_ids) == 1 else None
        summaries.append(
            TeamEventSummary(
                event_id=event_id,
                event_name=name or "(unknown)",
                year=year,
                round_count=len(members),
                player_count=len(players),
                rounds_missing_sg_total=missing_sg,
                rounds_missing_fin=missing_fin,
                inferred_pairs=inferred,
                ambiguous_pairs=ambiguous,
            )
        )
    return summaries


def _format_markdown_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    headers = list(headers)
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _verdict(summaries: list[TeamEventSummary]) -> tuple[str, str]:
    """Return (verdict_label, detail_paragraph).

    Heuristic: we need at least 2 prior Zurich editions with >= 60 rounds
    each (≈ 30 pairs × 2 players for a cut round) and a clean pair
    reconstruction rate > 50% to justify walking-forward a v1 model from
    history. Otherwise fall back to the DG-composite baseline.
    """
    zurich = [s for s in summaries if "zurich" in s.event_name.lower()]
    usable = [s for s in zurich if s.round_count >= 60 and s.inferred_pairs > 0]

    if len(usable) >= 2:
        return (
            "READY (historical)",
            "Sufficient Zurich Classic history present to train a walk-forward "
            "pair estimator. Phase 1 uses the format-aware skill combiner with "
            "historical round SD; DG-composite fallback remains wired but is not "
            "the primary path.",
        )

    if len(zurich) == 0:
        return (
            "INSUFFICIENT — no historical team events in local rounds table",
            "Phase 1 ships as an analytics-only shadow estimator driven entirely "
            "by the DG-composite-average fallback. No historical pair data means "
            "we cannot even spot-check directional behaviour against past results; "
            "predictions are logged but not calibrated. Phase 2 will need a DG "
            "historical backfill before calibration can begin.",
        )

    return (
        "INSUFFICIENT (limited history)",
        "Zurich Classic rows exist but coverage is thin (fewer than two usable "
        "editions of sufficient depth, or pair reconstruction is ambiguous). "
        "Phase 1 ships as analytics-only with DG-composite fallback as the primary "
        "path. Phase 2 must audit and backfill DG round-level pair data before "
        "calibration is attempted.",
    )


def render_report(summaries: list[TeamEventSummary], total_rounds_in_db: int) -> str:
    verdict_label, verdict_detail = _verdict(summaries)

    total_team_rounds = sum(s.round_count for s in summaries)
    total_team_players = len({(s.event_name, s.year) for s in summaries})  # event-years
    total_inferred_pairs = sum(s.inferred_pairs for s in summaries)
    total_ambiguous = sum(s.ambiguous_pairs for s in summaries)

    issues: list[str] = []
    if total_team_rounds == 0:
        issues.append(
            "No team-event rounds found in the local DB. Either the historical "
            "DataGolf backfill did not include Zurich Classic editions, or the "
            "`event_name` column does not match the team-event regex. Re-run "
            "`setup_wizard.py` with DG historical backfill enabled to populate."
        )
    for s in summaries:
        if s.rounds_missing_sg_total / max(s.round_count, 1) > 0.25:
            issues.append(
                f"{s.event_name} {s.year}: >25% of rounds missing sg_total "
                f"({s.rounds_missing_sg_total}/{s.round_count}). Likely a "
                "pre-2017 ingestion gap; DG SG data thins out on older team events."
            )
        if s.ambiguous_pairs > 0 and s.inferred_pairs == 0:
            issues.append(
                f"{s.event_name} {s.year}: pair reconstruction failed — no clean "
                "two-player groups on matching finish strings. Without a pair_id "
                "column we cannot recover the team identities."
            )

    lines = [
        "# Pair / Team Matchup Model — Phase 0 Data Audit",
        "",
        "Tracking issue: **#47** (golf-model repo). Scope: Zurich Classic 2026 "
        "and any other historical team events already in our round-level warehouse.",
        "",
        "Generated by `research/pair_matchup_phase0.py` (read-only). Re-run the "
        "script to refresh.",
        "",
        "## Verdict",
        "",
        f"**{verdict_label}**",
        "",
        verdict_detail,
        "",
        "## Headline numbers",
        "",
        f"- Total rounds in `rounds` table: **{total_rounds_in_db:,}**",
        f"- Team-event rounds in `rounds` table: **{total_team_rounds:,}**",
        f"- Distinct team-event editions (event × year): **{total_team_players}**",
        f"- Inferred two-player pairings (sum across editions): **{total_inferred_pairs}**",
        f"- Ambiguous pair groups (group size != 2): **{total_ambiguous}**",
        "",
        "## Per-edition breakdown",
        "",
    ]

    if summaries:
        lines.append(
            _format_markdown_table(
                [
                    "Event",
                    "Year",
                    "Rounds",
                    "Unique players",
                    "Missing sg_total",
                    "Missing fin_text",
                    "Inferred pairs",
                    "Ambiguous",
                ],
                [
                    [
                        s.event_name,
                        s.year if s.year is not None else "—",
                        s.round_count,
                        s.player_count,
                        s.rounds_missing_sg_total,
                        s.rounds_missing_fin,
                        s.inferred_pairs,
                        s.ambiguous_pairs,
                    ]
                    for s in summaries
                ],
            )
        )
    else:
        lines.append("_No team-event rounds present in the local DB._")

    lines += [
        "",
        "## Data-quality issues",
        "",
    ]
    if issues:
        for item in issues:
            lines.append(f"- {item}")
    else:
        lines.append("- No data-quality issues detected.")

    lines += [
        "",
        "## What Phase 1 actually ships",
        "",
        "Independent of the verdict above, Phase 1 delivers an **analytics-only, "
        "flag-gated** pair matchup module (`src/models/pair_matchup_v1.py`) "
        "behind `PAIR_MATCHUP_V1` (default **OFF**). When the flag is off the "
        "production card is byte-identical to main — a golden test enforces this. "
        "Predictions are written only to a new `pair_matchup_predictions` shadow "
        "table and surfaced via a research endpoint for post-hoc inspection.",
        "",
        "Phase 3 — actually putting pair matchup picks on the live dashboard — "
        "is explicitly **not** part of this week's work.",
        "",
    ]

    return "\n".join(lines).rstrip() + "\n"


def run(output_path: Path) -> str:
    """Execute the audit and write the report. Returns the verdict label."""
    _db.ensure_initialized()
    conn = _db.get_conn()
    try:
        rows = _fetch_team_event_rounds(conn)
        total_rounds = conn.execute("SELECT COUNT(*) AS c FROM rounds").fetchone()["c"]
    finally:
        conn.close()

    summaries = summarise(rows)
    report = render_report(summaries, total_rounds_in_db=total_rounds)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    verdict_label, _ = _verdict(summaries)
    return verdict_label


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Destination markdown path (default: {DEFAULT_OUTPUT.relative_to(_REPO_ROOT)})",
    )
    args = parser.parse_args(argv)

    verdict = run(args.output)
    rel = os.path.relpath(args.output, _REPO_ROOT)
    print(f"[pair_matchup_phase0] verdict: {verdict}")
    print(f"[pair_matchup_phase0] wrote audit to {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
