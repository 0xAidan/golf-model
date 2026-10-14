"""Read-only, non-predictive evidence from preserved pick/outcome records.

This module intentionally imports neither ``src.db`` nor any model module.
Opening a report must never initialize/migrate the source database. The source
connection honors SQLite WAL; ``immutable=1`` must not be used on a live database.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import time
from typing import Any


MARKETS = {
    "72h": "72-hole matchups",
    "18h": "18-hole matchups",
    "group": "Group & three-ball",
    "other": "Other & unspecified",
}
MIN_RECORDS = 30
MIN_EVENTS = 5
_LANES = {
    "cockpit": "dashboard", "ui_display": "dashboard", "dashboard": "dashboard",
    "lab": "lab", "lab_sandbox": "lab", "lab_sandbox_candidate": "lab", "ui_candidate": "lab",
}
_CAVEATS = [
    "Stored model picks are a paper record; actual wager placement is unknown.",
    "Coverage describes this database only. Full-season completeness is not established.",
    "Existing outcomes and profit are read as stored; this report does not regrade history.",
    "Repeated identical records count once; conflicting repeats are excluded from performance metrics.",
    "Small samples and correlated picks are not evidence of a durable profitable edge.",
    "This report cannot change predictions, weights, calibration, selection, or model promotion.",
]


def default_database_path() -> Path:
    """Resolve explicit deployment paths without importing auto-migrating helpers."""
    if os.environ.get("GOLF_DB_PATH", "").strip():
        return Path(os.environ["GOLF_DB_PATH"]).expanduser().absolute()
    if os.environ.get("GOLF_DATA_DIR", "").strip():
        return Path(os.environ["GOLF_DATA_DIR"]).expanduser().absolute() / "golf.db"
    return Path(__file__).resolve().parents[1] / "data" / "golf.db"


def _number(value: Any) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number is not None and math.isfinite(number) else None


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _market(row: dict) -> str:
    kind = _token(row.get("market_type") or row.get("bet_type"))
    if any(part in kind for part in ("group", "3ball", "3_ball", "three_ball", "threeball")):
        return "group"
    if any(part in kind for part in ("round_matchup", "18_hole", "18h")) or re.search(r"(?:^|_)r[1-4](?:_|$)", kind):
        return "18h"
    if "matchup" in kind and re.search(r"round_?[1-4]", kind):
        return "18h"
    if any(part in kind for part in ("tournament_matchup", "72_hole", "72h")):
        return "72h"
    # A legacy 'matchup' without duration evidence must not become a 72-hole claim.
    return "other"


def _round(row: dict) -> str:
    explicit = row.get("round_num") or row.get("round_number")
    if explicit is not None:
        return str(explicit)
    match = re.search(r"(?:^|_)(?:round_?|r)([1-4])(?:_|$)", _token(row.get("market_type")))
    return match.group(1) if match else ""


def _season(row: dict) -> str:
    year = row.get("year")
    if year is not None:
        return str(year)
    date = str(row.get("event_date") or "")
    return date[:4] if re.match(r"^\d{4}-\d{2}-\d{2}", date) else ""


def _event_key(row: dict) -> tuple:
    # Internal ID is retained alongside vendor ID so reused event IDs cannot
    # merge seasons/tours or distinct tournament records.
    return (_season(row), row.get("tournament_id"), str(row.get("event_id") or ""))


def _identity(row: dict) -> tuple:
    market = _market(row)
    round_key = _round(row)
    if market == "18h" and not round_key:
        # Duration alone does not establish which round this prediction covers.
        round_key = f"missing-round:{row['pick_id']}"
    group_key = str(row.get("group_id") or row.get("market_id") or row.get("opponent_key") or "")
    if market == "group" and not group_key:
        group_key = f"missing-group:{row['pick_id']}"
    return (
        *_event_key(row), str(row.get("source") or ""), str(row.get("model_variant") or ""),
        _token(row.get("bet_type")), _token(row.get("market_type")), round_key,
        group_key, str(row.get("market_id") or ""),
        str(row.get("player_key") or f"missing-player:{row['pick_id']}"),
        str(row.get("opponent_key") or ""), _token(row.get("market_book")),
    )


def _outcome(row: dict) -> str:
    if row.get("conflicting_record"):
        return "unknown"
    if row.get("outcome_id") is None:
        return "ungraded"
    authority = _token(row.get("grading_authority"))
    recorded = _token(row.get("outcome") or row.get("result") or row.get("actual_finish"))
    if authority == "void" or recorded in {"void", "cancelled", "canceled", "no_action", "v"}:
        return "void"
    if recorded in {"push", "p", "refund", "refunded"}:
        return "push"
    if recorded in {"win", "won", "w"}:
        return "win"
    if recorded in {"loss", "lost", "lose", "l"}:
        return "loss"
    hit, profit = _number(row.get("hit")), _number(row.get("profit"))
    if hit == 1:
        return "win"
    if hit == 0 and profit == 0:
        return "push"
    if hit == 0 and profit is not None and profit < 0:
        return "loss"
    return "unknown"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    # Names here are fixed code constants, never request parameters.
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")')}


def _load_rows(conn: sqlite3.Connection) -> list[dict]:
    cols = {table: _columns(conn, table) for table in ("picks", "pick_outcomes", "tournaments")}
    required = {"picks": {"id", "tournament_id"}, "pick_outcomes": {"id", "pick_id"}, "tournaments": {"id"}}
    if any(not names.issubset(cols[table]) for table, names in required.items()):
        raise ValueError("Required picks, pick_outcomes, or tournaments schema is unavailable.")

    def field(table: str, alias: str, name: str, output: str | None = None) -> str:
        expression = f'{alias}."{name}"' if name in cols[table] else "NULL"
        return f'{expression} AS "{output or name}"'

    selected = [field("picks", "p", "id", "pick_id")]
    selected += [field("picks", "p", name) for name in (
        "tournament_id", "source", "model_variant", "bet_type", "market_type", "player_key",
        "opponent_key", "market_book", "market_odds", "model_prob", "created_at", "round_num",
        "round_number", "group_id", "market_id",
    )]
    selected += [field("tournaments", "t", name, output) for name, output in (
        ("year", "year"), ("event_id", "event_id"), ("date", "event_date"), ("name", "event_name"),
    )]
    selected += [field("pick_outcomes", "po", "id", "outcome_id")]
    selected += [field("pick_outcomes", "po", name) for name in (
        "hit", "profit", "stake", "actual_finish", "grading_authority", "outcome_locked",
        "outcome", "result", "entered_at",
    )]
    query = f"""SELECT {', '.join(selected)}
                FROM picks p LEFT JOIN tournaments t ON t.id = p.tournament_id
                LEFT JOIN pick_outcomes po ON po.pick_id = p.id
                ORDER BY p.id, po.id"""
    return [dict(r) for r in conn.execute(query)]


def _project_records(rows: list[dict]) -> tuple[list[dict], int, int]:
    """Collapse exact repeat evidence only; never select a winning/late quote."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[_identity(row)].append(row)
    result = []
    conflicting = 0
    duplicate_picks = 0
    fields = ("market_odds", "model_prob", "hit", "profit", "stake", "actual_finish", "grading_authority", "outcome", "result")
    for group in groups.values():
        row = dict(group[0])
        duplicate_picks += max(0, len({r["pick_id"] for r in group}) - 1)
        signatures = {tuple(r.get(f) for f in fields) + (r.get("outcome_id") is not None,) for r in group}
        # Multiple outcomes for the same pick are ambiguous even if identical.
        outcomes_per_pick: dict[Any, set[Any]] = defaultdict(set)
        for original in group:
            if original.get("outcome_id") is not None:
                outcomes_per_pick[original["pick_id"]].add(original["outcome_id"])
        row["conflicting_record"] = len(signatures) > 1 or any(len(ids) > 1 for ids in outcomes_per_pick.values())
        conflicting += int(row["conflicting_record"])
        row["settlement"] = _outcome(row)
        row["market"] = _market(row)
        row["lane"] = _LANES.get(_token(row.get("source")), "other")
        result.append(row)
    return result, duplicate_picks, conflicting


def _calibration(rows: list[dict]) -> dict:
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        p, hit = _number(row.get("model_prob")), _number(row.get("hit"))
        result = _token(row.get("outcome") or row.get("result") or row.get("actual_finish"))
        if row["settlement"] not in {"win", "loss"} or p is None or not 0 <= p <= 1 or hit not in {0, 1}:
            continue
        if (row["settlement"] == "win") != (hit == 1) or "dead_heat" in result or result == "tie":
            continue
        buckets[min(9, int(p * 10))].append((p, hit))
    pairs = [pair for bucket in buckets.values() for pair in bucket]
    return {
        "n": len(pairs),
        "brier": round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 6) if pairs else None,
        "bins": [
            {
                "lower": i / 10, "upper": (i + 1) / 10, "n": len(bucket),
                "mean_probability": round(sum(p for p, _ in bucket) / len(bucket), 4),
                "observed_rate": round(sum(y for _, y in bucket) / len(bucket), 4),
            }
            for i, bucket in sorted(buckets.items())
        ],
        "note": "Binary win/loss records only; pushes, voids, conflicts and invalid probabilities are excluded.",
    }


def _aggregate(rows: list[dict]) -> dict:
    counts = Counter(row["settlement"] for row in rows)
    settled = [row for row in rows if row["settlement"] in {"win", "loss", "push", "void"}]
    with_profit = [row for row in settled if _number(row.get("profit")) is not None]
    # Void profit is preserved in net units but a void is not a wager at risk.
    roi_rows = [row for row in settled if row["settlement"] != "void"]
    complete_stakes = bool(roi_rows) and all(
        _number(row.get("profit")) is not None and (_number(row.get("stake")) or 0) > 0
        for row in roi_rows
    )
    net = sum(float(row["profit"]) for row in with_profit) if with_profit else None
    flat_roi = (
        100 * sum(float(row["profit"]) / float(row["stake"]) for row in roi_rows) / len(roi_rows)
        if complete_stakes else None
    )
    stake = sum(float(row["stake"]) for row in roi_rows) if complete_stakes else None
    events = {_event_key(row) for row in rows}
    settled_events = {_event_key(row) for row in roi_rows}
    binary_n = counts["win"] + counts["loss"]
    reasons = []
    if binary_n < MIN_RECORDS:
        reasons.append(f"Fewer than {MIN_RECORDS} binary settled records.")
    if len(settled_events) < MIN_EVENTS:
        reasons.append(f"Fewer than {MIN_EVENTS} events with settled records.")
    if not complete_stakes:
        reasons.append("Complete stored profit and positive stake are unavailable for every eligible settled record.")
    return {
        "records": len(rows), "event_count": len(events), "graded": len(settled),
        "wins": counts["win"], "losses": counts["loss"], "pushes": counts["push"],
        "voids": counts["void"], "unknown": counts["unknown"], "ungraded": counts["ungraded"],
        "net_units": round(net, 4) if net is not None else None,
        "profit_covered_records": len(with_profit), "profit_missing_records": len(settled) - len(with_profit),
        "profit_coverage_complete": bool(settled) and len(with_profit) == len(settled),
        "known_stake_units": round(stake, 4) if stake is not None else None,
        "flat_unit_roi_pct": round(flat_roi, 3) if flat_roi is not None else None,
        "roi_basis": "Stored profit divided by stored positive stake per record; voids excluded.",
        "binary_hit_rate_pct": round(100 * counts["win"] / binary_n, 2) if binary_n else None,
        "low_sample": binary_n < MIN_RECORDS or len(settled_events) < MIN_EVENTS,
        "evidence_state": "insufficient" if reasons else "descriptive_only",
        "limitations": reasons, "calibration": _calibration(rows),
    }


def _range(rows: list[dict], field: str) -> tuple[str | None, str | None]:
    values = [str(row[field]) for row in rows if row.get(field)]
    return (min(values), max(values)) if values else (None, None)


def _base_report(lane: str, season: int | None) -> dict:
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "state": "unavailable", "reason": None, "filters": {"lane": lane, "season": season},
        "provenance": {
            "data_kind": "stored_model_pick_record", "actual_wager_status": "unknown",
            "read_only": True, "model_changes": False, "history_changes": False,
            "full_season_verified": False, "clv_status": "not_evaluated",
        },
        "coverage": {
            "raw_pick_records": 0, "raw_outcome_records": 0, "record_count": 0, "event_count": 0,
            "first_event_date": None, "last_event_date": None,
            "first_prediction_at": None, "last_prediction_at": None,
            "first_grade_at": None, "last_grade_at": None,
            "duplicate_pick_records": 0, "conflicting_identities": 0,
        },
        "summary": _aggregate([]), "markets": [], "lanes": [], "gaps": [],
        "caveats": list(_CAVEATS),
    }


def build_market_evidence(
    database_path: str | Path | None = None, *, lane: str = "dashboard", season: int | None = None,
) -> dict:
    """Produce one consistent read transaction. Never creates or migrates a DB."""
    if lane not in {"dashboard", "lab", "all"}:
        raise ValueError("lane must be dashboard, lab, or all")
    report = _base_report(lane, season)
    path = Path(database_path) if database_path is not None else default_database_path()
    if not path.is_file():
        report["reason"] = "Source database is unavailable. No database was created."
        return report
    conn = None
    try:
        # mode=ro prevents file mutation; query_only additionally blocks SQL DDL/DML.
        # Do not use immutable=1: it ignores live WAL records.
        conn = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True, timeout=2.5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        started = time.monotonic()
        conn.set_progress_handler(lambda: int(time.monotonic() - started > 8.0), 10000)
        conn.execute("BEGIN")
        all_rows = _load_rows(conn)
        table_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        supporting = {}
        for table in ("historical_matchup_odds", "research_backtest_lines"):
            supporting[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) if table in table_names else None
        conn.rollback()
    except (sqlite3.Error, ValueError, OSError) as exc:
        # Expose a usable distinction without leaking paths or opaque SQL to the UI.
        report["reason"] = "Required source schema is unavailable." if isinstance(exc, ValueError) else "Source database could not be read consistently."
        report["gaps"].append({"code": "source_unavailable", "status": "unavailable", "detail": report["reason"]})
        return report
    finally:
        if conn is not None:
            conn.close()

    scoped = [row for row in all_rows if season is None or _season(row) == str(season)]
    if lane != "all":
        scoped = [row for row in scoped if _LANES.get(_token(row.get("source")), "other") == lane]
    records, duplicates, conflicts = _project_records(scoped)
    first_event, last_event = _range(scoped, "event_date")
    first_prediction, last_prediction = _range(scoped, "created_at")
    first_grade, last_grade = _range(scoped, "entered_at")
    report.update({
        "state": "available" if records else "empty",
        "reason": None if records else "No stored pick records match these filters.",
        "coverage": {
            "raw_pick_records": len({row["pick_id"] for row in scoped}),
            "raw_outcome_records": len({row["outcome_id"] for row in scoped if row["outcome_id"] is not None}),
            "record_count": len(records), "event_count": len({_event_key(row) for row in records}),
            "first_event_date": first_event, "last_event_date": last_event,
            "first_prediction_at": first_prediction, "last_prediction_at": last_prediction,
            "first_grade_at": first_grade, "last_grade_at": last_grade,
            "duplicate_pick_records": duplicates, "conflicting_identities": conflicts,
            "records_missing_market_duration": sum(row["market"] == "other" and _token(row.get("bet_type")) == "matchup" for row in records),
            "round_records_missing_round": sum(row["market"] == "18h" and not _round(row) for row in records),
            "group_records_missing_identity": sum(row["market"] == "group" and not (row.get("group_id") or row.get("market_id") or row.get("opponent_key")) for row in records),
            "records_missing_season": sum(not _season(row) for row in records),
        },
        "summary": _aggregate(records),
        "markets": [
            {
                "key": key, "label": label, **_aggregate([r for r in records if r["market"] == key]),
                "market_types": dict(Counter(str(r.get("market_type") or r.get("bet_type") or "unknown") for r in records if r["market"] == key)),
            }
            for key, label in MARKETS.items()
        ],
        "lanes": [
            {"key": key, **_aggregate([r for r in records if r["lane"] == key])}
            for key in ("dashboard", "lab", "other")
        ],
    })
    report["gaps"] = [
        {
            "code": table, "status": "missing" if count is None else "empty" if count == 0 else "present",
            "row_count": count, "scope": "whole_database",
            "detail": "Availability only; rows are not validated or used as live performance evidence.",
        }
        for table, count in supporting.items()
    ]
    report["gaps"].append({
        "code": "closing_line_value", "status": "not_evaluated",
        "detail": "Requires matched event, season, market duration, round/group, book and pre-start timestamp. Existing CLV rows are not treated as independent bets.",
    })
    if conflicts:
        report["gaps"].append({"code": "conflicting_records", "status": "needs_review", "count": conflicts,
                               "detail": "Conflicting repeated picks or multiple outcomes were excluded from performance and calibration."})
    return report


def write_report(report: dict, output: str | Path) -> Path:
    """Append a report artifact by creating a new file exclusively; never overwrite."""
    target = Path(output)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Source SQLite database; opened read-only, with WAL honored.")
    parser.add_argument("--out", required=True, type=Path, help="New unique JSON file; existing files are rejected.")
    parser.add_argument("--lane", choices=("dashboard", "lab", "all"), default="dashboard")
    parser.add_argument("--season", type=int)
    args = parser.parse_args()
    report = build_market_evidence(args.db, lane=args.lane, season=args.season)
    write_report(report, args.out)
    print(f"{report['state']}: {args.out}")


if __name__ == "__main__":
    main()
