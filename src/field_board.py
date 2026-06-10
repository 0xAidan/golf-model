"""Field-complete player board: one response for the whole tournament field.

Per-player intelligence built in a single pass over the live-refresh snapshot (which is
already field-complete and computed each tick), enriched with both-track rank provenance
and pick involvement. Strokes-gained splits are a best-effort enrichment from the
``metrics`` table (one bulk query) when available.

This avoids the previous one-player-at-a-time pattern (a rich-profile call per player) for
the directory/board use case while keeping the deep per-player profile endpoints intact.
"""

from __future__ import annotations

from typing import Any


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _section_for(snapshot: dict[str, Any], track_prefix: str, section: str) -> dict[str, Any] | None:
    """Resolve a tournament section from the snapshot for a track + live/upcoming choice."""
    live_key = f"{track_prefix}live_tournament" if track_prefix else "live_tournament"
    upcoming_key = f"{track_prefix}upcoming_tournament" if track_prefix else "upcoming_tournament"
    if section == "live":
        return snapshot.get(live_key)
    if section == "upcoming":
        return snapshot.get(upcoming_key)
    # auto: prefer an active live section, else upcoming
    live = snapshot.get(live_key)
    if isinstance(live, dict) and live.get("active"):
        return live
    return snapshot.get(upcoming_key) or live


def _rank_index(section: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(section, dict):
        return index
    for row in section.get("rankings") or []:
        key = _norm(row.get("player_key"))
        if key:
            index[key] = row
    return index


def _resolved_section_label(snapshot: dict[str, Any], section: str) -> str:
    live = snapshot.get("live_tournament")
    if section == "auto":
        return "live" if isinstance(live, dict) and live.get("active") else "upcoming"
    return section


def build_field_board(
    snapshot: dict[str, Any] | None,
    *,
    section: str = "auto",
    sg_by_player: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the field board dict from a snapshot.

    Args:
        snapshot: live-refresh snapshot dict.
        section: ``auto`` | ``live`` | ``upcoming``.
        sg_by_player: optional ``{player_key: {metric_name: value}}`` SG enrichment.
    """
    snapshot = snapshot or {}
    resolved = _resolved_section_label(snapshot, section)
    champ_section = _section_for(snapshot, "", section)
    lab_section = _section_for(snapshot, "lab_", section)

    champ_ranks = _rank_index(champ_section)
    lab_ranks = _rank_index(lab_section)
    sg_lookup = sg_by_player or {}

    # Pick involvement from the champion section.
    matchup_count: dict[str, int] = {}
    positive_ev_players: set[str] = set()
    if isinstance(champ_section, dict):
        for bet in champ_section.get("matchup_bets") or []:
            for who in (_norm(bet.get("pick_key")), _norm(bet.get("opponent_key"))):
                if who:
                    matchup_count[who] = matchup_count.get(who, 0) + 1
            if (bet.get("ev") or 0) > 0:
                pick = _norm(bet.get("pick_key"))
                if pick:
                    positive_ev_players.add(pick)
        for _market, bets in (champ_section.get("value_bets") or {}).items():
            for bet in bets or []:
                if bet.get("is_value") and (bet.get("ev") or 0) > 0:
                    pk = _norm(bet.get("player_key"))
                    if pk:
                        positive_ev_players.add(pk)

    players: list[dict[str, Any]] = []
    for key, row in champ_ranks.items():
        lab_row = lab_ranks.get(key)
        champion_rank = row.get("rank")
        challenger_rank = lab_row.get("rank") if lab_row else None
        rank_delta = (
            champion_rank - challenger_rank
            if isinstance(champion_rank, (int, float)) and isinstance(challenger_rank, (int, float))
            else None
        )
        players.append({
            "player_key": row.get("player_key"),
            "player": row.get("player"),
            "champion_rank": champion_rank,
            "challenger_rank": challenger_rank,
            "rank_delta": rank_delta,
            "composite": row.get("composite"),
            "course_fit": row.get("course_fit"),
            "form": row.get("form"),
            "momentum": row.get("momentum"),
            "momentum_direction": row.get("momentum_direction"),
            "momentum_trend": row.get("momentum_trend"),
            "course_confidence": row.get("course_confidence"),
            "finish_state": row.get("finish_state"),
            "leaderboard_position": row.get("leaderboard_position"),
            "leaderboard_delta": row.get("leaderboard_delta"),
            "total_to_par": row.get("total_to_par"),
            "form_flags": row.get("form_flags") or [],
            "matchup_count": matchup_count.get(key, 0),
            "in_positive_ev": key in positive_ev_players,
            "sg": sg_lookup.get(key) or None,
            "has_sg": bool(sg_lookup.get(key)),
        })

    players.sort(key=lambda p: (p["champion_rank"] is None, p["champion_rank"] or 0))

    return {
        "section": resolved,
        "event_name": (champ_section or {}).get("event_name") if isinstance(champ_section, dict) else None,
        "tournament_id": (champ_section or {}).get("tournament_id") if isinstance(champ_section, dict) else None,
        "generated_at": snapshot.get("generated_at"),
        "snapshot_id": snapshot.get("snapshot_id"),
        "lab_available": bool(lab_ranks),
        "player_count": len(players),
        "players": players,
    }


def load_sg_by_player(tournament_id: int | None) -> dict[str, dict[str, Any]]:
    """Best-effort: one bulk query of the strokes_gained metrics for the whole field."""
    if not tournament_id:
        return {}
    try:
        from src import db

        rows = db.get_metrics_by_category(int(tournament_id), "strokes_gained")
    except Exception:
        return {}
    by_player: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        key = _norm(row.get("player_key"))
        name = row.get("metric_name")
        if not key or not name:
            continue
        by_player.setdefault(key, {})[str(name)] = row.get("metric_value")
    return by_player
