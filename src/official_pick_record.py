"""Official pick record identity and dedupe — single source of truth."""

from __future__ import annotations

from typing import Any


def american_odds_rank(market_odds: Any) -> float:
    if market_odds is not None:
        try:
            return float(int(str(market_odds).strip().replace("+", "")))
        except (TypeError, ValueError):
            pass
    return -1_000_000.0


def normalize_market_type(value: Any, *, default: str = "tournament_matchups") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"matchup", "matchups"}:
        return "tournament_matchups"
    return raw


def is_matchup_row(row: dict) -> bool:
    bet_type = str(row.get("bet_type") or "").strip().lower()
    market_family = str(row.get("market_family") or "").strip().lower()
    market_type = str(row.get("market_type") or "").strip().lower()
    if bet_type == "matchup" or market_family == "matchup":
        return True
    return "matchup" in market_type


def inventory_matchup_key(row: dict, *, lane: str = "") -> tuple:
    return (
        str(lane or row.get("lane") or "").strip().lower(),
        normalize_market_type(row.get("market_type") or row.get("market_family")),
        str(row.get("player_key") or row.get("player_display") or "").strip().lower(),
        str(row.get("opponent_key") or row.get("opponent_display") or "").strip().lower(),
    )


def inventory_prop_key(row: dict, *, lane: str = "") -> tuple:
    bet_type = str(
        row.get("bet_type") or row.get("market_family") or row.get("market_type") or "",
    ).strip().lower()
    return (
        str(lane or row.get("lane") or "").strip().lower(),
        bet_type,
        str(row.get("player_key") or row.get("player_display") or "").strip().lower(),
    )


def grading_matchup_key(pick: dict) -> tuple:
    return grading_pick_identity_key(pick)


def grading_pick_identity_key(pick: dict) -> tuple:
    """Canonical grading identity — one scored pick per player/market lane (best odds kept)."""
    bet_type = str(pick.get("bet_type") or "").strip().lower()
    base = (
        str(pick.get("source") or ""),
        str(pick.get("model_variant") or ""),
        bet_type,
    )
    player = str(pick.get("player_key") or pick.get("player_display") or "").strip().lower()
    if bet_type == "matchup" or is_matchup_row(pick):
        return base + (
            normalize_market_type(pick.get("market_type")),
            player,
            str(pick.get("opponent_key") or pick.get("opponent_display") or "").strip().lower(),
        )
    return base + (player,)


def dedupe_matchup_rows(
    rows: list[dict],
    *,
    key_fn,
    odds_field: str = "market_odds",
) -> list[dict]:
    deduped: list[dict] = []
    indexes: dict[tuple, int] = {}

    for row in rows:
        key = key_fn(row)
        existing_index = indexes.get(key)
        if existing_index is None:
            indexes[key] = len(deduped)
            deduped.append(row)
            continue
        existing_odds = deduped[existing_index].get(odds_field) or deduped[existing_index].get("odds")
        candidate_odds = row.get(odds_field) or row.get("odds")
        if american_odds_rank(candidate_odds) > american_odds_rank(existing_odds):
            deduped[existing_index] = row

    return deduped


def dedupe_inventory_rows(rows: list[dict], *, lane: str = "") -> list[dict]:
    matchups = [row for row in rows if is_matchup_row(row)]
    props = [row for row in rows if not is_matchup_row(row)]
    lane_value = lane.strip().lower()
    deduped_matchups = dedupe_matchup_rows(
        matchups,
        key_fn=lambda row: inventory_matchup_key(row, lane=lane_value),
        odds_field="odds",
    )
    deduped_props = dedupe_matchup_rows(
        props,
        key_fn=lambda row: inventory_prop_key(row, lane=lane_value),
        odds_field="odds",
    )
    return deduped_matchups + deduped_props


def dedupe_grading_picks(picks: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    indexes: dict[tuple, int] = {}

    for pick in picks:
        key = grading_pick_identity_key(pick)
        existing_index = indexes.get(key)
        if existing_index is None:
            indexes[key] = len(deduped)
            deduped.append(pick)
            continue
        if american_odds_rank(pick.get("market_odds")) > american_odds_rank(deduped[existing_index].get("market_odds")):
            deduped[existing_index] = pick

    return deduped


def consolidate_duplicate_picks(tournament_id: int) -> dict[str, int]:
    """Remove duplicate pick rows for the same grading identity, keeping best odds."""
    from src import db

    conn = db.get_conn()
    try:
        return dedupe_picks_by_grading_identity(conn, tournament_id=tournament_id)
    finally:
        conn.close()


def dedupe_picks_by_grading_identity(
    conn,
    *,
    tournament_id: int | None = None,
) -> dict[str, int]:
    """Collapse duplicate pick rows to one per grading identity (best odds kept)."""
    params: tuple = ()
    tournament_filter = ""
    if tournament_id is not None:
        tournament_filter = "WHERE tournament_id = ?"
        params = (int(tournament_id),)

    rows = conn.execute(
        f"""
        SELECT id, model_variant, source, bet_type, market_type, player_key, player_display,
               opponent_key, opponent_display, market_odds, market_book
        FROM picks
        {tournament_filter}
        ORDER BY id ASC
        """,
        params,
    ).fetchall()

    keep_ids: set[int] = set()
    remove_ids: list[int] = []
    indexes: dict[tuple, int] = {}
    odds_by_id: dict[int, Any] = {}

    for row in rows:
        pick = dict(row)
        pick_id = int(pick["id"])
        odds_by_id[pick_id] = pick.get("market_odds")
        key = grading_pick_identity_key(pick)
        existing_id = indexes.get(key)
        if existing_id is None:
            indexes[key] = pick_id
            keep_ids.add(pick_id)
            continue
        existing_odds = odds_by_id.get(existing_id)
        if american_odds_rank(pick.get("market_odds")) > american_odds_rank(existing_odds):
            remove_ids.append(existing_id)
            keep_ids.discard(existing_id)
            indexes[key] = pick_id
            keep_ids.add(pick_id)
        else:
            remove_ids.append(pick_id)

    removed = 0
    for pick_id in remove_ids:
        conn.execute("DELETE FROM pick_outcomes WHERE pick_id = ?", (pick_id,))
        conn.execute("DELETE FROM picks WHERE id = ?", (pick_id,))
        removed += 1

    conn.commit()
    return {"removed": removed, "kept": len(keep_ids)}


def filter_positive_ev(rows: list[dict], *, ev_field: str = "ev") -> list[dict]:
    positive: list[dict] = []
    for row in rows:
        ev = row.get(ev_field)
        if ev is None:
            continue
        try:
            if float(ev) > 0:
                positive.append(row)
        except (TypeError, ValueError):
            continue
    return positive
