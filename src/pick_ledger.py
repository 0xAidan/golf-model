"""Composable pick ledger — append-only store for every model-generated line."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from src import db
from src.player_normalizer import display_name, normalize_name
from src.scoring import parse_odds_to_decimal

_logger = logging.getLogger("pick_ledger")

AUTHORITATIVE_GRADING = frozenset({
    "trackRecord_json",
    "card_import",
    "dg_official",
    "manual",
})

LOCKED_GRADING_AUTHORITIES = AUTHORITATIVE_GRADING | frozenset({"computed"})


def normalize_american_odds(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith("+") or text.startswith("-"):
        return text
    try:
        n = int(float(text))
        return f"+{n}" if n > 0 else str(n)
    except (TypeError, ValueError):
        return text


def compute_pick_key(
    *,
    event_id: str,
    lane: str,
    section: str,
    phase: str,
    bet_type: str,
    player_key: str,
    opponent_key: str = "",
    book: str = "",
    odds: str = "",
    snapshot_id: str = "",
) -> str:
    parts = [
        str(event_id or "").strip(),
        str(lane or "").strip().lower(),
        str(section or "").strip().lower(),
        str(phase or "").strip().lower(),
        str(bet_type or "").strip().lower(),
        str(player_key or "").strip().lower(),
        str(opponent_key or "").strip().lower(),
        str(book or "").strip().lower(),
        normalize_american_odds(odds),
        str(snapshot_id or "").strip(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _section_to_lane(section: str) -> str:
    s = str(section or "").strip().lower()
    return "lab" if s.startswith("lab") else "cockpit"


def _section_to_phase(section: str) -> str:
    s = str(section or "").strip().lower()
    if s in {"upcoming", "lab_upcoming", "frozen"}:
        return "pre_tournament"
    if s in {"live", "lab_live"}:
        return "live"
    return "in_play"


def _ledger_row_from_market_row(
    row: dict[str, Any],
    *,
    lifecycle: str = "generated",
    source_origin: str = "live_refresh",
    tournament_id: int | None = None,
    year: int | None = None,
    model_variant: str | None = None,
    model_config_hash: str | None = None,
) -> dict[str, Any] | None:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if row.get("payload_json") and not payload:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}

    event_id = str(row.get("event_id") or "").strip()
    if not event_id:
        return None

    section = str(row.get("section") or "upcoming").strip().lower()
    lane = _section_to_lane(section)
    phase = _section_to_phase(section)
    market_family = str(row.get("market_family") or "").strip().lower()
    market_type = str(row.get("market_type") or market_family or "").strip().lower()
    bet_type = "matchup" if market_family == "matchup" else market_type or "matchup"

    player_display = row.get("player_display") or payload.get("pick") or payload.get("player") or ""
    opponent_display = row.get("opponent_display") or payload.get("opponent") or ""
    player_key = str(row.get("player_key") or "").strip() or normalize_name(str(player_display))
    opponent_key = str(row.get("opponent_key") or "").strip() or normalize_name(str(opponent_display))
    if not player_key:
        return None

    book = str(row.get("book") or payload.get("book") or payload.get("bookmaker") or "").strip()
    odds = normalize_american_odds(row.get("odds") or payload.get("odds") or payload.get("market_odds"))
    snapshot_id = str(row.get("snapshot_id") or "").strip()

    pick_key = compute_pick_key(
        event_id=event_id,
        lane=lane,
        section=section,
        phase=phase,
        bet_type=bet_type,
        player_key=player_key,
        opponent_key=opponent_key,
        book=book,
        odds=odds,
        snapshot_id=snapshot_id,
    )

    return {
        "pick_key": pick_key,
        "event_id": event_id,
        "event_name": row.get("event_name"),
        "tournament_id": tournament_id,
        "year": year,
        "phase": phase,
        "section": section,
        "lane": lane,
        "lifecycle": lifecycle,
        "bet_type": bet_type,
        "market_family": market_family or bet_type,
        "market_type": market_type or bet_type,
        "player_key": player_key,
        "player_display": player_display or display_name(player_key),
        "opponent_key": opponent_key,
        "opponent_display": opponent_display,
        "book": book,
        "odds": odds,
        "model_prob": row.get("model_prob"),
        "implied_prob": row.get("implied_prob"),
        "ev": row.get("ev"),
        "is_value": int(row.get("is_value") or (row.get("ev") is not None and float(row.get("ev") or 0) > 0)),
        "model_variant": model_variant or payload.get("model_variant") or ("v5" if lane == "lab" else "baseline"),
        "model_config_hash": model_config_hash or payload.get("model_config_hash"),
        "snapshot_id": snapshot_id,
        "generated_at": row.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "source_origin": source_origin,
        "payload_json": json.dumps(payload or row),
    }


def persist_pick_ledger_rows(rows: list[dict[str, Any]]) -> int:
    """Insert ledger rows idempotently. Returns count of new rows."""
    if not rows:
        return 0
    db.ensure_initialized()
    conn = db.get_conn()
    inserted = 0
    try:
        for row in rows:
            if not row.get("pick_key"):
                continue
            normalized = {
                "pick_key": row["pick_key"],
                "event_id": row.get("event_id"),
                "event_name": row.get("event_name"),
                "tournament_id": row.get("tournament_id"),
                "year": row.get("year"),
                "phase": row.get("phase") or "pre_tournament",
                "section": row.get("section") or "upcoming",
                "lane": row.get("lane") or "cockpit",
                "lifecycle": row.get("lifecycle") or "generated",
                "bet_type": row.get("bet_type"),
                "market_family": row.get("market_family"),
                "market_type": row.get("market_type"),
                "player_key": row.get("player_key"),
                "player_display": row.get("player_display"),
                "opponent_key": row.get("opponent_key"),
                "opponent_display": row.get("opponent_display"),
                "book": row.get("book"),
                "odds": row.get("odds"),
                "model_prob": row.get("model_prob"),
                "implied_prob": row.get("implied_prob"),
                "ev": row.get("ev"),
                "is_value": row.get("is_value", 0),
                "model_variant": row.get("model_variant"),
                "model_config_hash": row.get("model_config_hash"),
                "snapshot_id": row.get("snapshot_id"),
                "generated_at": row.get("generated_at"),
                "source_origin": row.get("source_origin") or "live_refresh",
                "payload_json": row.get("payload_json"),
            }
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO pick_ledger (
                    pick_key, event_id, event_name, tournament_id, year,
                    phase, section, lane, lifecycle,
                    bet_type, market_family, market_type,
                    player_key, player_display, opponent_key, opponent_display,
                    book, odds, model_prob, implied_prob, ev, is_value,
                    model_variant, model_config_hash, snapshot_id, generated_at,
                    source_origin, payload_json
                ) VALUES (
                    :pick_key, :event_id, :event_name, :tournament_id, :year,
                    :phase, :section, :lane, :lifecycle,
                    :bet_type, :market_family, :market_type,
                    :player_key, :player_display, :opponent_key, :opponent_display,
                    :book, :odds, :model_prob, :implied_prob, :ev, :is_value,
                    :model_variant, :model_config_hash, :snapshot_id, :generated_at,
                    :source_origin, :payload_json
                )
                """,
                normalized,
            )
            inserted += int(cur.rowcount or 0)
        conn.commit()
    finally:
        conn.close()
    return inserted


def persist_pick_ledger_from_market_rows(
    market_rows: list[dict[str, Any]],
    *,
    lifecycle: str = "generated",
    source_origin: str = "live_refresh",
    tournament_id: int | None = None,
    year: int | None = None,
) -> int:
    ledger_rows: list[dict[str, Any]] = []
    for row in market_rows:
        built = _ledger_row_from_market_row(
            row,
            lifecycle=lifecycle,
            source_origin=source_origin,
            tournament_id=tournament_id or row.get("tournament_id"),
            year=year or row.get("year"),
        )
        if built:
            ledger_rows.append(built)
    return persist_pick_ledger_rows(ledger_rows)


def backfill_pick_ledger_from_picks(
    tournament_id: int,
    *,
    lifecycle: str = "displayed",
    source_origin: str = "picks_backfill",
) -> int:
    """Sync gradeable picks rows into pick_ledger when ledger writes were missed."""
    tid = int(tournament_id or 0)
    if tid <= 0:
        return 0
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        picks = conn.execute(
            """
            SELECT p.*, t.event_id, t.year, t.name AS event_name
            FROM picks p
            JOIN tournaments t ON t.id = p.tournament_id
            WHERE p.tournament_id = ?
              AND p.ev IS NOT NULL AND p.ev > 0
            """,
            (tid,),
        ).fetchall()
    finally:
        conn.close()
    if not picks:
        return 0

    ledger_rows: list[dict[str, Any]] = []
    for raw in picks:
        pick = dict(raw)
        event_id = str(pick.get("event_id") or f"tournament_{tid}").strip()
        year = int(pick.get("year") or datetime.now(timezone.utc).year)
        source = str(pick.get("source") or "cockpit").strip().lower()
        lane = "lab" if source == "lab_sandbox" else "cockpit"
        bet_type = str(pick.get("bet_type") or "matchup").strip().lower()
        player_key = str(pick.get("player_key") or "").strip()
        if not player_key:
            continue
        opponent_key = str(pick.get("opponent_key") or "").strip()
        book = str(pick.get("market_book") or "").strip()
        odds = normalize_american_odds(pick.get("market_odds"))
        snapshot_id = f"displayed_{tid}"
        pick_key = compute_pick_key(
            event_id=event_id,
            lane=lane,
            section="upcoming",
            phase="pre_tournament",
            bet_type=bet_type,
            player_key=player_key,
            opponent_key=opponent_key,
            book=book,
            odds=odds,
            snapshot_id=snapshot_id,
        )
        ledger_rows.append({
            "pick_key": pick_key,
            "event_id": event_id,
            "event_name": pick.get("event_name"),
            "tournament_id": tid,
            "year": year,
            "phase": "pre_tournament",
            "section": "upcoming",
            "lane": lane,
            "lifecycle": lifecycle,
            "bet_type": bet_type,
            "market_family": bet_type if bet_type != "matchup" else "matchup",
            "market_type": pick.get("market_type") or bet_type,
            "player_key": player_key,
            "player_display": pick.get("player_display") or display_name(player_key),
            "opponent_key": opponent_key,
            "opponent_display": pick.get("opponent_display") or "",
            "book": book,
            "odds": odds,
            "model_prob": pick.get("model_prob"),
            "implied_prob": pick.get("market_implied_prob"),
            "ev": pick.get("ev"),
            "is_value": 1,
            "model_variant": pick.get("model_variant"),
            "model_config_hash": pick.get("model_config_hash"),
            "snapshot_id": snapshot_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_origin": source_origin,
            "payload_json": json.dumps(pick),
        })
    return persist_pick_ledger_rows(ledger_rows)


def persist_pick_ledger_from_section(
    section_payload: dict[str, Any] | None,
    *,
    section: str,
    snapshot_id: str,
    generated_at: str,
    lifecycle: str = "generated",
    source_origin: str = "live_refresh",
) -> int:
    """Build market-style rows from a snapshot section and persist to ledger."""
    if not section_payload:
        return 0
    from backtester.dashboard_runtime import _build_market_prediction_rows

    tour = str(section_payload.get("tour") or "pga")
    market_rows = _build_market_prediction_rows(
        snapshot_id=snapshot_id,
        generated_at=generated_at,
        tour=tour,
        section_name=section,
        section_payload=section_payload,
    )
    return persist_pick_ledger_from_market_rows(
        market_rows,
        lifecycle=lifecycle,
        source_origin=source_origin,
    )


def promote_lifecycle(pick_keys: list[str], lifecycle: str) -> int:
    if not pick_keys:
        return 0
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        cur = conn.executemany(
            "UPDATE pick_ledger SET lifecycle = ? WHERE pick_key = ?",
            [(lifecycle, pk) for pk in pick_keys if pk],
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def result_to_hit(result: str) -> tuple[int, int]:
    """Map trackRecord result string to (hit, model_hit). Push -> hit=0."""
    r = str(result or "").strip().lower()
    if r == "win":
        return 1, 1
    if r == "loss":
        return 0, 0
    if r == "push":
        return 0, 0
    return 0, 0


def insert_authoritative_pick_outcome(
    *,
    tournament_id: int,
    pick_row: dict[str, Any],
    ledger_row: dict[str, Any],
    result: str,
    profit: float,
    grading_authority: str,
    notes: str | None = None,
) -> int | None:
    """Insert pick + locked outcome from Tier A source. Returns pick_id."""
    db.store_picks([pick_row])
    conn = db.get_conn()
    try:
        pick = conn.execute(
            """
            SELECT id FROM picks
            WHERE tournament_id = ? AND model_variant = ? AND source = ?
              AND player_key = ? AND bet_type = ? AND opponent_key = ?
              AND market_book = ? AND market_odds = ?
            ORDER BY id DESC LIMIT 1
            """,
            (
                tournament_id,
                pick_row.get("model_variant") or "baseline",
                pick_row.get("source") or "cockpit",
                pick_row.get("player_key"),
                pick_row.get("bet_type"),
                pick_row.get("opponent_key") or "",
                pick_row.get("market_book") or "",
                pick_row.get("market_odds"),
            ),
        ).fetchone()
        if not pick:
            conn.close()
            return None
        pick_id = int(pick["id"])
        pick_key = ledger_row.get("pick_key")
        hit, model_hit = result_to_hit(result)
        odds_decimal = parse_odds_to_decimal(pick_row.get("market_odds"))
        existing = conn.execute(
            "SELECT id, outcome_locked FROM pick_outcomes WHERE pick_id = ?",
            (pick_id,),
        ).fetchone()
        if existing and int(existing["outcome_locked"] or 0) == 1:
            conn.close()
            return pick_id
        if existing:
            conn.execute(
                """
                UPDATE pick_outcomes SET
                    hit = ?, model_hit = ?, profit = ?, stake = 1.0,
                    odds_decimal = ?, grading_authority = ?, pick_key = ?,
                    outcome_locked = 1, notes = ?
                WHERE id = ? AND COALESCE(outcome_locked, 0) = 0
                """,
                (hit, model_hit, profit, odds_decimal, grading_authority, pick_key, notes, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO pick_outcomes
                    (pick_id, pick_key, hit, model_hit, actual_finish, odds_decimal,
                     stake, profit, notes, grading_authority, outcome_locked)
                VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, 1)
                """,
                (pick_id, pick_key, hit, model_hit, result, odds_decimal, profit, notes, grading_authority),
            )
        conn.commit()
        conn.close()
        graded_ledger = {**ledger_row, "lifecycle": "graded"}
        if graded_ledger.get("event_name") is None:
            graded_ledger["event_name"] = None
        persist_pick_ledger_rows([graded_ledger])
        return pick_id
    except Exception:
        conn.close()
        raise


def log_grading_audit(
    *,
    pick_id: int | None,
    pick_key: str | None,
    tournament_id: int | None,
    action: str,
    reason: str,
    previous: dict | None = None,
    new: dict | None = None,
) -> None:
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        conn.execute(
            """
            INSERT INTO grading_audit_log
                (pick_id, pick_key, tournament_id, action, reason, previous_json, new_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pick_id,
                pick_key,
                tournament_id,
                action,
                reason,
                json.dumps(previous) if previous else None,
                json.dumps(new) if new else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def tournament_has_locked_outcomes(tournament_id: int) -> bool:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM pick_outcomes po
            JOIN picks p ON p.id = po.pick_id
            WHERE p.tournament_id = ? AND COALESCE(po.outcome_locked, 0) = 1
            """,
            (tournament_id,),
        ).fetchone()
        return int(row["c"] or 0) > 0
    finally:
        conn.close()
