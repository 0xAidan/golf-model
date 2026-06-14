"""
Parse ephemeral Data Golf in-play live stats for live model refresh.

Official API (`preds/in-play`) is the primary source. Stats are point-in-time only
and must not overwrite historical ``rounds`` rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src import config
from src.datagolf import _flatten_in_play_player_rows, _safe_float
from src.player_normalizer import normalize_name as _norm

_LIVE_SG_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "round_sg_total": ("round_sg_total", "sg_total", "r_sg_total", "live_sg_total"),
    "round_sg_ott": ("round_sg_ott", "sg_ott", "r_sg_ott", "live_sg_ott"),
    "round_sg_app": ("round_sg_app", "sg_app", "r_sg_app", "live_sg_app"),
    "round_sg_arg": ("round_sg_arg", "sg_arg", "r_sg_arg", "live_sg_arg"),
    "round_sg_putt": ("round_sg_putt", "sg_putt", "r_sg_putt", "live_sg_putt"),
    "round_sg_t2g": ("round_sg_t2g", "sg_t2g", "r_sg_t2g", "live_sg_t2g"),
}


def _first_float(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        val = _safe_float(row.get(key))
        if val is not None:
            return val
    return None


def _parse_thru(raw: Any) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text or text in {"-", "—", "F", "FIN", "FINISHED"}:
        if text in {"F", "FIN", "FINISHED"}:
            return 18
        return None
    if text.isdigit():
        try:
            return int(text)
        except ValueError:
            return None
    if "/" in text:
        left = text.split("/", 1)[0].strip()
        if left.isdigit():
            return int(left)
    return None


def _parse_round_num(row: dict[str, Any]) -> int | None:
    rnd = row.get("round") or row.get("current_round") or row.get("rnd")
    try:
        if rnd is not None:
            return int(rnd)
    except (TypeError, ValueError):
        pass
    for n in (4, 3, 2, 1):
        if row.get(f"R{n}") is not None:
            return n
    return None


def _parse_current_round_score(row: dict[str, Any], round_num: int | None) -> int | None:
    if round_num is not None:
        raw_rs = row.get(f"R{round_num}")
        if raw_rs is not None:
            try:
                return int(float(raw_rs))
            except (TypeError, ValueError):
                pass
    for key in ("score", "current_round_score", "round_score"):
        raw = row.get(key)
        if raw is not None:
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                continue
    return None


def _row_timestamp(row: dict[str, Any], payload: dict[str, Any] | None, fetched_at: datetime) -> datetime:
    for container in (row, payload or {}):
        for key in ("updated_at", "last_updated", "timestamp", "as_of"):
            raw = container.get(key)
            if not raw:
                continue
            try:
                text = str(raw).replace("Z", "+00:00")
                return datetime.fromisoformat(text)
            except (TypeError, ValueError):
                continue
    return fetched_at


def _row_age_seconds(row_ts: datetime, fetched_at: datetime) -> float:
    return max(0.0, (fetched_at - row_ts).total_seconds())


def _row_is_complete(stats: dict[str, Any]) -> bool:
    if stats.get("thru") is not None:
        return True
    if stats.get("round_sg_total") is not None:
        return True
    if stats.get("score") is not None:
        return True
    return False


def parse_live_stats_from_in_play(
    raw: dict | list | None,
    *,
    fetched_at: datetime | None = None,
    max_row_age_seconds: float | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """
    Normalize per-player live stats from preds/in-play.

    Returns (live_stats_by_player_key, metadata).
    """
    fetched = fetched_at or datetime.now(timezone.utc)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    ttl = float(
        max_row_age_seconds
        if max_row_age_seconds is not None
        else getattr(config, "LIVE_STATS_FRESHNESS_TTL_SECONDS", 300)
    )
    payload = raw if isinstance(raw, dict) else {}
    rows_in = _flatten_in_play_player_rows(raw)
    if not rows_in:
        return {}, {
            "live_stats_source": "datagolf_in_play",
            "live_stats_fetched_at": fetched.isoformat(),
            "live_stats_age_seconds": None,
            "live_stats_fresh": False,
            "live_model_mode": "no_live_stats",
            "live_stats_warning": "No in-play player rows for live stats.",
            "players_accepted": 0,
            "players_rejected_stale": 0,
        }

    by_player: dict[str, dict[str, Any]] = {}
    rejected_stale = 0
    freshest_age: float | None = None

    for row in rows_in:
        name = (
            row.get("player_name")
            or row.get("name")
            or row.get("player")
            or row.get("p_name")
        )
        if not name or not isinstance(name, str):
            continue
        pk = _norm(name.strip())
        if not pk:
            continue
        row_ts = _row_timestamp(row, payload, fetched)
        age = _row_age_seconds(row_ts, fetched)
        if age > ttl:
            rejected_stale += 1
            continue
        if freshest_age is None or age < freshest_age:
            freshest_age = age

        round_num = _parse_round_num(row)
        stats: dict[str, Any] = {
            "player_key": pk,
            "round": round_num,
            "thru": _parse_thru(row.get("thru")),
            "score": _parse_current_round_score(row, round_num),
            "source_timestamp": row_ts.isoformat(),
            "row_age_seconds": round(age, 3),
        }
        for canonical, aliases in _LIVE_SG_FIELD_ALIASES.items():
            val = _first_float(row, aliases)
            if val is not None:
                stats[canonical] = val

        if not _row_is_complete(stats):
            continue
        prev = by_player.get(pk)
        if prev is None or float(stats.get("row_age_seconds", 9999)) < float(prev.get("row_age_seconds", 9999)):
            by_player[pk] = stats

    accepted = len(by_player)
    fresh = accepted > 0 and (freshest_age is not None) and freshest_age <= ttl
    if fresh:
        mode = "full_live_stats"
        warning = None
    elif accepted > 0:
        mode = "stale_live_stats"
        warning = "Live stats present but outside freshness window."
    else:
        mode = "no_live_stats"
        warning = "No acceptable live stat rows in in-play payload."

    return by_player, {
        "live_stats_source": "datagolf_in_play",
        "live_stats_fetched_at": fetched.isoformat(),
        "live_stats_age_seconds": round(freshest_age, 3) if freshest_age is not None else None,
        "live_stats_fresh": fresh,
        "live_model_mode": mode,
        "live_stats_warning": warning,
        "players_accepted": accepted,
        "players_rejected_stale": rejected_stale,
    }


def live_sg_trajectory_trend(stats: dict[str, Any] | None) -> float | None:
    """Map current-round SG total into a momentum_trend-scale value for live SG Traj."""
    if not stats:
        return None
    sg = _safe_float(stats.get("round_sg_total"))
    if sg is None:
        return None
    return round(float(sg) * 0.35, 4)
