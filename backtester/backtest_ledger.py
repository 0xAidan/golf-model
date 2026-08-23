"""Backtest-grade matchup line/outcome ledger derived from the operator's own capture.

Data Golf's historical matchup-odds archive has never populated (0 rows) and its
stored ``historical_odds`` are synthetic DG-model prices. What IS backtest-grade
is our own continuous capture: ``market_prediction_rows`` holds every-book
pre-tournament matchup lines since 2026-06-14, and graded outcomes exist in
``picks``/``pick_outcomes`` plus finish texts in ``rounds``.

This builder derives one row per (event, market_type, player, opponent, book):
the captured American odds with first/last capture timestamps, joined with the
graded outcome when available. It is IDEMPOTENT (INSERT OR IGNORE + refresh of
mutable fields) and safe to run weekly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src import db

logger = logging.getLogger("backtester.backtest_ledger")

# Sections that represent pre-tournament captures (pre-tee lines).
PRE_EVENT_SECTIONS = ("upcoming", "lab_upcoming")
MARKET_FAMILY = "matchup"

OUTCOME_WIN = "win"
OUTCOME_LOSS = "loss"
OUTCOME_PUSH = "push"
OUTCOME_VOID = "void"


@dataclass(frozen=True)
class LedgerBuildStats:
    events_seen: int
    rows_inserted: int
    rows_refreshed: int
    outcomes_set: int


def _parse_american(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("+", "")
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"even", "ev", "pk", "pick", "pickem"}:
        return "+100"
    try:
        price = int(float(text))
    except (TypeError, ValueError):
        return None
    if price == 0 or abs(price) > 100000:
        return None
    return f"+{price}" if price > 0 else str(price)


def _resolve_market_type(market_type_raw: Any) -> str:
    text = str(market_type_raw or "").lower()
    return "round_matchups" if "round" in text else "tournament_matchups"


def american_to_implied(odds_american: str) -> float | None:
    try:
        price = int(odds_american)
    except (TypeError, ValueError):
        return None
    if price == 0:
        return None
    if price > 0:
        return round(100.0 / (price + 100.0), 6)
    return round(abs(price) / (abs(price) + 100.0), 6)


def build_research_backtest_lines(
    *,
    event_id: str | None = None,
    year: int | None = None,
    batch_size: int = 2000,
    progress=None,
) -> LedgerBuildStats:
    """
    Derive pre-tournament book lines (+ outcomes where graded) into
    research_backtest_lines. Idempotent: reruns only refresh timestamps and
    fill newly available outcomes.
    """
    from src.db import ensure_initialized

    ensure_initialized()
    conn = db.get_conn()

    where = ["m.market_family = ?", "m.section IN (?, ?)", "m.event_id IS NOT NULL",
             "m.odds IS NOT NULL AND m.odds != ''"]
    params: list[Any] = [MARKET_FAMILY, *PRE_EVENT_SECTIONS]
    if event_id is not None:
        where.append("m.event_id = ?")
        params.append(str(event_id))

    # Single ordered scan: earliest capture per (event, pair, book) supplies the
    # opening line; Python-side dict keeps one row per key. json_extract recovers
    # player/opponent for rows whose denormalized columns were left empty.
    query = f"""
        SELECT m.event_id,
               COALESCE(NULLIF(m.player_key, ''),
                        LOWER(REPLACE(REPLACE(json_extract(m.payload_json, '$.pick'), '.', ''), ' ', '_'))) AS pkey,
               COALESCE(NULLIF(m.opponent_key, ''),
                        LOWER(REPLACE(REPLACE(json_extract(m.payload_json, '$.opponent'), '.', ''), ' ', '_'))) AS okey,
               m.book,
               m.generated_at,
               m.market_type,
               m.odds
        FROM market_prediction_rows m
        WHERE {' AND '.join(where)}
        ORDER BY m.event_id, pkey, okey, m.book, m.generated_at ASC
    """

    stats = {"events": set(), "inserted": 0, "refreshed": 0, "outcomes": 0}

    # Accumulate per key: first line, last ts, capture count, market type.
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    year_by_event: dict[str, int] = {}
    cursor = conn.execute(query, params)
    for row in cursor:
        ev_id, pkey, okey, book, generated_at, market_type_raw, odds_raw = row
        if not pkey or not okey or not book:
            continue
        ev_key = str(ev_id)
        if ev_key not in year_by_event:
            trow = conn.execute(
                "SELECT MAX(year) FROM tournaments WHERE event_id = ?", (ev_key,)
            ).fetchone()
            year_by_event[ev_key] = int(trow[0] or (year if year is not None else 2026))
        key = (ev_key, str(pkey), str(okey), str(book))
        entry = grouped.get(key)
        if entry is None:
            parsed_odds = _parse_american(odds_raw)
            if parsed_odds is None:
                continue
            entry = {
                "first": generated_at,
                "last": generated_at,
                "count": 1,
                "odds_american": parsed_odds,
                "market_type": _resolve_market_type(market_type_raw),
            }
            grouped[key] = entry
        else:
            entry["last"] = generated_at
            entry["count"] += 1

    pending: list[tuple] = []
    for (ev_key, pkey, okey, book), entry in grouped.items():
        stats["events"].add(ev_key)
        pending.append(
            (
                ev_key,
                year_by_event[ev_key],
                entry["market_type"],
                pkey,
                okey,
                book,
                entry["odds_american"],
                american_to_implied(entry["odds_american"]),
                entry["first"],
                entry["last"],
                entry["count"],
            )
        )
        if len(pending) >= batch_size:
            _flush(conn, pending, stats)
            if progress:
                progress(len(pending))
    _flush(conn, pending, stats)
    conn.commit()

    outcomes = _refresh_outcomes(conn, event_id=event_id, year=year)
    stats["outcomes"] = outcomes
    conn.close()

    return LedgerBuildStats(
        events_seen=len(stats["events"]),
        rows_inserted=stats["inserted"],
        rows_refreshed=stats["refreshed"],
        outcomes_set=outcomes,
    )


def _flush(conn, pending: list[tuple], stats: dict) -> None:
    if not pending:
        return
    before = conn.total_changes
    conn.executemany(
        """
        INSERT INTO research_backtest_lines (
            event_id, year, market_type, player_key, player_display, opponent_key,
            opponent_display, book, odds_american, implied_prob,
            first_captured_at, last_captured_at, capture_count, outcome, outcome_source
        ) VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, NULL, NULL)
        ON CONFLICT(event_id, year, market_type, player_key, opponent_key, book) DO UPDATE SET
            last_captured_at = excluded.last_captured_at,
            capture_count = excluded.capture_count
        """,
        pending,
    )
    after = conn.total_changes
    changed = after - before
    # INSERTs and UPDATEs both count; we report combined activity as refreshed+inserted.
    stats["refreshed"] += changed
    pending.clear()


def _refresh_outcomes(conn, *, event_id: str | None, year: int | None) -> int:
    """Fill outcomes for ledger rows using the graded picks spine (best-effort)."""
    updated = 0
    where = ["r.outcome IS NULL"]
    params: list[Any] = []
    if event_id is not None:
        where.append("r.event_id = ?")
        params.append(str(event_id))
    if year is not None:
        where.append("r.year = ?")
        params.append(int(year))

    # Join through tournaments.event_id -> picks -> pick_outcomes.
    query = f"""
        UPDATE research_backtest_lines AS r
        SET outcome = (
            SELECT CASE po.hit WHEN 1 THEN '{OUTCOME_WIN}' ELSE '{OUTCOME_LOSS}' END
            FROM picks p
            JOIN pick_outcomes po ON po.pick_id = p.id
            JOIN tournaments t ON t.id = p.tournament_id
            WHERE t.event_id = r.event_id
              AND p.player_key = r.player_key
              AND p.opponent_key = r.opponent_key
              AND p.bet_type LIKE '%match%'
            ORDER BY po.id DESC LIMIT 1
        ),
        outcome_source = 'graded_picks'
        WHERE {' AND '.join(where)}
    """
    cur = conn.execute(query, params)
    updated = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    return updated


def coverage_summary() -> dict[str, Any]:
    """Row/event coverage of the derived ledger (for dashboards + honesty checks)."""
    from src.db import ensure_initialized

    ensure_initialized()
    conn = db.get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM research_backtest_lines").fetchone()[0]
        events = conn.execute(
            "SELECT COUNT(DISTINCT event_id || '/' || year) FROM research_backtest_lines"
        ).fetchone()[0]
        graded = conn.execute(
            "SELECT COUNT(*) FROM research_backtest_lines WHERE outcome IS NOT NULL"
        ).fetchone()[0]
        per_event = conn.execute(
            """
            SELECT event_id, year, COUNT(*) AS n, SUM(outcome IS NOT NULL) AS graded
            FROM research_backtest_lines GROUP BY event_id, year ORDER BY year DESC, event_id
            """
        ).fetchall()
        return {
            "total_lines": total,
            "distinct_events": events,
            "lines_with_outcome": graded,
            "per_event": [
                {"event_id": r[0], "year": r[1], "n": r[2], "graded": r[3]} for r in per_event
            ],
        }
    finally:
        conn.close()
