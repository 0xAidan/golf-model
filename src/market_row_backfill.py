"""Backfill gradeable picks from completed durable market-row snapshots."""

from __future__ import annotations

from typing import Any

from src import db


def backfill_completed_market_rows_into_picks(
    event_id: str,
    tournament_id: int,
    *,
    source: str = "dashboard",
    limit: int = 10000,
) -> int:
    """Persist the final pre-teeoff market rows as gradeable picks.

    The source maps to the durable pick lane:
    - ``dashboard`` -> ``cockpit`` / ``baseline``
    - ``lab`` -> ``lab_sandbox`` / ``v5``

    ``store_picks`` is idempotent via the picks unique index; this function
    returns the number of newly inserted picks.
    """
    tid = int(tournament_id or 0)
    if tid <= 0:
        return 0

    normalized_source = str(source or "dashboard").strip().lower()
    pick_source = "lab_sandbox" if normalized_source == "lab" else "cockpit"
    default_model_variant = "v5" if normalized_source == "lab" else "baseline"
    rows = db.get_completed_market_prediction_rows_for_event(
        event_id,
        source=normalized_source,
        limit=limit,
    )
    if not rows:
        return 0

    before = _pick_count(tid, pick_source)
    db.store_picks(
        [
            _row_to_pick(row, tournament_id=tid, source=pick_source, default_model_variant=default_model_variant)
            for row in rows
            if row.get("player_key") or row.get("player_display")
        ]
    )
    after = _pick_count(tid, pick_source)
    return max(0, after - before)


def _pick_count(tournament_id: int, source: str) -> int:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM picks WHERE tournament_id = ? AND source = ?",
        (tournament_id, source),
    ).fetchone()
    conn.close()
    return int(row["c"] or 0) if row else 0


def _row_to_pick(
    row: dict[str, Any],
    *,
    tournament_id: int,
    source: str,
    default_model_variant: str,
) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    model_variant = str(payload.get("model_variant") or default_model_variant).strip().lower()
    market_family = str(row.get("market_family") or "").strip().lower()
    market_type = str(row.get("market_type") or market_family or "").strip()
    bet_type = "matchup" if market_family == "matchup" else market_type
    provenance = "market_prediction_rows"
    if row.get("snapshot_id"):
        provenance = f"{provenance}:{row.get('snapshot_id')}"
    if row.get("section"):
        provenance = f"{provenance}:{row.get('section')}"
    existing_reason = payload.get("reason") or payload.get("why") or payload.get("reason_code")
    reasoning = f"{provenance}; {existing_reason}" if existing_reason else provenance

    return {
        "tournament_id": tournament_id,
        "model_variant": model_variant,
        "source": source,
        "bet_type": bet_type,
        "player_key": row.get("player_key") or "",
        "player_display": row.get("player_display") or payload.get("player") or payload.get("pick"),
        "opponent_key": row.get("opponent_key") or "",
        "opponent_display": row.get("opponent_display") or payload.get("opponent") or "",
        "composite_score": payload.get("composite") or payload.get("composite_score"),
        "course_fit_score": payload.get("course_fit") or payload.get("course_fit_score"),
        "form_score": payload.get("form") or payload.get("form_score"),
        "momentum_score": payload.get("momentum") or payload.get("momentum_score"),
        "model_prob": row.get("model_prob") if row.get("model_prob") is not None else payload.get("model_win_prob"),
        "market_odds": row.get("odds") or payload.get("odds") or payload.get("market_odds"),
        "market_book": row.get("book") or payload.get("book") or payload.get("bookmaker") or "",
        "market_implied_prob": (
            row.get("implied_prob") if row.get("implied_prob") is not None else payload.get("implied_prob")
        ),
        "ev": row.get("ev") if row.get("ev") is not None else payload.get("ev"),
        "confidence": payload.get("confidence") or payload.get("tier"),
        "reasoning": reasoning,
    }
