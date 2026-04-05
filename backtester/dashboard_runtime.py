"""
Always-on live refresh runtime for dashboard snapshots.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src import db
from src.live_refresh_policy import resolve_cadence
from src.services.live_snapshot_service import run_snapshot_analysis

_logger = logging.getLogger("dashboard.runtime")
_state_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None

_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "live_refresh_snapshot.json"


def _default_state() -> dict[str, Any]:
    return {
        "running": False,
        "tour": "pga",
        "cadence_mode": "off_window",
        "ingest_seconds": 1800,
        "recompute_seconds": 3600,
        "run_count": 0,
        "last_started_at": None,
        "last_finished_at": None,
        "last_error": None,
        "next_ingest_at": None,
        "next_recompute_at": None,
        "last_ingest_summary": None,
        "last_snapshot_generated_at": None,
    }


_state: dict[str, Any] = _default_state()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _write_snapshot(payload: dict[str, Any]) -> None:
    _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_snapshot() -> dict[str, Any]:
    if not _SNAPSHOT_PATH.exists():
        return {}
    try:
        return json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_live_schedule_event(event_row: dict[str, Any], *, today: date) -> bool:
    start_date = _parse_iso_date(event_row.get("start_date"))
    end_date = _parse_iso_date(event_row.get("end_date"))
    if not start_date or not end_date:
        return False
    return start_date <= today <= end_date


def _load_finish_state_map(event_id: str | None, *, year: int | None = None) -> dict[str, str]:
    if not event_id:
        return {}
    resolved_year = int(year or datetime.now(timezone.utc).year)
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT player_key, MAX(fin_text) AS fin_text
            FROM rounds
            WHERE event_id = ? AND year = ?
              AND fin_text IS NOT NULL
              AND TRIM(fin_text) != ''
            GROUP BY player_key
            """,
            (str(event_id), resolved_year),
        ).fetchall()
        finish_states: dict[str, str] = {}
        for row in rows:
            key = str(row["player_key"] or "").strip().lower()
            finish = str(row["fin_text"] or "").strip().upper()
            if key and finish:
                finish_states[key] = finish
        return finish_states
    finally:
        conn.close()


def _is_cut_or_inactive(finish_state: str | None) -> bool:
    if not finish_state:
        return False
    state = str(finish_state).strip().upper()
    return state in {"CUT", "MDF", "WD", "DQ", "DNS"}


def _extract_rankings(
    composite: list[dict],
    *,
    finish_states: dict[str, str] | None = None,
    exclude_cut_players: bool = False,
    limit: int = 30,
) -> list[dict]:
    rows = sorted(composite or [], key=lambda item: item.get("composite", 0), reverse=True)
    rankings: list[dict] = []
    finish_state_map = finish_states or {}
    rank = 0
    for row in rows:
        player_key = str(row.get("player_key") or "").strip().lower()
        finish_state = finish_state_map.get(player_key)
        if exclude_cut_players and _is_cut_or_inactive(finish_state):
            continue
        rank += 1
        rankings.append(
            {
                "rank": rank,
                "player_key": row.get("player_key"),
                "player": row.get("player_display"),
                "composite": row.get("composite"),
                "course_fit": row.get("course_fit"),
                "form": row.get("form"),
                "momentum": row.get("momentum"),
                "finish_state": finish_state,
            }
        )
        if rank >= limit:
            break
    return rankings


def _extract_matchups(matchups: list[dict], *, limit: int = 25) -> list[dict]:
    sorted_rows = sorted(matchups or [], key=lambda item: item.get("ev", 0), reverse=True)
    rows: list[dict] = []
    for row in sorted_rows[:limit]:
        rows.append(
            {
                "player": row.get("player") or row.get("pick"),
                "player_key": row.get("player_key") or row.get("pick_key"),
                "opponent": row.get("opponent"),
                "opponent_key": row.get("opponent_key"),
                "bookmaker": row.get("bookmaker") or row.get("book"),
                "market_odds": row.get("market_odds") or row.get("odds"),
                "model_prob": row.get("model_prob") or row.get("model_win_prob"),
                "ev": row.get("ev"),
                "market_type": row.get("market_type"),
            }
        )
    return rows


def _run_ingest(tour: str) -> dict[str, Any]:
    from src.datagolf import (
        fetch_matchup_odds,
        fetch_schedule,
        get_current_event_info,
        get_latest_completed_event_info,
    )

    event_info = get_current_event_info(tour) or {}
    schedule = fetch_schedule(tour=tour, upcoming_only=True)
    tournament_matchups = fetch_matchup_odds(market="tournament_matchups", tour=tour)
    three_ball = fetch_matchup_odds(market="3_balls", tour=tour)
    now_date = _utc_now().date()
    schedule_by_id = {str(row.get("event_id")): row for row in schedule if row.get("event_id")}
    event_id = str(event_info.get("event_id") or "")
    event_name = str(event_info.get("event_name") or "").strip()
    current_row = schedule_by_id.get(event_id)
    if current_row is None and event_name:
        current_row = next(
            (row for row in schedule if str(row.get("event_name") or "").strip().lower() == event_name.lower()),
            None,
        )
    current_idx = schedule.index(current_row) if current_row in schedule else None
    active_row = current_row if current_row else (schedule[0] if schedule else {})
    live_event_active = bool(active_row and _is_live_schedule_event(active_row, today=now_date))
    if current_idx is None:
        if live_event_active and len(schedule) > 1:
            upcoming_row = schedule[1]
        else:
            upcoming_row = schedule[0] if schedule else None
    else:
        if live_event_active:
            next_idx = current_idx + 1
            upcoming_row = schedule[next_idx] if next_idx < len(schedule) else None
        else:
            upcoming_row = schedule[current_idx]

    latest_completed = get_latest_completed_event_info(tour=tour, as_of=now_date) or {}
    return {
        "event_name": event_info.get("event_name"),
        "event_id": event_info.get("event_id"),
        "course": event_info.get("course"),
        "schedule_count": len(schedule),
        "live_event_active": live_event_active,
        "current_event_row": current_row,
        "upcoming_event_row": upcoming_row,
        "latest_completed_event_name": latest_completed.get("event_name"),
        "latest_completed_event_id": latest_completed.get("event_id"),
        "upcoming_event_names": [row.get("event_name") for row in schedule[:3] if row.get("event_name")],
        "market_counts": {
            "tournament_matchups": len(tournament_matchups),
            "three_ball": len(three_ball),
        },
    }


def _run_recompute(tour: str, cadence_mode: str, ingest_summary: dict[str, Any]) -> dict[str, Any]:
    mode = "full" if cadence_mode != "live_window" else "round-matchups"
    live_result = run_snapshot_analysis(
        tour=tour,
        mode=mode,
        enable_ai=False,
        enable_backfill=False,
    )
    generated_at = _iso_now()
    event_name = live_result.get("event_name") or ingest_summary.get("event_name")
    finish_states = _load_finish_state_map(ingest_summary.get("event_id"))
    section = {
        "event_name": event_name,
        "course_name": live_result.get("course_name"),
        "field_size": live_result.get("field_size"),
        "rankings": _extract_rankings(
            live_result.get("composite_results") or [],
            finish_states=finish_states,
            exclude_cut_players=False,
        ),
        "matchups": _extract_matchups(live_result.get("matchup_bets") or []),
        "card_path": live_result.get("output_file") or live_result.get("card_filepath"),
    }
    schedule_names = ingest_summary.get("upcoming_event_names") or []
    live_is_active = bool(ingest_summary.get("live_event_active"))
    live_event_name = event_name if live_is_active else (ingest_summary.get("latest_completed_event_name") or event_name)
    upcoming_row = ingest_summary.get("upcoming_event_row") or {}
    upcoming_event_name = str(upcoming_row.get("event_name") or "").strip()
    upcoming_course = str(upcoming_row.get("course") or "").split(";")[0].strip() or None
    if not upcoming_event_name:
        upcoming_event_name = schedule_names[1] if live_is_active and len(schedule_names) > 1 else (schedule_names[0] if schedule_names else event_name)

    upcoming_result = {}
    if upcoming_event_name:
        try:
            upcoming_result = run_snapshot_analysis(
                tour=tour,
                tournament_name=upcoming_event_name,
                course_name=upcoming_course,
                mode="full",
                enable_ai=False,
                enable_backfill=False,
            )
        except Exception as exc:
            _logger.warning("Upcoming snapshot recompute failed; falling back to live section: %s", exc)
            upcoming_result = {}

    if upcoming_result:
        upcoming_section = {
            "event_name": upcoming_result.get("event_name") or upcoming_event_name,
            "course_name": upcoming_result.get("course_name"),
            "field_size": upcoming_result.get("field_size"),
            "rankings": _extract_rankings(upcoming_result.get("composite_results") or [], exclude_cut_players=False),
            "matchups": _extract_matchups(upcoming_result.get("matchup_bets") or []),
            "card_path": upcoming_result.get("output_file") or upcoming_result.get("card_filepath"),
            "source_event_id": str(upcoming_row.get("event_id") or ""),
            "source_event_name": upcoming_event_name,
            "generated_from": "upcoming_event_model",
        }
    else:
        upcoming_section = {
            **section,
            "event_name": upcoming_event_name,
            "source_event_id": str(upcoming_row.get("event_id") or ""),
            "source_event_name": upcoming_event_name,
            "generated_from": "live_fallback",
        }

    snapshot = {
        "generated_at": generated_at,
        "cadence_mode": cadence_mode,
        "event_context": {
            "event_name": event_name,
            "event_id": ingest_summary.get("event_id"),
            "course": ingest_summary.get("course"),
            "upcoming_event_names": schedule_names,
        },
        "live_tournament": {
            **section,
            "event_name": live_event_name,
            "active": live_is_active,
            "rankings": _extract_rankings(
                live_result.get("composite_results") or [],
                finish_states=finish_states,
                exclude_cut_players=True,
            ),
            "source_event_id": str(ingest_summary.get("event_id") or ""),
            "source_event_name": event_name,
            "data_mode": mode,
            "source": "current_event_model",
        },
        "upcoming_tournament": {
            **upcoming_section,
            "active": True,
            "event_name": upcoming_section.get("event_name") or upcoming_event_name,
            "data_mode": "full",
            "source": "upcoming_event_model",
        },
    }
    _write_snapshot(snapshot)
    return snapshot


def _run_loop(tour: str) -> None:
    next_ingest = 0.0
    next_recompute = 0.0
    ingest_summary: dict[str, Any] = {}
    while not _stop_event.is_set():
        from src.autoresearch_settings import get_settings

        settings = get_settings().get("live_refresh", {})
        if not settings.get("enabled", False):
            with _state_lock:
                _state["cadence_mode"] = "off_window"
                _state["next_ingest_at"] = None
                _state["next_recompute_at"] = None
            if _stop_event.wait(5.0):
                break
            continue
        cadence = resolve_cadence(settings)
        now_epoch = time.time()
        with _state_lock:
            _state["cadence_mode"] = cadence.mode
            _state["ingest_seconds"] = cadence.ingest_seconds
            _state["recompute_seconds"] = cadence.recompute_seconds
        try:
            if now_epoch >= next_ingest:
                ingest_summary = _run_ingest(tour)
                with _state_lock:
                    _state["last_ingest_summary"] = ingest_summary
                    _state["next_ingest_at"] = datetime.fromtimestamp(now_epoch + cadence.ingest_seconds, timezone.utc).isoformat()
                next_ingest = now_epoch + cadence.ingest_seconds

            if now_epoch >= next_recompute:
                started_at = _iso_now()
                with _state_lock:
                    _state["last_started_at"] = started_at
                    _state["last_error"] = None
                snapshot = _run_recompute(tour, cadence.mode, ingest_summary)
                finished_at = _iso_now()
                with _state_lock:
                    _state["run_count"] += 1
                    _state["last_finished_at"] = finished_at
                    _state["last_snapshot_generated_at"] = snapshot.get("generated_at")
                    _state["next_recompute_at"] = datetime.fromtimestamp(now_epoch + cadence.recompute_seconds, timezone.utc).isoformat()
                next_recompute = now_epoch + cadence.recompute_seconds
        except Exception as exc:
            _logger.exception("Live refresh cycle failed")
            with _state_lock:
                _state["last_error"] = str(exc)
                _state["last_finished_at"] = _iso_now()
            # Short retry on failure.
            next_recompute = min(next_recompute, now_epoch + 30) if next_recompute else now_epoch + 30
        wait_target = min(next_ingest or now_epoch + 1, next_recompute or now_epoch + 1)
        sleep_for = max(1.0, wait_target - time.time())
        if _stop_event.wait(sleep_for):
            break
    with _state_lock:
        _state["running"] = False


def start_live_refresh(*, tour: str = "pga") -> dict[str, Any]:
    global _thread
    with _state_lock:
        if _state.get("running"):
            return dict(_state)
        _stop_event.clear()
        _state["running"] = True
        _state["tour"] = tour
        _state["last_error"] = None
    _thread = threading.Thread(target=_run_loop, args=(tour,), daemon=True, name="live-refresh-runtime")
    _thread.start()
    return get_live_refresh_status()


def stop_live_refresh() -> dict[str, Any]:
    global _thread
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)
    _thread = None
    with _state_lock:
        _state["running"] = False
    return get_live_refresh_status()


def get_live_refresh_status() -> dict[str, Any]:
    with _state_lock:
        status = dict(_state)
    snapshot = read_snapshot()
    generated_at = snapshot.get("generated_at")
    age_seconds = None
    if generated_at:
        try:
            generated_ts = datetime.fromisoformat(generated_at)
            age_seconds = max(0, int((_utc_now() - generated_ts).total_seconds()))
        except ValueError:
            age_seconds = None
    status["snapshot_age_seconds"] = age_seconds
    status["snapshot_available"] = bool(snapshot)
    return status

