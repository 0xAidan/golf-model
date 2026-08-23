"""Local, cached player-profile projections for HTTP routes.

Profiles deliberately read only the SQLite ingestion store and live-refresh
snapshot. Data Golf fetching belongs to the refresh pipeline, never to a
request handler.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from backtester.dashboard_runtime import read_snapshot
from src import db
from src.player_normalizer import display_name

_CACHE_TTL_SECONDS = 30.0
_cache_lock = threading.Lock()
_profile_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _metric_value(row: dict[str, Any]) -> float | str | None:
    if row.get("metric_value") is not None:
        return _float(row["metric_value"])
    return row.get("metric_text")


def _latest_metrics(player_key: str) -> tuple[int | None, list[dict[str, Any]], str]:
    """Return the most recently ingested tournament metric set for a player."""
    conn = db.get_conn()
    try:
        latest = conn.execute(
            """SELECT tournament_id, MAX(rowid) AS version
               FROM metrics WHERE player_key = ? GROUP BY tournament_id
               ORDER BY version DESC LIMIT 1""",
            (player_key,),
        ).fetchone()
        if not latest:
            return None, [], "0"
        tournament_id = int(latest["tournament_id"])
        rows = conn.execute(
            """SELECT * FROM metrics WHERE tournament_id = ? AND player_key = ?
               ORDER BY metric_category, round_window, metric_name""",
            (tournament_id, player_key),
        ).fetchall()
        return tournament_id, [dict(row) for row in rows], str(latest["version"])
    finally:
        conn.close()


def _rounds_version(player_key: str) -> str:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS version FROM rounds WHERE player_key = ?",
            (player_key,),
        ).fetchone()
        return str(row["version"] if row else 0)
    finally:
        conn.close()


def _snapshot_player(player_key: str, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    for section_name in ("live_tournament", "upcoming_tournament"):
        section = snapshot.get(section_name)
        if not isinstance(section, dict):
            continue
        for row in section.get("rankings") or []:
            if str(row.get("player_key") or "").strip().lower() == player_key:
                return dict(row)
    return None


def _availability(metrics: list[dict[str, Any]], rounds: list[dict[str, Any]], snapshot_row: dict[str, Any] | None) -> dict[str, bool]:
    categories = {str(row.get("metric_category") or "") for row in metrics}
    return {
        "skill": "dg_skill" in categories,
        "rankings": "dg_ranking" in categories,
        "approach": "dg_approach" in categories,
        "rounds": bool(rounds),
        "snapshot": snapshot_row is not None,
    }


def _metrics_by_category(metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in metrics:
        category = str(row.get("metric_category") or "other")
        name = str(row.get("metric_name") or "value")
        value = _metric_value(row)
        if value is not None:
            grouped.setdefault(category, {})[name] = value
    return grouped


def _round_payload(round_row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "round_num", "event_name", "event_completed", "event_id", "course_name", "tour",
        "score", "sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "sg_t2g",
        "driving_dist", "driving_acc", "gir", "scrambling", "fin_text",
        # Recovered columns — already fetched via SELECT *, previously discarded.
        "birdies", "eagles_or_better", "bogies", "doubles_or_worse",
        "pars", "prox_fw", "prox_rgh", "great_shots", "poor_shots",
    )
    float_fields = (
        "sg_", "driving_", "gir", "scrambling",
        "prox_fw", "prox_rgh", "great_shots", "poor_shots",
    )
    payload: dict[str, Any] = {}
    for field in fields:
        value = round_row.get(field)
        payload[field] = _float(value) if field.startswith(float_fields) else value
    return payload


def _event_payload(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for row in rounds:
        key = f"{row.get('event_id') or row.get('event_name')}-{row.get('event_completed') or ''}"
        event = events.setdefault(key, {
            "event_name": row.get("event_name"), "event_completed": row.get("event_completed"),
            "event_id": row.get("event_id"), "course_name": row.get("course_name"),
            "tour": row.get("tour"), "fin_text": row.get("fin_text"), "rounds_played": 0,
            "score_values": [], "course_par_values": [],
            "values": {name: [] for name in ("sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "sg_t2g")},
        })
        event["rounds_played"] += 1
        score = _float(row.get("score"))
        if score is not None:
            event["score_values"].append(score)
        course_par = _float(row.get("course_par"))
        if course_par is not None:
            event["course_par_values"].append(course_par)
        for name, values in event["values"].items():
            value = _float(row.get(name))
            if value is not None:
                values.append(value)
    result = []
    for event in events.values():
        avg_score = _average(event["score_values"])
        avg_course_par = _average(event["course_par_values"])
        result.append({
            key: event[key] for key in ("event_name", "event_completed", "event_id", "course_name", "tour", "fin_text", "rounds_played")
        } | {
            "avg_score": avg_score,
            "avg_to_par": round(avg_score - avg_course_par, 3)
            if avg_score is not None and avg_course_par is not None else None,
        } | {f"avg_{name}": _average(values) for name, values in event["values"].items()})
    return sorted(result, key=lambda row: (row["event_completed"] or "", row["event_name"] or ""), reverse=True)[:30]


def _course_summaries(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    courses: dict[str, list[float]] = {}
    round_counts: dict[str, int] = {}
    for row in rounds:
        course_name = row.get("course_name")
        if not course_name:
            continue
        round_counts[course_name] = round_counts.get(course_name, 0) + 1
        value = _float(row.get("sg_total"))
        if value is not None:
            courses.setdefault(course_name, []).append(value)
    return sorted(
        (
            {
                "course_name": name,
                "rounds_played": round_counts[name],
                "avg_sg_total": _average(courses.get(name, [])),
            }
            for name in round_counts
        ),
        key=lambda row: (row["rounds_played"], row["avg_sg_total"] or -999),
        reverse=True,
    )[:8]


def build_standalone_profile(player_key: str) -> dict[str, Any]:
    """Build a player profile strictly from already-ingested local sources."""
    db.ensure_initialized()
    snapshot = read_snapshot() or {}
    tournament_id, metric_rows, metrics_version = _latest_metrics(player_key)
    rounds = db.get_player_recent_rounds_by_key(player_key, limit=120)
    snapshot_row = _snapshot_player(player_key, snapshot)
    cache_key = ":".join((
        player_key, metrics_version, _rounds_version(player_key),
        str(snapshot.get("snapshot_id") or snapshot.get("generated_at") or "0"),
    ))
    now = time.monotonic()
    with _cache_lock:
        cached = _profile_cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    grouped = _metrics_by_category(metric_rows)
    skill = grouped.get("dg_skill", {})
    rankings = grouped.get("dg_ranking", {})
    approach = grouped.get("dg_approach", {})
    player_display = next((row.get("player_display") for row in metric_rows if row.get("player_display")), None)
    player_display = player_display or next((row.get("player_name") for row in rounds if row.get("player_name")), None)
    player_display = player_display or (snapshot_row or {}).get("player") or display_name(player_key)
    sg_skills = {
        name: _float(skill.get(name))
        for name in ("sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "driving_dist", "driving_acc")
        if _float(skill.get(name)) is not None
    }
    approach_buckets = [
        {"key": name, "label": name.replace("_", " ").upper(), "value": _float(value)}
        for name, value in approach.items()
        if name.startswith("sg_") and _float(value) is not None
    ]
    approach_buckets.sort(key=lambda row: row["value"], reverse=True)
    sg_values = {
        name: [_float(row.get(name)) for row in rounds if _float(row.get(name)) is not None]
        for name in ("sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "sg_t2g")
    }
    rolling_windows_expanded = {
        name: {window: _average(values[:int(window)]) for window in ("10", "25", "50")}
        for name, values in sg_values.items()
    }
    recent_events = _event_payload(rounds)
    availability = _availability(metric_rows, rounds, snapshot_row)
    ranking_card = {
        "dg_rank": _float(rankings.get("dg_rank")) or (snapshot_row or {}).get("rank"),
        "owgr_rank": _float(rankings.get("owgr_rank")),
        "dg_skill_estimate": _float(rankings.get("dg_skill_estimate")),
        "primary_tour": rankings.get("primary_tour"),
        "player_name": player_display,
        "extra_scalars": {},
    }
    payload = {
        "player_key": player_key,
        "player_display": player_display,
        "header": {
            "player_display": player_display, **ranking_card,
            "rounds_in_db": len(rounds), "events_tracked": len(recent_events),
            "tournament_id": tournament_id,
        },
        "sg_skills": sg_skills,
        "approach_buckets": approach_buckets[:12],
        "rolling_windows": rolling_windows_expanded["sg_total"],
        "rolling_windows_expanded": rolling_windows_expanded,
        "trend_series": list(reversed(sg_values["sg_total"][:50])),
        "recent_events": recent_events,
        "recent_rounds_sample": [_round_payload(row) for row in rounds[:48]],
        "course_summaries": _course_summaries(rounds),
        "ranking_card": ranking_card,
        "ranking_data": rankings or None,
        "has_skill_data": availability["skill"],
        "has_ranking_data": availability["rankings"],
        "has_approach_data": availability["approach"],
        "availability": availability,
        "snapshot": snapshot_row,
        "cache": {"key": cache_key, "ttl_seconds": _CACHE_TTL_SECONDS},
    }
    with _cache_lock:
        _profile_cache[cache_key] = (now, payload)
        if len(_profile_cache) > 256:
            oldest_key = min(_profile_cache, key=lambda key: _profile_cache[key][0])
            _profile_cache.pop(oldest_key, None)
    return payload
