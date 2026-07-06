"""Persist and query Data Golf historical matchup outcomes for grading."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.player_normalizer import normalize_name


def ensure_matchup_outcome_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matchup_outcome_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            event_id TEXT,
            year INTEGER,
            market_type TEXT NOT NULL,
            player_key TEXT NOT NULL,
            opponent_key TEXT NOT NULL,
            book TEXT NOT NULL DEFAULT '',
            p1_outcome REAL,
            p2_outcome REAL,
            p1_outcome_text TEXT,
            p2_outcome_text TEXT,
            tie_rule TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_matchup_outcome_unique
        ON matchup_outcome_results(tournament_id, player_key, opponent_key, market_type, book)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_matchup_outcome_lookup
        ON matchup_outcome_results(tournament_id, market_type, player_key, opponent_key)
        """
    )


def _canonical_market_label(label: str) -> str:
    return (
        str(label or "")
        .strip()
        .lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def resolve_market_type(bet_type: str) -> str:
    canon = _canonical_market_label(bet_type)
    if "72hole" in canon or "tournament" in canon:
        return "tournament_matchups"
    if "3ball" in canon or canon in {"3balls", "group"}:
        return "3_balls"
    return "round_matchups"


def _parse_matchup_row(row: dict, *, book: str) -> dict[str, Any] | None:
    p1_name = row.get("p1_name") or row.get("p1_player_name")
    p2_name = row.get("p2_name") or row.get("p2_player_name")
    if not p1_name or not p2_name:
        return None
    p1_key = normalize_name(str(p1_name))
    p2_key = normalize_name(str(p2_name))
    if not p1_key or not p2_key:
        return None
    return {
        "market_type": resolve_market_type(str(row.get("bet_type") or "")),
        "player_key": p1_key,
        "opponent_key": p2_key,
        "book": str(book or row.get("book") or ""),
        "p1_outcome": row.get("p1_outcome"),
        "p2_outcome": row.get("p2_outcome"),
        "p1_outcome_text": row.get("p1_outcome_text"),
        "p2_outcome_text": row.get("p2_outcome_text"),
        "tie_rule": row.get("tie_rule"),
    }


def store_matchup_outcomes(
    tournament_id: int,
    event_id: str,
    year: int,
    rows: list[dict],
    *,
    book: str = "bet365",
    conn: sqlite3.Connection | None = None,
) -> int:
    """Idempotently persist parsed DG matchup outcome rows."""
    close = False
    if conn is None:
        from src import db

        conn = db.get_conn()
        close = True
    ensure_matchup_outcome_table(conn)
    stored = 0
    for raw in rows:
        parsed = _parse_matchup_row(raw, book=book)
        if not parsed:
            continue
        cursor = conn.execute(
            """
            INSERT INTO matchup_outcome_results (
                tournament_id, event_id, year, market_type,
                player_key, opponent_key, book,
                p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tournament_id, player_key, opponent_key, market_type, book)
            DO UPDATE SET
                event_id = excluded.event_id,
                year = excluded.year,
                p1_outcome = excluded.p1_outcome,
                p2_outcome = excluded.p2_outcome,
                p1_outcome_text = excluded.p1_outcome_text,
                p2_outcome_text = excluded.p2_outcome_text,
                tie_rule = excluded.tie_rule
            """,
            (
                tournament_id,
                str(event_id),
                int(year),
                parsed["market_type"],
                parsed["player_key"],
                parsed["opponent_key"],
                parsed["book"],
                parsed["p1_outcome"],
                parsed["p2_outcome"],
                parsed["p1_outcome_text"],
                parsed["p2_outcome_text"],
                parsed["tie_rule"],
            ),
        )
        if cursor.rowcount:
            stored += 1
    conn.commit()
    if close:
        conn.close()
    return stored


def lookup_matchup_outcome(
    conn: sqlite3.Connection,
    tournament_id: int,
    player_key: str,
    opponent_key: str,
    market_type: str,
    book: str | None = None,
) -> dict[str, Any] | None:
    ensure_matchup_outcome_table(conn)
    params: list[Any] = [tournament_id, player_key, opponent_key, market_type]
    book_clause = ""
    if book:
        book_clause = " AND book = ?"
        params.append(str(book))
    row = conn.execute(
        f"""
        SELECT * FROM matchup_outcome_results
        WHERE tournament_id = ? AND player_key = ? AND opponent_key = ?
          AND market_type = ?{book_clause}
        ORDER BY id DESC LIMIT 1
        """,
        params,
    ).fetchone()
    if row:
        return dict(row)
    flip_params: list[Any] = [tournament_id, opponent_key, player_key, market_type]
    if book:
        flip_params.append(str(book))
    flipped = conn.execute(
        f"""
        SELECT * FROM matchup_outcome_results
        WHERE tournament_id = ? AND player_key = ? AND opponent_key = ?
          AND market_type = ?{book_clause}
        ORDER BY id DESC LIMIT 1
        """,
        flip_params,
    ).fetchone()
    if not flipped:
        return None
    data = dict(flipped)
    data["_flipped"] = True
    return data


def lookup_any_matchup_for_player(
    conn: sqlite3.Connection,
    tournament_id: int,
    player_key: str,
    market_type: str,
    book: str | None = None,
) -> dict[str, Any] | None:
    """Find any stored DG matchup row involving player_key (e.g. 3-ball without opponent on pick)."""
    ensure_matchup_outcome_table(conn)
    params: list[Any] = [tournament_id, market_type, player_key, player_key]
    book_clause = ""
    if book:
        book_clause = " AND book = ?"
        params.append(str(book))
    row = conn.execute(
        f"""
        SELECT * FROM matchup_outcome_results
        WHERE tournament_id = ?
          AND market_type = ?
          AND (player_key = ? OR opponent_key = ?){book_clause}
        ORDER BY id DESC LIMIT 1
        """,
        params,
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    if str(data.get("player_key") or "") != str(player_key or ""):
        data["_flipped"] = True
    return data


def threeball_group_opponent_keys(
    conn: sqlite3.Connection,
    tournament_id: int,
    player_key: str,
    *,
    pick_opponent_key: str | None = None,
) -> list[str]:
    """Collect opponent player keys in the same 3-ball group from stored DG rows."""
    ensure_matchup_outcome_table(conn)
    keys: set[str] = set()
    if pick_opponent_key:
        keys.add(str(pick_opponent_key))
    rows = conn.execute(
        """
        SELECT player_key, opponent_key FROM matchup_outcome_results
        WHERE tournament_id = ? AND market_type = '3_balls'
          AND (player_key = ? OR opponent_key = ?)
        """,
        (tournament_id, player_key, player_key),
    ).fetchall()
    for row in rows:
        for col in ("player_key", "opponent_key"):
            val = str(row[col] or "")
            if val and val != player_key:
                keys.add(val)
    return sorted(keys)


def outcome_from_stored_matchup(row: dict[str, Any], pick_player_key: str) -> dict[str, Any]:
    """Map a stored DG matchup row to scoring outcome for the picked side."""
    flipped = bool(row.get("_flipped"))
    if flipped:
        outcome_text = str(row.get("p2_outcome_text") or "").strip().lower()
    elif str(row.get("player_key") or "") == str(pick_player_key or ""):
        outcome_text = str(row.get("p1_outcome_text") or "").strip().lower()
    else:
        outcome_text = str(row.get("p2_outcome_text") or "").strip().lower()

    if outcome_text == "win":
        return {"hit": 1, "fraction": 1.0, "is_push": False}
    if outcome_text in {"push", "tie", "draw"}:
        return {"hit": 0, "fraction": 0.0, "is_push": True}
    return {"hit": 0, "fraction": 0.0, "is_push": False}
