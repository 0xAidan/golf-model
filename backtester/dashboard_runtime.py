"""
Always-on live refresh runtime for dashboard snapshots.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
import fcntl
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src import config, db
from src.atomic_io import atomic_write_json
from src.autoresearch_settings import get_settings
from src.datagolf import fetch_in_play_predictions, parse_in_play_leaderboard
from src.live_stats_source import live_sg_trajectory_trend, parse_live_stats_from_in_play
from src.disk_guard import warn_if_low_disk
from src.lab_profile import resolve_lab_model_variant
from src.live_refresh_policy import resolve_cadence
from src.player_normalizer import normalize_name
from src.runtime_paths import (
    detect_split_brain,
    get_app_root,
    get_cycle_lock_path,
    get_data_dir,
    get_heartbeat_path,
    get_manual_trigger_path,
    get_runtime_identity,
    get_snapshot_path,
    heartbeat_age_seconds,
    live_refresh_worker_owned,
    read_heartbeat,
)
from src.services.live_snapshot_service import run_lab_snapshot_analysis, run_snapshot_analysis

_logger = logging.getLogger("dashboard.runtime")
_state_lock = threading.Lock()
_recompute_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_last_snapshot_prune_at: float = 0.0
_last_heartbeat_touch: float = 0.0
_HEARTBEAT_TOUCH_INTERVAL_SECONDS = 60.0

_SNAPSHOT_PATH = get_snapshot_path()
_OUTPUT_DIR = get_app_root() / "output"
_DOWNLOADS_DIR = Path.home() / "Downloads"


def _default_state() -> dict[str, Any]:
    return {
        "running": False,
        "tour": "pga",
        "cadence_mode": "off_window",
        "ingest_seconds": 3600,
        "recompute_seconds": 3600,
        "run_count": 0,
        "last_started_at": None,
        "last_finished_at": None,
        "last_error": None,
        "next_ingest_at": None,
        "next_recompute_at": None,
        "last_ingest_summary": None,
        "last_snapshot_generated_at": None,
        "last_auto_grade_at": None,
        "last_auto_grade_status": None,
        "refresh_state": "idle",
        "phase": None,
        "phase_detail": None,
        "progress_updated_at": None,
        "progress_started_at": None,
        "recompute_percent": None,
    }


_state: dict[str, Any] = _default_state()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


class LiveRefreshRecomputeBusy(RuntimeError):
    """Non-blocking recompute could not start because another thread holds the recompute lock."""


class _CrossProcessCycleLock:
    """fcntl lock spanning dashboard + worker processes for one ingest+recompute cycle."""

    def __init__(self) -> None:
        self._fd: int | None = None

    def acquire(self, *, blocking: bool = False) -> bool:
        path = get_cycle_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


_cross_process_cycle_lock = _CrossProcessCycleLock()


def _snapshot_path() -> Path:
    return get_snapshot_path()


def _write_heartbeat(**extra: Any) -> None:
    with _state_lock:
        running = bool(_state.get("running"))
        phase = _state.get("phase")
        refresh_state = _state.get("refresh_state")
        last_error = _state.get("last_error")
    payload = {
        **get_runtime_identity(),
        "updated_at": _iso_now(),
        "running": running,
        "worker_pid": os.getpid(),
        "phase": phase,
        "refresh_state": refresh_state,
        "last_error": last_error,
        **extra,
    }
    atomic_write_json(get_heartbeat_path(), payload)


def request_manual_refresh(*, requested_by: str = "api") -> dict[str, Any]:
    path = get_manual_trigger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "request_id": str(uuid.uuid4()),
        "requested_at": _iso_now(),
        "requested_by": requested_by,
    }
    atomic_write_json(path, payload)
    return payload


def manual_trigger_pending() -> bool:
    return get_manual_trigger_path().is_file()


def consume_manual_trigger() -> dict[str, Any] | None:
    path = get_manual_trigger_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        path.unlink(missing_ok=True)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def worker_is_available(*, max_heartbeat_age_seconds: int = 900) -> bool:
    heartbeat = read_heartbeat()
    if not heartbeat:
        return False
    age = heartbeat_age_seconds(heartbeat)
    if age is None or age > max_heartbeat_age_seconds:
        return False
    return bool(heartbeat.get("running"))


def cycle_lock_is_held() -> bool:
    if not _cross_process_cycle_lock.acquire(blocking=False):
        return True
    _cross_process_cycle_lock.release()
    return False


def _touch_progress(
    *,
    refresh_state: str | None = None,
    phase: str | None = None,
    phase_detail: str | None = None,
    recompute_percent: float | None = None,
    last_error: str | None = None,
    idle: bool = False,
) -> None:
    """Update coarse-grained progress fields for the live-refresh status API."""
    with _state_lock:
        if idle:
            if last_error is not None:
                _state["last_error"] = last_error
                _state["refresh_state"] = "error"
            else:
                _state["refresh_state"] = "idle"
                _state["last_error"] = None
            _state["phase"] = None
            _state["phase_detail"] = None
            _state["recompute_percent"] = None
            _state["progress_started_at"] = None
            _state["progress_updated_at"] = _iso_now()
            return
        if refresh_state is not None:
            _state["refresh_state"] = refresh_state
            if refresh_state == "running":
                _state["progress_started_at"] = _iso_now()
        if phase is not None:
            _state["phase"] = phase
        if phase_detail is not None:
            _state["phase_detail"] = phase_detail
        if recompute_percent is not None:
            _state["recompute_percent"] = recompute_percent
        if last_error is not None:
            _state["last_error"] = last_error
        _state["progress_updated_at"] = _iso_now()
    _maybe_refresh_heartbeat()


def _maybe_refresh_heartbeat() -> None:
    """Keep worker heartbeat fresh during long recompute phases (cross-process liveness)."""
    global _last_heartbeat_touch
    with _state_lock:
        if _state.get("refresh_state") != "running":
            return
    now_ts = time.time()
    if _last_heartbeat_touch and (now_ts - _last_heartbeat_touch) < _HEARTBEAT_TOUCH_INTERVAL_SECONDS:
        return
    _write_heartbeat()
    _last_heartbeat_touch = now_ts


def _recompute_timeout_seconds() -> float:
    raw = os.environ.get("LIVE_REFRESH_RECOMPUTE_TIMEOUT_S", "2700")
    try:
        return max(300.0, float(raw))
    except (TypeError, ValueError):
        return 2700.0


def _shadow_mc_timeout_seconds() -> float:
    raw = os.environ.get("LIVE_REFRESH_SHADOW_MC_TIMEOUT_S", "300")
    try:
        return max(30.0, float(raw))
    except (TypeError, ValueError):
        return 300.0


def _run_recompute_with_timeout(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run _run_recompute in a helper thread so the loop can enforce a hard ceiling."""
    timeout_s = _recompute_timeout_seconds()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-refresh-recompute") as pool:
        future = pool.submit(_run_recompute, *args, **kwargs)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeoutError as exc:
            raise TimeoutError(
                f"Live refresh recompute exceeded {int(timeout_s)}s timeout"
            ) from exc


def _run_shadow_monte_carlo_with_timeout(**kwargs: Any) -> int:
    timeout_s = _shadow_mc_timeout_seconds()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-refresh-shadow-mc") as pool:
        future = pool.submit(_run_shadow_monte_carlo_v1, **kwargs)
        try:
            return int(future.result(timeout=timeout_s) or 0)
        except FuturesTimeoutError:
            _logger.warning(
                "shadow Monte Carlo batch exceeded %ss timeout; skipping (snapshot already published)",
                int(timeout_s),
            )
            return 0


_DATA_SOURCE_VALUES = {"live", "replay", "fixture"}


def _resolve_data_source() -> str:
    """Classify the snapshot's data origin so the UI can surface it.

    Derived from the same environment toggles that drive the refresh path:
    `GOLF_DATA_SOURCE` (explicit override) wins; otherwise any active
    fixture/replay env markers map to their labels, defaulting to "live".
    """
    explicit = (os.environ.get("GOLF_DATA_SOURCE") or "").strip().lower()
    if explicit in _DATA_SOURCE_VALUES:
        return explicit
    if (os.environ.get("GOLF_USE_FIXTURES") or "").strip().lower() in {"1", "true", "yes"}:
        return "fixture"
    if (os.environ.get("GOLF_REPLAY_MODE") or "").strip().lower() in {"1", "true", "yes"}:
        return "replay"
    return "live"


def _write_snapshot(payload: dict[str, Any]) -> None:
    atomic_write_json(_snapshot_path(), payload)
    _write_heartbeat(last_snapshot_generated_at=payload.get("generated_at"))


def _cap_list_rows(rows: Any, *, max_rows: int) -> list[Any]:
    if not isinstance(rows, list):
        return []
    if max_rows <= 0:
        return []
    if len(rows) <= max_rows:
        return rows
    return rows[:max_rows]


def _trim_snapshot_section_for_memory(section: dict[str, Any]) -> dict[str, Any]:
    """Bound large arrays in a section to prevent runaway snapshot memory size."""
    if not isinstance(section, dict):
        return section
    trimmed = dict(section)
    trimmed["matchup_bets_all_books"] = _cap_list_rows(
        section.get("matchup_bets_all_books") or section.get("matchup_bets") or [],
        max_rows=max(0, int(config.SNAPSHOT_MATCHUPS_ALL_BOOKS_MAX_ROWS)),
    )
    diagnostics = trimmed.get("diagnostics")
    if isinstance(diagnostics, dict):
        diag_copy = dict(diagnostics)
        diag_copy["failed_candidates"] = _cap_list_rows(
            diagnostics.get("failed_candidates") or [],
            max_rows=max(0, int(config.SNAPSHOT_FAILED_CANDIDATES_MAX_ROWS)),
        )
        trimmed["diagnostics"] = diag_copy
    return trimmed


def _maybe_prune_snapshot_history_tables(snapshot: dict[str, Any]) -> None:
    """Prune append-heavy history tables periodically to enforce retention."""
    global _last_snapshot_prune_at
    interval_seconds = max(60, int(config.SNAPSHOT_HISTORY_PRUNE_INTERVAL_SECONDS))
    now_ts = time.time()
    if _last_snapshot_prune_at and (now_ts - _last_snapshot_prune_at) < interval_seconds:
        return

    retain_days = max(1, int(config.SNAPSHOT_HISTORY_RETAIN_DAYS))
    try:
        prune_result = db.prune_snapshot_history_tables(retain_days=retain_days)
        _last_snapshot_prune_at = now_ts
        snapshot.setdefault("diagnostics", {})["history_prune"] = prune_result
    except Exception as exc:
        snapshot.setdefault("diagnostics", {})["history_prune"] = {
            "skipped": True,
            "reason": f"prune_failed: {exc}",
        }
        _logger.warning("Snapshot history prune failed: %s", exc)


def read_snapshot() -> dict[str, Any]:
    path = _snapshot_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    from src.datagolf import is_schedule_event_live

    return is_schedule_event_live(event_row, today=today)


def _has_started_schedule_event(event_row: dict[str, Any], *, today: date) -> bool:
    start_date = _parse_iso_date(event_row.get("start_date"))
    if not start_date:
        return False
    return start_date <= today


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


def _merge_in_play_finish_states(
    db_states: dict[str, str] | None,
    leaderboard_rows: list[dict] | None,
) -> dict[str, str]:
    from src.datagolf import normalize_in_play_finish_state

    merged = dict(db_states or {})
    for row in leaderboard_rows or []:
        pk = str(row.get("player_key") or "").strip().lower()
        finish = row.get("finish_state")
        if not finish:
            finish = normalize_in_play_finish_state(
                row.get("position") or row.get("current_pos") or row.get("dg_position")
            )
        if pk and finish:
            merged[pk] = str(finish).strip().upper()
    return merged


def _is_cut_or_inactive(finish_state: str | None) -> bool:
    if not finish_state:
        return False
    state = str(finish_state).strip().upper()
    return state in {"CUT", "MC", "MDF", "WD", "DQ", "DNS"}


def _finish_rank_from_text(finish_state: str | None) -> int | None:
    if not finish_state:
        return None
    normalized = str(finish_state).strip().upper()
    if normalized.startswith("T"):
        normalized = normalized[1:]
    if normalized.isdigit():
        try:
            return int(normalized)
        except ValueError:
            return None
    return None


def _load_event_leaderboard_rows(
    event_id: str | None,
    *,
    year: int | None = None,
    limit: int = 30,
) -> list[dict]:
    if not event_id:
        return []
    resolved_year = int(year or datetime.now(timezone.utc).year)
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            WITH latest_round AS (
                SELECT player_key, MAX(round_num) AS latest_round_num
                FROM rounds
                WHERE event_id = ? AND year = ?
                GROUP BY player_key
            )
            SELECT
                r.player_key,
                MAX(r.player_name) AS player_name,
                MAX(
                    CASE
                        WHEN r.fin_text IS NOT NULL AND TRIM(r.fin_text) != '' THEN r.fin_text
                        ELSE NULL
                    END
                ) AS finish_state,
                SUM(
                    CASE
                        WHEN r.score IS NOT NULL AND r.course_par IS NOT NULL THEN (r.score - r.course_par)
                        ELSE 0
                    END
                ) AS total_to_par,
                MAX(r.round_num) AS latest_round_num,
                MAX(CASE WHEN r.round_num = lr.latest_round_num THEN r.score END) AS latest_round_score,
                COUNT(CASE WHEN r.score IS NOT NULL THEN 1 END) AS rounds_played
            FROM rounds r
            JOIN latest_round lr ON lr.player_key = r.player_key
            WHERE r.event_id = ? AND r.year = ?
            GROUP BY r.player_key
            """,
            (str(event_id), resolved_year, str(event_id), resolved_year),
        ).fetchall()
    finally:
        conn.close()

    leaderboard_rows: list[dict] = []
    for row in rows:
        player_key = str(row["player_key"] or "").strip().lower()
        player_name = str(row["player_name"] or "").strip()
        if not player_key or not player_name:
            continue
        finish_state = str(row["finish_state"] or "").strip().upper() or None
        finish_rank = _finish_rank_from_text(finish_state)
        total_to_par_raw = row["total_to_par"]
        total_to_par = int(total_to_par_raw) if total_to_par_raw is not None else None
        latest_round_num_raw = row["latest_round_num"]
        latest_round_num = int(latest_round_num_raw) if latest_round_num_raw is not None else None
        latest_round_score_raw = row["latest_round_score"]
        latest_round_score = int(latest_round_score_raw) if latest_round_score_raw is not None else None
        rounds_played_raw = row["rounds_played"]
        rounds_played = int(rounds_played_raw) if rounds_played_raw is not None else 0
        leaderboard_rows.append(
            {
                "player_key": player_key,
                "player": player_name,
                "finish_state": finish_state,
                "finish_rank": finish_rank,
                "total_to_par": total_to_par,
                "latest_round_num": latest_round_num,
                "latest_round_score": latest_round_score,
                "rounds_played": rounds_played,
            }
        )

    leaderboard_rows.sort(
        key=lambda row: (
            row["finish_rank"] is None,
            row["finish_rank"] if row["finish_rank"] is not None else 9999,
            row["total_to_par"] if row["total_to_par"] is not None else 9999,
            row["player"],
        )
    )

    output: list[dict] = []
    for idx, row in enumerate(leaderboard_rows[:limit], start=1):
        display_position = row["finish_state"] or str(idx)
        output.append(
            {
                "rank": idx,
                "position": display_position,
                "player_key": row["player_key"],
                "player": row["player"],
                "total_to_par": row["total_to_par"],
                "latest_round_num": row["latest_round_num"],
                "latest_round_score": row["latest_round_score"],
                "rounds_played": row["rounds_played"],
                "finish_state": row["finish_state"],
            }
        )
    return output


def _extract_rankings(
    composite: list[dict],
    *,
    finish_states: dict[str, str] | None = None,
    exclude_cut_players: bool = False,
    limit: int | None = None,
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
        entry: dict = {
            "rank": rank,
            "player_key": row.get("player_key"),
            "player": row.get("player_display"),
            "composite": row.get("composite"),
            "course_fit": row.get("course_fit"),
            "form": row.get("form"),
            "momentum": row.get("momentum"),
            "momentum_direction": row.get("momentum_direction"),
            "momentum_trend": row.get("momentum_trend"),
            "course_confidence": row.get("course_confidence"),
            "course_rounds": row.get("course_rounds"),
            "weather_adjustment": row.get("weather_adjustment"),
            "finish_state": finish_state,
            "availability": row.get("availability"),
            "form_flags": row.get("form_flags") or [],
            "form_notes": row.get("form_notes") or [],
        }
        details = row.get("details")
        if details:
            entry["details"] = details
            if not entry.get("availability") and details.get("availability"):
                entry["availability"] = details.get("availability")
        rankings.append(entry)
        if limit is not None and rank >= limit:
            break
    return rankings


def _median_float(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    if len(s) % 2 == 1:
        return float(s[len(s) // 2])
    mid = len(s) // 2
    return (float(s[mid - 1]) + float(s[mid])) / 2.0


def _build_live_point_in_time_rankings(
    composite_results: list[dict],
    leaderboard_rows: list[dict],
    *,
    finish_states: dict[str, str] | None,
    exclude_cut_players: bool,
    dg_win_prob: dict[str, float] | None,
    live_stats_by_player: dict[str, dict[str, Any]] | None = None,
    live_stats_fresh: bool = False,
) -> tuple[list[dict], str]:
    """
    Re-rank pre-tournament composite scores using current tournament state (DG live or DB leaderboard).

    When Data Golf in-play win probabilities are available, blend them into the sort key so the
    live board tracks the event rather than static pre-tournament ordering.
    """
    finish_state_map = finish_states or {}
    ttp_map: dict[str, int] = {}
    for row in leaderboard_rows or []:
        pk = str(row.get("player_key") or "").strip().lower()
        if not pk:
            continue
        ttp = row.get("total_to_par")
        if ttp is None:
            continue
        try:
            ttp_map[pk] = int(ttp)
        except (TypeError, ValueError):
            continue
    dg_w = dg_win_prob or {}
    live_stats = live_stats_by_player or {}
    ttps_list = list(ttp_map.values())
    has_spread = len(ttps_list) >= 2 and len(set(ttps_list)) > 1
    has_win_signal = len(dg_w) > 0
    if not has_win_signal and not has_spread:
        # No tournament signal (e.g. DB fallback with all zeros, or parse missed scores): do not
        # pretend point-in-time ordering — that degenerates to pure pre-tournament composite.
        return (
            _extract_rankings(
                composite_results,
                finish_states=finish_states,
                exclude_cut_players=exclude_cut_players,
            ),
            "live_point_in_time_pre_tournament_fallback",
        )
    ttps = [float(v) for v in ttp_map.values()]
    median_ttp = _median_float(ttps) if ttps else 0.0
    scored: list[tuple[float, float, dict]] = []
    for row in composite_results or []:
        pk = str(row.get("player_key") or "").strip().lower()
        if not pk:
            continue
        finish_state = finish_state_map.get(pk)
        if exclude_cut_players and _is_cut_or_inactive(finish_state):
            continue
        base = float(row.get("composite") or 0)
        ttp = ttp_map.get(pk)
        if dg_w and pk in dg_w:
            adjusted = base + 25.0 * float(dg_w[pk])
        else:
            gap = median_ttp - float(ttp if ttp is not None else median_ttp)
            adjusted = base + 0.12 * gap
        if live_stats_fresh:
            player_stats = live_stats.get(pk) or {}
            sg_total = player_stats.get("round_sg_total")
            if sg_total is not None:
                try:
                    adjusted += 1.5 * float(sg_total)
                except (TypeError, ValueError):
                    pass
            thru = player_stats.get("thru")
            if thru is not None:
                try:
                    adjusted += 0.02 * float(thru)
                except (TypeError, ValueError):
                    pass
        scored.append((adjusted, base, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    rankings: list[dict] = []
    rank = 0
    for adjusted, base, row in scored:
        rank += 1
        pk = str(row.get("player_key") or "").strip().lower()
        finish_state = finish_state_map.get(pk)
        entry: dict[str, Any] = {
            "rank": rank,
            "player_key": row.get("player_key"),
            "player": row.get("player_display"),
            "composite": round(adjusted, 3),
            "pre_tournament_composite": base,
            "course_fit": row.get("course_fit"),
            "form": row.get("form"),
            "momentum": row.get("momentum"),
            "momentum_direction": row.get("momentum_direction"),
            "momentum_trend": row.get("momentum_trend"),
            "course_confidence": row.get("course_confidence"),
            "course_rounds": row.get("course_rounds"),
            "weather_adjustment": row.get("weather_adjustment"),
            "finish_state": finish_state,
            "availability": row.get("availability"),
            "form_flags": row.get("form_flags") or [],
            "form_notes": row.get("form_notes") or [],
        }
        details = row.get("details")
        if details:
            entry["details"] = details
        rankings.append(entry)
    if live_stats_fresh and live_stats:
        source_used = "live_point_in_time_model_live_stats_blend"
    elif (
        dg_w
        and scored
        and any(str(r.get("player_key") or "").strip().lower() in dg_w for _, _, r in scored)
    ):
        source_used = "live_point_in_time_model_dg_blend"
    else:
        source_used = "live_point_in_time_model_tournament_state"
    return rankings, source_used


def _maybe_freeze_pre_teeoff(
    *,
    live_event_id: str,
    tour: str,
    live_event_name: str | None,
    snapshot_id: str,
    previous_snapshot: dict[str, Any] | None,
) -> None:
    """Freeze the last verified upcoming board for this event once it goes live."""
    if not live_event_id or db.has_pre_teeoff_frozen(live_event_id):
        return
    cand = db.get_pre_teeoff_candidate_payload(live_event_id)
    if not cand:
        prev = (previous_snapshot or {}).get("upcoming_tournament") or {}
        if str(prev.get("source_event_id") or "").strip() == str(live_event_id).strip():
            cand = prev
    if not cand:
        return
    db.insert_pre_teeoff_frozen(
        live_event_id,
        tour=tour,
        event_name=str(cand.get("event_name") or live_event_name or "").strip() or None,
        section_payload=cand,
        source_snapshot_id=snapshot_id,
    )
    try:
        from src.pick_ledger import persist_pick_ledger_from_section

        persist_pick_ledger_from_section(
            cand,
            section="frozen",
            snapshot_id=snapshot_id,
            generated_at=_iso_now(),
            lifecycle="frozen_pre_teeoff",
            source_origin="freeze",
        )
    except Exception as exc:
        _logger.warning("Failed to persist frozen pre-teeoff ledger rows: %s", exc)
    try:
        from datetime import datetime, timezone

        from src.event_pick_freeze import capture_pre_teeoff_picks

        year = datetime.now(timezone.utc).year
        inserted = capture_pre_teeoff_picks(
            live_event_id,
            year=year,
            event_name=str(cand.get("event_name") or live_event_name or "").strip() or None,
            section_payload=cand,
        )
        if inserted:
            _logger.info(
                "Pre-teeoff capture: %s +EV picks frozen for event %s",
                inserted,
                live_event_id,
            )
    except Exception as exc:
        _logger.warning("Failed to capture pre-teeoff picks: %s", exc)


_NON_BOOK_SOURCES = {"datagolf"}


def _is_non_book_source(value: Any) -> bool:
    return str(value or "").strip().lower() in _NON_BOOK_SOURCES


def _extract_matchups(matchups: list[dict], *, limit: int = 25) -> list[dict]:
    filtered = [
        m for m in (matchups or [])
        if not _is_non_book_source(m.get("bookmaker") or m.get("book"))
    ]
    sorted_rows = sorted(filtered, key=lambda item: item.get("ev", 0), reverse=True)
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
                "tier": row.get("tier"),
                "conviction": row.get("conviction"),
                "composite_gap": row.get("composite_gap"),
                "form_gap": row.get("form_gap"),
                "course_fit_gap": row.get("course_fit_gap"),
                "pick_momentum": row.get("pick_momentum"),
                "opp_momentum": row.get("opp_momentum"),
                "momentum_aligned": row.get("momentum_aligned"),
            }
        )
    return rows


def _extract_board_matchup_bets(matchups: list[dict]) -> list[dict]:
    filtered = [
        dict(row)
        for row in (matchups or [])
        if not _is_non_book_source(row.get("book") or row.get("bookmaker"))
    ]
    filtered.sort(key=lambda item: item.get("ev", 0), reverse=True)

    for row in filtered:
        if not row.get("pick") and row.get("player"):
            row["pick"] = row.get("player")
        if not row.get("pick_key") and row.get("player_key"):
            row["pick_key"] = row.get("player_key")
        if row.get("book") is None and row.get("bookmaker") is not None:
            row["book"] = row.get("bookmaker")
        if row.get("odds") is None and row.get("market_odds") is not None:
            row["odds"] = row.get("market_odds")
        if row.get("model_win_prob") is None and row.get("model_prob") is not None:
            row["model_win_prob"] = row.get("model_prob")
        if row.get("ev_pct") is None and row.get("ev") is not None:
            row["ev_pct"] = f"{float(row['ev']) * 100:.1f}%"
        if not row.get("reason"):
            row["reason"] = "Hydrated from always-on snapshot"

    return filtered


def _extract_board_value_bets(
    value_bets: dict[str, list[dict]],
    *,
    return_diagnostics: bool = False,
) -> dict[str, list[dict]] | tuple[dict[str, list[dict]], dict[str, int]]:
    extracted: dict[str, list[dict]] = {}
    diagnostics = {
        "missing_display_odds": 0,
        "ev_cap_filtered": 0,
        "probability_inconsistency_filtered": 0,
    }
    for market, bets in (value_bets or {}).items():
        filtered: list[dict] = []
        for bet in bets or []:
            if not bet.get("is_value"):
                continue
            if _is_non_book_source(bet.get("book") or bet.get("best_book")):
                continue
            if bet.get("ev_capped"):
                diagnostics["ev_cap_filtered"] += 1
                continue
            if bet.get("suspicious"):
                diagnostics["probability_inconsistency_filtered"] += 1
                continue
            odds_text = _normalize_market_odds(bet.get("odds"), bet.get("best_odds"))
            if not odds_text:
                diagnostics["missing_display_odds"] += 1
                continue
            row = dict(bet)
            row["odds"] = odds_text
            filtered.append(row)
        filtered.sort(key=lambda item: item.get("ev", 0), reverse=True)
        if filtered:
            extracted[market] = filtered
    if return_diagnostics:
        return extracted, diagnostics
    return extracted


def _normalize_market_odds(value: Any, fallback: Any = None) -> str | None:
    candidate = value if value not in (None, "", "n/a") else fallback
    if candidate in (None, "", "n/a"):
        return None
    if isinstance(candidate, (int, float)):
        number = int(candidate)
        return f"+{number}" if number > 0 else str(number)
    text = str(candidate).strip()
    return text or None


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_player_key(value: Any, *, fallback_name: Any = None) -> str:
    key = str(value or "").strip().lower()
    if key:
        return key
    name = str(fallback_name or "").strip()
    if not name:
        return ""
    return normalize_name(name)


def _parse_position_rank(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip().upper()
    if not text:
        return None
    if text.startswith("T"):
        text = text[1:]
    if not text.isdigit():
        return None
    parsed = _coerce_int(text)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _build_rank_baseline_map(rows: list[dict]) -> dict[str, dict[str, Any]]:
    baseline: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows or [], start=1):
        key = _normalize_player_key(row.get("player_key"), fallback_name=row.get("player"))
        if not key:
            continue
        rank = _coerce_int(row.get("rank")) or idx
        baseline[key] = {
            "rank": rank,
            "composite": _coerce_float(row.get("composite")),
            "player": row.get("player"),
        }
    return baseline


def _build_leaderboard_lookup(
    rows: list[dict],
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows or [], start=1):
        key = _normalize_player_key(row.get("player_key"), fallback_name=row.get("player"))
        if not key:
            continue
        position_label = str(row.get("position") or row.get("finish_state") or "").strip()
        rank = _parse_position_rank(row.get("rank"))
        if rank is None:
            rank = _parse_position_rank(position_label)
        if rank is None:
            rank = idx
        lookup[key] = {
            "rank": rank,
            "position": position_label or (f"T{rank}" if str(position_label).upper().startswith("T") else str(rank)),
            "player": row.get("player"),
            "total_to_par": _coerce_int(row.get("total_to_par")),
            "source": source,
        }
    return lookup


def _build_leaderboard_baseline_map(
    *,
    event_id: str,
    frozen_section: dict[str, Any] | None,
    history_section: str,
) -> dict[str, dict[str, Any]]:
    baseline: dict[str, dict[str, Any]] = {}
    frozen_rows = (frozen_section or {}).get("leaderboard") or []
    baseline.update(_build_leaderboard_lookup(frozen_rows, source="tee_off_frozen"))
    if not event_id:
        return baseline
    first_snapshot = db.get_first_snapshot_section(event_id, section=history_section)
    first_rows = ((first_snapshot or {}).get("snapshot") or {}).get("leaderboard") or []
    first_lookup = _build_leaderboard_lookup(first_rows, source="since_live_start")
    for key, row in first_lookup.items():
        baseline.setdefault(key, row)
    return baseline


def _enrich_leaderboard_rows(
    rows: list[dict],
    *,
    baseline_lookup: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], str]:
    enriched: list[dict[str, Any]] = []
    joined_lookup: dict[str, dict[str, Any]] = {}
    default_source = "tee_off_frozen" if any(
        str(item.get("source") or "").strip() == "tee_off_frozen"
        for item in baseline_lookup.values()
    ) else "since_live_start"
    observed_sources: set[str] = set()
    for idx, row in enumerate(rows or [], start=1):
        item = dict(row or {})
        key = _normalize_player_key(item.get("player_key"), fallback_name=item.get("player"))
        current_rank = _parse_position_rank(item.get("rank"))
        if current_rank is None:
            current_rank = _parse_position_rank(item.get("position"))
        if current_rank is None:
            current_rank = idx
        position_label = str(item.get("position") or "").strip() or str(current_rank)
        baseline_row = baseline_lookup.get(key) if key else None
        if baseline_row is None:
            baseline_row = {
                "rank": current_rank,
                "position": position_label,
                "source": default_source,
                "total_to_par": _coerce_int(item.get("total_to_par")),
            }
            if key:
                baseline_lookup[key] = baseline_row
        start_rank = _coerce_int(baseline_row.get("rank"))
        start_position = str(baseline_row.get("position") or "").strip() or (str(start_rank) if start_rank else None)
        delta = (start_rank - current_rank) if (start_rank is not None and current_rank is not None) else None
        baseline_source = str(baseline_row.get("source") or default_source).strip() or default_source
        observed_sources.add(baseline_source)
        item["leaderboard_rank"] = current_rank
        item["leaderboard_position"] = position_label
        item["start_leaderboard_rank"] = start_rank
        item["start_leaderboard_position"] = start_position
        item["leaderboard_delta"] = delta
        item["leaderboard_baseline_source"] = baseline_source
        enriched.append(item)
        if key:
            joined_lookup[key] = {
                "leaderboard_rank": current_rank,
                "leaderboard_position": position_label,
                "start_leaderboard_rank": start_rank,
                "start_leaderboard_position": start_position,
                "leaderboard_delta": delta,
                "leaderboard_baseline_source": baseline_source,
                "total_to_par": _coerce_int(item.get("total_to_par")),
            }
    if "tee_off_frozen" in observed_sources:
        baseline_label = "frozen_at_tee_off"
    elif "since_live_start" in observed_sources:
        baseline_label = "since_live_start"
    else:
        baseline_label = default_source
    return enriched, joined_lookup, baseline_label


def _enrich_static_rankings(rows: list[dict], *, ranking_source: str) -> list[dict]:
    enriched: list[dict] = []
    for idx, row in enumerate(rows or [], start=1):
        item = dict(row or {})
        current_rank = _coerce_int(item.get("rank")) or idx
        baseline_rank = _coerce_int(item.get("start_rank")) or current_rank
        baseline_composite = _coerce_float(item.get("start_composite"))
        if baseline_composite is None:
            baseline_composite = _coerce_float(item.get("pre_tournament_composite"))
        if baseline_composite is None:
            baseline_composite = _coerce_float(item.get("composite"))
        item["current_rank"] = current_rank
        item["start_rank"] = baseline_rank
        item["rank_delta"] = baseline_rank - current_rank
        item["start_composite"] = baseline_composite
        item["pre_tournament_composite"] = baseline_composite
        item.setdefault("ranking_source", ranking_source)
        enriched.append(item)
    return enriched


def _enrich_live_rankings(
    rows: list[dict],
    *,
    pre_baseline: dict[str, dict[str, Any]],
    frozen_baseline: dict[str, dict[str, Any]],
    leaderboard_lookup: dict[str, dict[str, Any]],
    ranking_source: str,
    live_point_in_time_source: str | None,
) -> list[dict]:
    enriched: list[dict] = []
    for idx, row in enumerate(rows or [], start=1):
        item = dict(row or {})
        key = _normalize_player_key(item.get("player_key"), fallback_name=item.get("player"))
        baseline = frozen_baseline.get(key) or pre_baseline.get(key) or {}
        current_rank = _coerce_int(item.get("rank")) or idx
        start_rank = _coerce_int(baseline.get("rank"))
        start_composite = _coerce_float(baseline.get("composite"))
        pre_tournament_composite = _coerce_float(item.get("pre_tournament_composite"))
        if pre_tournament_composite is None:
            pre_tournament_composite = start_composite
        if start_composite is None:
            start_composite = pre_tournament_composite
        rank_delta = (start_rank - current_rank) if (start_rank is not None) else None
        item["current_rank"] = current_rank
        item["start_rank"] = start_rank
        item["rank_delta"] = rank_delta
        item["start_composite"] = start_composite
        item["pre_tournament_composite"] = pre_tournament_composite
        item["ranking_source"] = ranking_source
        item["live_point_in_time_source"] = live_point_in_time_source
        scoring = leaderboard_lookup.get(key) or {}
        item["leaderboard_rank"] = scoring.get("leaderboard_rank")
        item["leaderboard_position"] = scoring.get("leaderboard_position")
        item["start_leaderboard_rank"] = scoring.get("start_leaderboard_rank")
        item["start_leaderboard_position"] = scoring.get("start_leaderboard_position")
        item["leaderboard_delta"] = scoring.get("leaderboard_delta")
        item["leaderboard_baseline_source"] = scoring.get("leaderboard_baseline_source")
        item["total_to_par"] = scoring.get("total_to_par")
        enriched.append(item)
    return enriched


def _build_live_player_board(
    live_rankings: list[dict],
    *,
    live_stats_by_player: dict[str, dict[str, Any]] | None = None,
    live_stats_fresh: bool = False,
) -> list[dict]:
    live_stats = live_stats_by_player or {}
    board: list[dict] = []
    for row in live_rankings or []:
        pk = str(row.get("player_key") or "").strip().lower()
        player_stats = live_stats.get(pk) or {}
        momentum_trend = row.get("momentum_trend")
        momentum_direction = row.get("momentum_direction")
        if live_stats_fresh and player_stats:
            live_trend = live_sg_trajectory_trend(player_stats)
            if live_trend is not None:
                momentum_trend = live_trend
                momentum_direction = "hot" if live_trend > 0.05 else "cold" if live_trend < -0.05 else "neutral"
        board.append(
            {
                "player_key": row.get("player_key"),
                "player": row.get("player"),
                "finish_state": row.get("finish_state"),
                "model": {
                    "start_rank": row.get("start_rank"),
                    "current_rank": row.get("current_rank"),
                    "rank_delta": row.get("rank_delta"),
                    "composite": row.get("composite"),
                    "start_composite": row.get("start_composite"),
                    "pre_tournament_composite": row.get("pre_tournament_composite"),
                    "momentum": row.get("momentum"),
                    "momentum_trend": momentum_trend,
                    "momentum_direction": momentum_direction,
                },
                "scoring": {
                    "position_label": row.get("leaderboard_position"),
                    "position_rank": row.get("leaderboard_rank"),
                    "start_position": row.get("start_leaderboard_position"),
                    "start_position_rank": row.get("start_leaderboard_rank"),
                    "position_delta": row.get("leaderboard_delta"),
                    "total_to_par": row.get("total_to_par"),
                    "baseline_source": row.get("leaderboard_baseline_source"),
                    "live_stats": player_stats if player_stats else None,
                },
            }
        )
    return board


def _extract_eliminated_players(
    composite_results: list[dict],
    *,
    finish_states: dict[str, str] | None,
) -> list[dict]:
    eliminated: list[dict] = []
    finish_state_map = finish_states or {}
    for row in composite_results or []:
        pk = str(row.get("player_key") or "").strip().lower()
        if not pk:
            continue
        finish_state = finish_state_map.get(pk)
        if not _is_cut_or_inactive(finish_state):
            continue
        eliminated.append(
            {
                "player_key": row.get("player_key"),
                "player": row.get("player_display") or row.get("player"),
                "finish_state": finish_state,
                "pre_tournament_composite": row.get("composite"),
            }
        )
    eliminated.sort(key=lambda item: (str(item.get("finish_state") or ""), str(item.get("player") or "")))
    return eliminated


_LIVE_ACTIONABLE_MARKET_TYPES = frozenset({"round_matchups", "3_balls"})


def _annotate_live_market_row(
    row: dict[str, Any],
    *,
    generated_at: str,
    last_seen_tick: str,
    live_is_active: bool,
) -> None:
    if not isinstance(row, dict):
        return
    market_type = str(row.get("market_type") or "tournament_matchups").strip().lower()
    book = str(row.get("book") or row.get("bookmaker") or "").strip().lower()
    odds = str(row.get("odds") or row.get("market_odds") or "").strip()
    has_line = bool(book and odds and odds not in {"--", "-", ""} and not _is_non_book_source(book))

    if market_type in {"round_matchups", "round"}:
        provenance = "round_matchups"
    elif market_type in {"tournament_matchups", "72-hole", "72-hole fallback"}:
        provenance = "tournament_matchups"
    elif market_type in {"3_balls", "3ball", "group"}:
        provenance = "3_balls"
    elif market_type in {"outright", "win"}:
        provenance = "outright"
    elif market_type in {"top5", "top10", "top20", "make_cut", "player_market"}:
        provenance = "player_market"
    else:
        provenance = "unknown"

    gating = bool(getattr(config, "LIVE_MARKET_AVAILABILITY_GATING", True))
    if not live_is_active:
        bettable = has_line
        reason = "Pre-event market row" if bettable else "Missing book line"
    elif provenance == "tournament_matchups" and gating:
        bettable = False
        reason = "72-hole tournament matchup is not a live book market"
    elif provenance in _LIVE_ACTIONABLE_MARKET_TYPES or provenance == "outright":
        bettable = has_line
        reason = "Current live book line on supported market" if bettable else "No current live book line"
    elif provenance == "player_market":
        bettable = has_line and bool(row.get("live_model_prob") or row.get("model_prob"))
        reason = (
            "Live player market with book line"
            if bettable
            else "Player market missing live probability or book line"
        )
    else:
        bettable = has_line
        reason = "Book line present" if bettable else "Unsupported or missing live market line"

    row["market_provenance"] = provenance
    row["market_type"] = market_type
    row["live_bettable"] = bool(bettable)
    row["availability_reason"] = reason
    row["line_seen_at"] = generated_at if bettable else row.get("line_seen_at")
    row["last_seen_tick"] = last_seen_tick if bettable else None


def _annotate_live_market_availability(
    section_payload: dict[str, Any],
    *,
    generated_at: str,
    snapshot_id: str,
    live_is_active: bool,
) -> None:
    if not isinstance(section_payload, dict):
        return
    tick = str(snapshot_id or generated_at)
    for surface_key in ("matchup_bets", "matchup_bets_all_books", "matchups"):
        for row in section_payload.get(surface_key) or []:
            if isinstance(row, dict):
                _annotate_live_market_row(
                    row,
                    generated_at=generated_at,
                    last_seen_tick=tick,
                    live_is_active=live_is_active,
                )
    for market_type, bets in (section_payload.get("value_bets") or {}).items():
        for row in bets or []:
            if isinstance(row, dict):
                if not row.get("market_type"):
                    row["market_type"] = str(market_type)
                _annotate_live_market_row(
                    row,
                    generated_at=generated_at,
                    last_seen_tick=tick,
                    live_is_active=live_is_active,
                )


def _build_live_groups_shadow(
    *,
    dg_win_prob: dict[str, float],
    generated_at: str,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    """Shadow-only live group rows — not actionable until a book posts 3-ball lines."""
    if not getattr(config, "LIVE_GROUPS_SHADOW", True):
        return []
    rows: list[dict[str, Any]] = []
    keys = sorted(dg_win_prob.keys())[:9]
    for idx in range(0, max(0, len(keys) - 2), 3):
        group_keys = keys[idx : idx + 3]
        if len(group_keys) < 3:
            break
        probs = [max(float(dg_win_prob.get(k) or 0.0), 0.0001) for k in group_keys]
        total = sum(probs)
        norm = [p / total for p in probs] if total > 0 else probs
        rows.append(
            {
                "market_type": "3_balls",
                "market_provenance": "3_balls",
                "players": group_keys,
                "model_probs": dict(zip(group_keys, norm)),
                "shadow_only": True,
                "live_bettable": False,
                "availability_reason": "Shadow group pricing — no verified live 3-ball book line",
                "line_seen_at": None,
                "last_seen_tick": None,
                "generated_at": generated_at,
                "snapshot_id": snapshot_id,
            }
        )
    return rows


def _build_live_player_markets_shadow(
    *,
    dg_win_prob: dict[str, float],
    generated_at: str,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    """Shadow outright / placement rows using in-play win probability."""
    if not getattr(config, "LIVE_PLAYER_MARKETS_SHADOW", True):
        return []
    rows: list[dict[str, Any]] = []
    for pk, win_prob in sorted(dg_win_prob.items(), key=lambda item: item[1], reverse=True)[:15]:
        rows.append(
            {
                "bet_type": "outright",
                "player_key": pk,
                "market_provenance": "outright",
                "model_prob": float(win_prob),
                "live_model_prob": float(win_prob),
                "shadow_only": True,
                "live_bettable": False,
                "availability_reason": "Shadow outright — no verified live book line this tick",
                "line_seen_at": None,
                "last_seen_tick": None,
                "generated_at": generated_at,
                "snapshot_id": snapshot_id,
            }
        )
    return rows


def _market_ev_threshold(market_family: str, market_type: str) -> float:
    if market_family == "matchup":
        return float(config.MATCHUP_EV_THRESHOLD)
    threshold = config.MARKET_EV_THRESHOLDS.get(str(market_type or "").strip().lower(), config.DEFAULT_EV_THRESHOLD)
    try:
        return float(threshold)
    except (TypeError, ValueError):
        return float(config.DEFAULT_EV_THRESHOLD)


def _ev_threshold_steps(market_family: str, market_type: str) -> list[float]:
    thresholds = {
        _market_ev_threshold(market_family, market_type),
        float(config.MATCHUP_TIER_GOOD_EV_PCT) / 100.0,
        float(config.MATCHUP_TIER_STRONG_EV_PCT) / 100.0,
    }
    return sorted(step for step in thresholds if step > 0)


def _is_material_ev_increase(
    previous_ev: float | None,
    current_ev: float | None,
    *,
    market_family: str,
    market_type: str,
) -> bool:
    if previous_ev is None or current_ev is None:
        return False
    if current_ev <= previous_ev:
        return False
    for threshold in _ev_threshold_steps(market_family, market_type):
        if previous_ev < threshold <= current_ev:
            return True
    return False


def _build_live_opportunity_groups(section_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    section = section_payload or {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    matchup_surfaces = [
        section.get("matchup_bets") or [],
        section.get("matchup_bets_all_books") or [],
    ]
    for surface in matchup_surfaces:
        for row in surface:
            item = dict(row or {})
            ev = _coerce_float(item.get("ev"))
            market_type = str(item.get("market_type") or "tournament_matchups").strip() or "tournament_matchups"
            book = str(item.get("book") or item.get("bookmaker") or "").strip().lower()
            pick_key = _normalize_player_key(item.get("pick_key") or item.get("player_key"), fallback_name=item.get("pick") or item.get("player"))
            opp_key = _normalize_player_key(item.get("opponent_key"), fallback_name=item.get("opponent"))
            odds = str(item.get("odds") or item.get("market_odds") or "").strip()
            key = "|".join(["matchup", market_type, pick_key, opp_key, book, odds])
            grouped.setdefault(key, []).append(
                {
                    "row": row,
                    "ev": ev,
                    "market_family": "matchup",
                    "market_type": market_type,
                    "bookmaker": book,
                    "player": item.get("pick") or item.get("player"),
                    "opponent": item.get("opponent"),
                }
            )
    for market_type, bets in (section.get("value_bets") or {}).items():
        for row in bets or []:
            item = dict(row or {})
            ev = _coerce_float(item.get("ev"))
            if ev is None:
                continue
            book = str(item.get("book") or item.get("best_book") or "").strip().lower()
            player_key = _normalize_player_key(item.get("player_key"), fallback_name=item.get("player"))
            odds = str(item.get("odds") or item.get("best_odds") or "").strip()
            key = "|".join(["value", str(market_type).strip().lower(), player_key, book, odds])
            grouped.setdefault(key, []).append(
                {
                    "row": row,
                    "ev": ev,
                    "market_family": "value",
                    "market_type": str(market_type),
                    "bookmaker": book,
                    "player": item.get("player"),
                    "opponent": None,
                }
            )
    return grouped


def _apply_live_opportunity_flags(
    section_payload: dict[str, Any],
    *,
    previous_section_payload: dict[str, Any] | None,
    generated_at: str,
) -> list[dict[str, Any]]:
    if not isinstance(section_payload, dict):
        return []
    current_groups = _build_live_opportunity_groups(section_payload)
    previous_groups = _build_live_opportunity_groups(previous_section_payload or {}) if previous_section_payload else {}
    previous_exists = bool(previous_section_payload)
    previous_lookup: dict[str, dict[str, Any]] = {}
    for key, rows in previous_groups.items():
        best = max(rows, key=lambda item: item.get("ev") if item.get("ev") is not None else float("-inf"))
        previous_lookup[key] = {
            "ev": best.get("ev"),
            "first_seen_at": ((best.get("row") or {}).get("first_seen_at")),
        }
    alerts: list[dict[str, Any]] = []
    for key, rows in current_groups.items():
        best = max(rows, key=lambda item: item.get("ev") if item.get("ev") is not None else float("-inf"))
        previous = previous_lookup.get(key)
        is_new = bool(previous_exists and previous is None)
        material = bool(
            previous_exists
            and previous is not None
            and _is_material_ev_increase(
                previous.get("ev"),
                best.get("ev"),
                market_family=str(best.get("market_family") or ""),
                market_type=str(best.get("market_type") or ""),
            )
        )
        first_seen_at = generated_at if is_new else (previous.get("first_seen_at") if previous else generated_at)
        for item in rows:
            row = item.get("row")
            if not isinstance(row, dict):
                continue
            row["is_new_since_last_snapshot"] = is_new
            row["is_new_live_opportunity"] = bool(is_new and row.get("live_bettable"))
            row["is_material_ev_increase"] = material
            row["first_seen_at"] = first_seen_at
        if not (is_new or material):
            continue
        best_row = best.get("row") if isinstance(best.get("row"), dict) else {}
        if best_row.get("live_bettable") is False:
            continue
        alerts.append(
            {
                "opportunity_key": key,
                "is_new_since_last_snapshot": is_new,
                "is_new_live_opportunity": bool(is_new and best.get("row", {}).get("live_bettable")),
                "is_material_ev_increase": material,
                "first_seen_at": first_seen_at,
                "ev": best.get("ev"),
                "market_family": best.get("market_family"),
                "market_type": best.get("market_type"),
                "bookmaker": best.get("bookmaker"),
                "player": best.get("player"),
                "opponent": best.get("opponent"),
            }
        )
    alerts.sort(key=lambda row: _coerce_float(row.get("ev")) or float("-inf"), reverse=True)
    return alerts[:20]


def _enrich_live_section(
    section_payload: dict[str, Any],
    *,
    event_id: str,
    generated_at: str,
    previous_section: dict[str, Any] | None,
    frozen_section: dict[str, Any] | None,
    history_section: str,
    snapshot_id: str | None = None,
    live_is_active: bool = True,
) -> None:
    if not isinstance(section_payload, dict):
        return
    _annotate_live_market_availability(
        section_payload,
        generated_at=generated_at,
        snapshot_id=str(snapshot_id or generated_at),
        live_is_active=live_is_active,
    )
    pre_rows = _enrich_static_rankings(
        section_payload.get("pre_tournament_rankings") or section_payload.get("rankings") or [],
        ranking_source="pre_tournament_model",
    )
    frozen_rows = _enrich_static_rankings(
        (frozen_section or {}).get("rankings")
        or (frozen_section or {}).get("pre_tournament_rankings")
        or [],
        ranking_source="frozen_pre_teeoff",
    )
    pre_baseline = _build_rank_baseline_map(pre_rows)
    frozen_baseline = _build_rank_baseline_map(frozen_rows)
    leaderboard_baseline = _build_leaderboard_baseline_map(
        event_id=event_id,
        frozen_section=frozen_section,
        history_section=history_section,
    )
    leaderboard_rows, leaderboard_lookup, scoring_baseline_label = _enrich_leaderboard_rows(
        section_payload.get("leaderboard") or [],
        baseline_lookup=leaderboard_baseline,
    )
    live_rows = _enrich_live_rankings(
        section_payload.get("live_rankings") or section_payload.get("rankings") or [],
        pre_baseline=pre_baseline,
        frozen_baseline=frozen_baseline,
        leaderboard_lookup=leaderboard_lookup,
        ranking_source=str(section_payload.get("ranking_source") or ""),
        live_point_in_time_source=section_payload.get("live_point_in_time_source"),
    )
    fallback_reason = None
    if str(section_payload.get("live_point_in_time_source") or "") == "live_point_in_time_pre_tournament_fallback":
        fallback_reason = (
            "Model order unchanged - waiting for live scoring signal."
        )
    section_payload["pre_tournament_rankings"] = pre_rows
    section_payload["frozen_pre_teeoff_rankings"] = frozen_rows
    section_payload["live_rankings"] = live_rows
    section_payload["rankings"] = live_rows
    section_payload["leaderboard"] = leaderboard_rows
    section_payload["live_player_board"] = _build_live_player_board(
        live_rows,
        live_stats_by_player=section_payload.get("live_stats_by_player"),
        live_stats_fresh=bool(section_payload.get("live_stats_fresh")),
    )
    section_payload["scoring_baseline_label"] = scoring_baseline_label
    section_payload["ranking_fallback_reason"] = fallback_reason
    section_payload["live_opportunity_alerts"] = _apply_live_opportunity_flags(
        section_payload,
        previous_section_payload=previous_section,
        generated_at=generated_at,
    )


def _build_market_prediction_rows(
    *,
    snapshot_id: str,
    generated_at: str,
    tour: str,
    section_name: str,
    section_payload: dict[str, Any] | None,
) -> list[dict]:
    section = section_payload or {}
    event_id = str(section.get("source_event_id") or section.get("event_id") or "").strip()
    event_name = str(section.get("event_name") or "").strip() or None
    if not event_id:
        return []

    rows: list[dict] = []
    seen_row_keys: set[str] = set()

    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _append_row(row: dict[str, Any], *, row_key: str) -> None:
        if row_key in seen_row_keys:
            return
        seen_row_keys.add(row_key)
        rows.append(row)

    matchup_rows = section.get("matchup_bets_all_books") or section.get("matchup_bets") or []
    for bet in matchup_rows:
        ev = _safe_float(bet.get("ev")) or 0.0
        model_prob = bet.get("model_win_prob")
        implied_prob = bet.get("implied_prob")
        odds = _normalize_market_odds(bet.get("odds"), bet.get("market_odds"))
        player_key = str(bet.get("pick_key") or bet.get("player_key") or "").strip() or None
        opponent_key = str(bet.get("opponent_key") or "").strip() or None
        book = str(bet.get("book") or bet.get("bookmaker") or "").strip() or None
        market_type = str(bet.get("market_type") or "tournament_matchups")
        _append_row(
            {
                "snapshot_id": snapshot_id,
                "generated_at": generated_at,
                "tour": str(tour or "").strip().lower() or None,
                "section": section_name,
                "event_id": event_id,
                "event_name": event_name,
                "market_family": "matchup",
                "market_type": market_type,
                "player_key": player_key,
                "player_display": str(bet.get("pick") or bet.get("player") or "").strip() or None,
                "opponent_key": opponent_key,
                "opponent_display": str(bet.get("opponent") or "").strip() or None,
                "book": book,
                "odds": odds,
                "model_prob": _safe_float(model_prob),
                "implied_prob": _safe_float(implied_prob),
                "ev": ev,
                "is_value": 1 if ev > 0 else 0,
                "payload_json": json.dumps(bet),
            },
            row_key="|".join(
                [
                    "matchup",
                    market_type,
                    player_key or "",
                    opponent_key or "",
                    book or "",
                    odds or "",
                ]
            ),
        )

    failed_candidates = (
        section.get("all_failed_candidates")
        or (section.get("diagnostics") or {}).get("failed_candidates")
        or []
    )
    for cand in failed_candidates:
        ev = _safe_float(cand.get("ev")) or 0.0
        odds = _normalize_market_odds(cand.get("odds"))
        player_key = str(cand.get("pick_key") or cand.get("player_key") or "").strip() or None
        opponent_key = str(cand.get("opponent_key") or "").strip() or None
        book = str(cand.get("book") or cand.get("bookmaker") or "").strip() or None
        market_type = str(cand.get("market_type") or "tournament_matchups")
        _append_row(
            {
                "snapshot_id": snapshot_id,
                "generated_at": generated_at,
                "tour": str(tour or "").strip().lower() or None,
                "section": section_name,
                "event_id": event_id,
                "event_name": event_name,
                "market_family": "matchup",
                "market_type": market_type,
                "player_key": player_key,
                "player_display": str(cand.get("pick") or cand.get("player") or "").strip() or None,
                "opponent_key": opponent_key,
                "opponent_display": str(cand.get("opponent") or "").strip() or None,
                "book": book,
                "odds": odds,
                "model_prob": _safe_float(cand.get("model_win_prob")),
                "implied_prob": _safe_float(cand.get("implied_prob")),
                "ev": ev,
                "is_value": 1 if ev > 0 else 0,
                "payload_json": json.dumps(cand),
            },
            row_key="|".join(
                [
                    "matchup",
                    market_type,
                    player_key or "",
                    opponent_key or "",
                    book or "",
                    odds or "",
                ]
            ),
        )

    value_bets_source = section.get("all_value_bets") or section.get("value_bets") or {}
    for market_type, bets in value_bets_source.items():
        for bet in bets or []:
            model_prob = bet.get("model_prob")
            implied_prob = bet.get("market_prob")
            ev = _safe_float(bet.get("ev")) or 0.0
            odds = _normalize_market_odds(bet.get("odds"), bet.get("best_odds"))
            player_key = str(bet.get("player_key") or "").strip() or None
            book = str(bet.get("book") or bet.get("best_book") or "").strip() or None
            market_type_str = str(market_type)
            _append_row(
                {
                    "snapshot_id": snapshot_id,
                    "generated_at": generated_at,
                    "tour": str(tour or "").strip().lower() or None,
                    "section": section_name,
                    "event_id": event_id,
                    "event_name": event_name,
                    "market_family": "placement",
                    "market_type": market_type_str,
                    "player_key": player_key,
                    "player_display": str(bet.get("player_display") or bet.get("player") or "").strip() or None,
                    "opponent_key": None,
                    "opponent_display": None,
                    "book": book,
                    "odds": odds,
                    "model_prob": _safe_float(model_prob),
                    "implied_prob": _safe_float(implied_prob),
                    "ev": ev,
                    "is_value": 1 if bool(bet.get("is_value")) else 0,
                    "payload_json": json.dumps(bet),
                },
                row_key="|".join(
                    [
                        "placement",
                        market_type_str,
                        player_key or "",
                        book or "",
                        odds or "",
                    ]
                ),
            )

    return rows


def _rankings_to_shadow_field(rankings: list[dict]) -> list[tuple[str, float]]:
    """Build (player_key, composite) tuples from snapshot rankings for shadow MC."""
    out: list[tuple[str, float]] = []
    for row in rankings or []:
        pk = str(row.get("player_key") or "").strip().lower()
        if not pk:
            continue
        comp = row.get("composite")
        if comp is None:
            continue
        try:
            c = float(comp)
        except (TypeError, ValueError):
            continue
        out.append((pk, c))
    return out


def _run_shadow_monte_carlo_v1(
    *,
    snapshot_id: str,
    generated_at: str,
    tour: str,
    snapshot: dict[str, Any],
) -> int:
    """
    Append-only shadow simulation rows when enabled; never affects EV or card output.
    """
    from src.models.prob_engine_v1.shadow_dispatch import run_shadow_field_simulation
    from src.models.prob_engine_v1.shadow_mc import is_any_shadow_monte_carlo_enabled

    if not is_any_shadow_monte_carlo_enabled():
        return 0
    rows_written = 0
    for section_name, section_key in (
        ("upcoming", "upcoming_tournament"),
        ("live", "live_tournament"),
    ):
        sec = snapshot.get(section_key) or {}
        if not (sec.get("eligibility") or {}).get("verified"):
            continue
        event_id = str(sec.get("source_event_id") or "").strip()
        if not event_id:
            continue
        rankings = sec.get("rankings") or []
        field = _rankings_to_shadow_field(rankings)
        if len(field) < int(getattr(config, "SHADOW_MC_MIN_FIELD", 30)):
            continue
        seed = hash(snapshot_id + section_name + event_id) % (2**32)
        try:
            payload = run_shadow_field_simulation(
                field,
                rankings,
                seed=seed,
            )
            payload["snapshot_generated_at"] = generated_at
            payload["section"] = section_name
            payload["event_id"] = event_id
            db.append_shadow_event_simulation(
                snapshot_id=snapshot_id,
                event_id=event_id,
                section=section_name,
                tour=str(tour or "").strip().lower() or None,
                n_sims=int(payload.get("n_sims") or 0),
                engine_version=str(payload.get("engine_version") or ""),
                payload_json=payload,
            )
            rows_written += 1
        except Exception as exc:
            _logger.warning(
                "shadow Monte Carlo v1 failed (%s/%s): %s", section_name, event_id, exc
            )
    return rows_written


def _event_slug(value: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return slug.strip("_")


def _discover_event_card_path(event_name: str | None) -> str | None:
    slug = _event_slug(event_name)
    if not slug:
        return None
    candidates: list[Path] = []
    for root in (_OUTPUT_DIR, _DOWNLOADS_DIR):
        if not root.exists():
            continue
        for path in root.glob("*.md"):
            name = path.name
            if "_methodology_" in name:
                continue
            if name.startswith("backtest") or name.startswith("research"):
                continue
            if slug not in path.stem:
                continue
            candidates.append(path)
    if not candidates:
        return None
    latest = max(candidates, key=lambda entry: entry.stat().st_mtime)
    return str(latest)


def _discover_latest_card_path() -> str | None:
    """
    Discover latest local card snapshot.

    Preference order:
    1) Downloads (manual/operator artifacts)
    2) output/ (runtime artifacts)
    """

    def _collect(root: Path) -> list[Path]:
        if not root.exists():
            return []
        rows: list[Path] = []
        for path in root.glob("*.md"):
            name = path.name
            if "_methodology_" in name:
                continue
            if name.startswith("backtest") or name.startswith("research"):
                continue
            rows.append(path)
        return rows

    download_cards = _collect(_DOWNLOADS_DIR)
    if download_cards:
        return str(max(download_cards, key=lambda entry: entry.stat().st_mtime))
    output_cards = _collect(_OUTPUT_DIR)
    if output_cards:
        return str(max(output_cards, key=lambda entry: entry.stat().st_mtime))
    return None


def _discover_latest_card_path_excluding(excluded_event_name: str | None) -> str | None:
    excluded_slug = _event_slug(excluded_event_name)

    def _collect(root: Path) -> list[Path]:
        if not root.exists():
            return []
        rows: list[Path] = []
        for path in root.glob("*.md"):
            name = path.name
            if "_methodology_" in name:
                continue
            if name.startswith("backtest") or name.startswith("research"):
                continue
            if excluded_slug and excluded_slug in path.stem:
                continue
            rows.append(path)
        return rows

    download_cards = _collect(_DOWNLOADS_DIR)
    if download_cards:
        return str(max(download_cards, key=lambda entry: entry.stat().st_mtime))
    output_cards = _collect(_OUTPUT_DIR)
    if output_cards:
        return str(max(output_cards, key=lambda entry: entry.stat().st_mtime))
    return None


def _extract_event_name_from_card(card_path: str | None) -> str | None:
    if not card_path:
        return None
    try:
        lines = Path(card_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("# "):
            continue
        title = stripped[2:].strip()
        if "— Betting Card" in title:
            return title.split("— Betting Card", 1)[0].strip()
        if "- Betting Card" in title:
            return title.split("- Betting Card", 1)[0].strip()
        return title
    return None


def _safe_float(value: str) -> float | None:
    cleaned = value.strip().replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_rankings_from_card(card_path: str | None, *, limit: int = 30) -> list[dict]:
    if not card_path:
        return []
    try:
        lines = Path(card_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    header = "| Rank | Player | Composite | Course Fit | Form | Momentum | Trend |"
    start_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == header:
            start_idx = idx + 2
            break
    if start_idx < 0:
        return []
    rankings: list[dict] = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if len(parts) < 6:
            continue
        rank = _safe_float(parts[0])
        if rank is None:
            continue
        player = parts[1]
        composite = _safe_float(parts[2])
        course_fit = _safe_float(parts[3])
        form = _safe_float(parts[4])
        momentum = _safe_float(parts[5])
        rankings.append(
            {
                "rank": int(rank),
                "player_key": re.sub(r"[^a-z0-9]+", "_", player.lower()).strip("_"),
                "player": player,
                "composite": composite,
                "course_fit": course_fit,
                "form": form,
                "momentum": momentum,
                "finish_state": None,
            }
        )
        if len(rankings) >= limit:
            break
    return rankings


def _parse_matchups_from_card(card_path: str | None, *, limit: int = 25) -> list[dict]:
    """Parse matchup bets from a stored betting card markdown file."""
    if not card_path:
        return []
    try:
        lines = Path(card_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    matchup_header = "| Pick | vs | Odds | Model Win% | EV | Conviction | Tier | Book | Why |"
    matchups: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == matchup_header:
            i += 2  # skip header + separator
            while i < len(lines):
                stripped = lines[i].strip()
                if not stripped.startswith("|"):
                    break
                parts = [part.strip() for part in stripped.strip("|").split("|")]
                if len(parts) < 8:
                    i += 1
                    continue
                player = parts[0].replace("**", "").strip()
                opponent = parts[1].strip()
                odds_str = parts[2].strip()
                model_prob_str = parts[3].strip().rstrip("%")
                ev_str = parts[4].strip().rstrip("%")
                book = parts[7].strip()
                ev_val = _safe_float(ev_str)
                model_prob_val = _safe_float(model_prob_str)
                if player and opponent:
                    matchups.append({
                        "player": player,
                        "player_key": re.sub(r"[^a-z0-9]+", "_", player.lower()).strip("_"),
                        "opponent": opponent,
                        "opponent_key": re.sub(r"[^a-z0-9]+", "_", opponent.lower()).strip("_"),
                        "bookmaker": book if book and book != "—" else None,
                        "market_odds": odds_str,
                        "model_prob": (model_prob_val / 100) if model_prob_val is not None else None,
                        "ev": (ev_val / 100) if ev_val is not None else None,
                        "market_type": "tournament_matchups",
                    })
                    if len(matchups) >= limit:
                        return matchups
                i += 1
        i += 1
    return matchups


def _classify_matchup_state(
    *,
    market_counts: dict[str, Any] | None,
    diagnostics_state: str | None,
    selected_rows: int,
    errors: list[str] | None = None,
) -> str:
    if errors:
        return "pipeline_error"
    if diagnostics_state in {"pipeline_error", "no_market_posted_yet", "market_available_no_edges", "edges_available"}:
        return diagnostics_state
    total_market_rows = 0
    for payload in (market_counts or {}).values():
        total_market_rows += int((payload or {}).get("raw_rows", 0))
    if total_market_rows == 0:
        return "no_market_posted_yet"
    if selected_rows <= 0:
        return "market_available_no_edges"
    return "edges_available"


def _run_ingest(tour: str) -> dict[str, Any]:
    warn_if_low_disk(str(get_data_dir()), context="live_refresh_ingest_start")
    from src.datagolf import (
        fetch_matchup_odds_with_diagnostics,
        fetch_schedule,
        get_latest_completed_event_info,
    )

    full_schedule = fetch_schedule(tour=tour, upcoming_only=False)
    upcoming_schedule = fetch_schedule(tour=tour, upcoming_only=True)
    tournament_matchups, tournament_diag = fetch_matchup_odds_with_diagnostics(market="tournament_matchups", tour=tour)
    three_ball, three_ball_diag = fetch_matchup_odds_with_diagnostics(market="3_balls", tour=tour)
    now_date = _utc_now().date()
    live_row = next((row for row in full_schedule if _is_live_schedule_event(row, today=now_date)), None)
    if not live_row:
        live_row = next((row for row in upcoming_schedule if _has_started_schedule_event(row, today=now_date)), None)
    live_event_active = bool(live_row)
    current_row = live_row if live_row else (upcoming_schedule[0] if upcoming_schedule else {})

    def _is_future_event(row: dict[str, Any]) -> bool:
        start = _parse_iso_date(row.get("start_date"))
        if not start:
            return False
        return start > now_date

    if live_event_active:
        upcoming_row = next(
            (
                row
                for row in upcoming_schedule
                if _is_future_event(row) and str(row.get("event_id") or "") != str((live_row or {}).get("event_id") or "")
            ),
            None,
        )
        if upcoming_row is None:
            upcoming_row = next(
                (
                    row
                    for row in full_schedule
                    if _is_future_event(row) and str(row.get("event_id") or "") != str((live_row or {}).get("event_id") or "")
                ),
                None,
            )
    else:
        upcoming_row = next((row for row in upcoming_schedule if _is_future_event(row)), None)
        if upcoming_row is None:
            upcoming_row = upcoming_schedule[0] if upcoming_schedule else None

    latest_completed = get_latest_completed_event_info(tour=tour, as_of=now_date) or {}
    latest_completed_name = str(latest_completed.get("event_name") or "").strip()
    if latest_completed_name and upcoming_row and str(upcoming_row.get("event_name") or "").strip().lower() == latest_completed_name.lower():
        upcoming_row = next(
            (
                row
                for row in upcoming_schedule
                if str(row.get("event_name") or "").strip().lower() != latest_completed_name.lower()
            ),
            upcoming_row,
        )
    context_row = current_row or upcoming_row or {}
    return {
        "event_name": context_row.get("event_name"),
        "event_id": context_row.get("event_id"),
        "event_year": context_row.get("year"),
        "course": context_row.get("course"),
        "schedule_count": len(upcoming_schedule),
        "live_event_active": live_event_active,
        "current_event_row": current_row,
        "upcoming_event_row": upcoming_row,
        "latest_completed_event_name": latest_completed.get("event_name"),
        "latest_completed_event_id": latest_completed.get("event_id"),
        "latest_completed_event_year": latest_completed.get("year"),
        "latest_completed_event_course": latest_completed.get("course"),
        "upcoming_event_names": [row.get("event_name") for row in upcoming_schedule[:3] if row.get("event_name")],
        "market_counts": {
            "tournament_matchups": {
                "raw_rows": len(tournament_matchups),
                "reason_code": tournament_diag.get("reason_code"),
            },
            "three_ball": {
                "raw_rows": len(three_ball),
                "reason_code": three_ball_diag.get("reason_code"),
            },
        },
    }


def _ingest_has_event_context(ingest_summary: dict[str, Any]) -> bool:
    """True when schedule ingest resolved enough context to run the model."""
    return bool(
        str(ingest_summary.get("event_id") or "").strip()
        or str(ingest_summary.get("event_name") or "").strip()
    )


def _maybe_auto_grade_completed_event(ingest_summary: dict[str, Any]) -> dict[str, Any] | None:
    """Backfill + grade +EV inventory for the latest completed event."""
    event_id = str(ingest_summary.get("latest_completed_event_id") or "").strip()
    raw_year = ingest_summary.get("latest_completed_event_year")
    if not event_id:
        return None
    try:
        year = int(raw_year)
    except (TypeError, ValueError):
        year = datetime.now(timezone.utc).year

    from src.event_pick_freeze import _inventory_exists, freeze_completed_event_picks

    ledger_count, mpr_count = _inventory_exists(event_id)

    conn = db.get_conn()
    try:
        tournament = conn.execute(
            "SELECT id, name FROM tournaments WHERE event_id = ? AND year = ? ORDER BY id DESC LIMIT 1",
            (event_id, year),
        ).fetchone()
        picks_count = 0
        graded_count = 0
        ungraded_positive = 0
        if tournament:
            tournament_id = int(tournament["id"])
            picks_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM picks WHERE tournament_id = ?",
                    (tournament_id,),
                ).fetchone()["count"]
                or 0
            )
            graded_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM pick_outcomes po
                    JOIN picks p ON p.id = po.pick_id
                    WHERE p.tournament_id = ?
                    """,
                    (tournament_id,),
                ).fetchone()["count"]
                or 0
            )
            ungraded_positive = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM picks p
                    LEFT JOIN pick_outcomes po ON po.pick_id = p.id
                    WHERE p.tournament_id = ?
                      AND p.ev IS NOT NULL AND p.ev > 0
                      AND po.id IS NULL
                    """,
                    (tournament_id,),
                ).fetchone()["count"]
                or 0
            )
    finally:
        conn.close()

    if ledger_count == 0 and mpr_count == 0 and picks_count == 0:
        return {
            "status": "skipped",
            "reason": "no_tracked_picks",
            "event_id": event_id,
            "year": year,
        }

    if (
        ledger_count > 0
        or mpr_count > 0
        or ungraded_positive > 0
        or (picks_count > 0 and graded_count < picks_count)
    ):
        _logger.info(
            "Auto-capture/grade completed event %s/%s (ledger=%s mpr=%s picks=%s graded=%s ungraded+ev=%s)",
            event_id,
            year,
            ledger_count,
            mpr_count,
            picks_count,
            graded_count,
            ungraded_positive,
        )
        return freeze_completed_event_picks(
            event_id,
            year=year,
            event_name=ingest_summary.get("latest_completed_event_name"),
        )

    return {
        "status": "skipped",
        "reason": "already_graded",
        "event_id": event_id,
        "year": year,
        "picks_count": picks_count,
        "graded_count": graded_count,
    }


def _build_section_eligibility(
    analysis_result: dict[str, Any],
    *,
    source_event_id: str | None,
    tour: str,
) -> dict[str, Any]:
    field_validation = analysis_result.get("field_validation") or {}
    verification_error = analysis_result.get("verification_error") or {}
    failed_invariants = list(
        field_validation.get("failed_invariants")
        or verification_error.get("failed_invariants")
        or []
    )
    status = str(analysis_result.get("status") or "").strip().lower()
    strict_field_verified = bool(field_validation.get("strict_field_verified"))
    has_rows = bool(analysis_result.get("composite_results"))
    verified = bool(status == "complete" and strict_field_verified and has_rows)
    if status != "complete" and "analysis_not_complete" not in failed_invariants:
        failed_invariants.append("analysis_not_complete")
    if not strict_field_verified and "strict_field_not_verified" not in failed_invariants:
        failed_invariants.append("strict_field_not_verified")
    if not has_rows and "no_rankings_rows" not in failed_invariants:
        failed_invariants.append("no_rankings_rows")

    if verified:
        summary = "Field verified for this event. Rankings are eligible for display."
        details = (
            "All displayed players are validated against the confirmed event field feed."
        )
        action = None
        code = "field_verified"
        retryable = False
    else:
        summary = verification_error.get("summary") or "Field verification failed; rankings withheld."
        details = verification_error.get("details") or (
            "The current run could not prove that rankings match the confirmed event field."
        )
        action = verification_error.get("action") or (
            "Retry refresh after the event field feed is available and event context matches."
        )
        code = verification_error.get("code") or "field_verification_failed"
        retryable = bool(verification_error.get("retryable", True))

    return {
        "verified": verified,
        "field_event_id": str(field_validation.get("expected_event_id") or source_event_id or ""),
        "field_player_count": int(analysis_result.get("field_size") or 0),
        "field_source": str(field_validation.get("field_source") or analysis_result.get("field_source") or "unknown"),
        "failed_invariants": failed_invariants,
        "summary": summary,
        "details": details,
        "action": action,
        "code": code,
        "retryable": retryable,
        "major_event": bool(field_validation.get("major_event")),
        "cross_tour_backfill_used": bool(field_validation.get("cross_tour_backfill_used")),
        "observed_tour": tour,
    }


def _load_verified_section_fallback(
    previous_snapshot: dict[str, Any],
    *,
    section_key: str,
    expected_event_id: str | None,
    expected_tour: str,
) -> dict[str, Any] | None:
    section = (previous_snapshot or {}).get(section_key) or {}
    if not section:
        return None
    eligibility = section.get("eligibility") or {}
    if not eligibility.get("verified"):
        return None
    prev_tour = str(((previous_snapshot or {}).get("event_context") or {}).get("tour") or "").strip().lower()
    if prev_tour and prev_tour != str(expected_tour or "").strip().lower():
        return None
    current_event_id = str(expected_event_id or "").strip()
    section_event_id = str(section.get("source_event_id") or eligibility.get("field_event_id") or "").strip()
    if current_event_id and section_event_id and current_event_id != section_event_id:
        return None
    return section


def _board_section_from_analysis(
    live_result: dict[str, Any],
    *,
    source_event_id: str,
    tour: str,
    finish_states: dict[str, Any],
    exclude_cut_players: bool,
) -> dict[str, Any]:
    """Shared board fields (rankings, matchups, value bets) from a service analysis dict."""
    base_value_bets, _vf = _extract_board_value_bets(
        live_result.get("value_bets") or {},
        return_diagnostics=True,
    )
    return {
        "event_name": live_result.get("event_name"),
        "course_name": live_result.get("course_name"),
        "field_size": live_result.get("field_size"),
        "tournament_id": live_result.get("tournament_id"),
        "course_num": live_result.get("course_num"),
        "model_variant": live_result.get("model_variant", config.DEFAULT_MODEL_VARIANT),
        "event_format": live_result.get("event_format"),
        "skipped_reason": live_result.get("skipped_reason"),
        "rankings": _extract_rankings(
            live_result.get("composite_results") or [],
            finish_states=finish_states,
            exclude_cut_players=exclude_cut_players,
        ),
        "leaderboard": _load_event_leaderboard_rows(
            source_event_id,
            year=live_result.get("event_year"),
        ),
        "matchups": _extract_matchups(live_result.get("matchup_bets") or []),
        "matchup_bets": _extract_board_matchup_bets(live_result.get("matchup_bets") or []),
        "matchup_bets_all_books": _extract_board_matchup_bets(
            live_result.get("matchup_bets_all_books") or live_result.get("matchup_bets") or []
        ),
        "value_bets": base_value_bets,
        "card_path": live_result.get("output_file") or live_result.get("card_filepath"),
        "source_card_path": live_result.get("output_file") or live_result.get("card_filepath"),
        "eligibility": _build_section_eligibility(
            live_result,
            source_event_id=source_event_id,
            tour=tour,
        ),
        "verification_error": live_result.get("verification_error"),
    }


def _build_upcoming_section_from_result(
    upcoming_result: dict[str, Any],
    *,
    upcoming_row: dict[str, Any],
    upcoming_event_name: str,
    upcoming_event_id: str,
    upcoming_course: str | None,
    ingest_summary: dict[str, Any],
    tour: str,
    lane_prefix: str,
) -> dict[str, Any]:
    upcoming_value_bets, upcoming_value_filters = _extract_board_value_bets(
        upcoming_result.get("value_bets") or {},
        return_diagnostics=True,
    )
    upcoming_diag = upcoming_result.get("matchup_diagnostics") or {}
    upcoming_selection_counts = upcoming_diag.get("selection_counts") or {}
    upcoming_selected_rows = int(
        upcoming_selection_counts.get("all_qualifying_rows", upcoming_selection_counts.get("selected_rows", 0))
    )
    upcoming_eligibility = _build_section_eligibility(
        upcoming_result,
        source_event_id=upcoming_event_id,
        tour=tour,
    )
    upcoming_is_team_event = upcoming_result.get("event_format") == "team"
    if upcoming_is_team_event:
        upcoming_state = "team_event"
    else:
        upcoming_state = _classify_matchup_state(
            market_counts=ingest_summary.get("market_counts"),
            diagnostics_state=upcoming_diag.get("state"),
            selected_rows=upcoming_selected_rows,
            errors=upcoming_diag.get("errors"),
        )
        if not upcoming_eligibility.get("verified"):
            upcoming_state = "eligibility_failed"
    upcoming_variant = str(
        upcoming_result.get("model_variant", config.DEFAULT_MODEL_VARIANT)
    ).strip().lower() or config.DEFAULT_MODEL_VARIANT
    return {
        "event_name": upcoming_result.get("event_name") or upcoming_event_name,
        "course_name": upcoming_result.get("course_name"),
        "field_size": upcoming_result.get("field_size"),
        "event_format": upcoming_result.get("event_format"),
        "skipped_reason": upcoming_result.get("skipped_reason"),
        "leaderboard": _load_event_leaderboard_rows(
            upcoming_event_id,
            year=upcoming_row.get("year"),
        ),
        "rankings": (
            _extract_rankings(upcoming_result.get("composite_results") or [], exclude_cut_players=False)
            if upcoming_eligibility.get("verified")
            else []
        ),
        "matchups": (
            _extract_matchups(upcoming_result.get("matchup_bets") or [])
            if upcoming_eligibility.get("verified")
            else []
        ),
        "matchup_bets": (
            _extract_board_matchup_bets(upcoming_result.get("matchup_bets") or [])
            if upcoming_eligibility.get("verified")
            else []
        ),
        "matchup_bets_all_books": (
            _extract_board_matchup_bets(
                upcoming_result.get("matchup_bets_all_books") or upcoming_result.get("matchup_bets") or []
            )
            if upcoming_eligibility.get("verified")
            else []
        ),
        "value_bets": (upcoming_value_bets if upcoming_eligibility.get("verified") else {}),
        "card_path": upcoming_result.get("output_file") or upcoming_result.get("card_filepath"),
        "source_event_id": str(upcoming_row.get("event_id") or ""),
        "source_event_name": upcoming_event_name,
        "generated_from": f"{lane_prefix}_{upcoming_variant}",
        "source_card_path": upcoming_result.get("output_file") or upcoming_result.get("card_filepath"),
        "ranking_source": f"{lane_prefix}_{upcoming_variant}",
        "model_variant": upcoming_variant,
        "eligibility": upcoming_eligibility,
        "verification_error": upcoming_result.get("verification_error"),
        "diagnostics": {
            "market_counts": ingest_summary.get("market_counts") or {},
            "selection_counts": upcoming_diag.get("selection_counts") or {},
            "adaptation_state": upcoming_diag.get("adaptation_state", "normal"),
            "reason_codes": upcoming_diag.get("reason_codes") or {},
            "value_filters": upcoming_value_filters,
            "books_seen": upcoming_diag.get("books_seen") or [],
            "books_with_qualifying_edges": upcoming_diag.get("books_with_qualifying_edges") or [],
            "books_after_card_caps": upcoming_diag.get("books_after_card_caps") or [],
            "book_stats": upcoming_diag.get("book_stats") or {},
            "failed_candidates": upcoming_diag.get("failed_candidates") or [],
            "state": upcoming_state,
            "errors": (
                (upcoming_diag.get("errors") or [])
                + (
                    []
                    if upcoming_eligibility.get("verified")
                    else [
                        upcoming_eligibility.get("summary"),
                        upcoming_eligibility.get("action"),
                    ]
                )
            ),
        },
    }


def _build_lab_tournament_sections(
    snapshot: dict[str, Any],
    *,
    tour: str,
    mode: str,
    ingest_summary: dict[str, Any],
    upcoming_row: dict[str, Any],
    upcoming_event_name: str,
    upcoming_event_id: str,
    upcoming_course: str | None,
    live_course: str | None,
    live_event_name: str,
    live_source_event_id: str,
    live_source_event_year: int | None,
    live_is_active: bool,
    finish_states: dict[str, Any],
    dg_leaderboard: list[dict[str, Any]],
    dg_win_prob: dict[str, float],
    leaderboard_source: str,
    in_play_parse_note: str | None,
    lab_mv: str,
    snapshot_id: str,
    generated_at: str,
) -> list[dict[str, Any]]:
    """
    Parallel lab snapshot lane: fills ``lab_upcoming_tournament`` / ``lab_live_tournament``
    (same shape as production sections) and returns extra ``market_prediction_rows`` payloads.
    """
    rows_extra: list[dict[str, Any]] = []
    live_template = dict(snapshot.get("live_tournament") or {})

    lab_upcoming_result: dict[str, Any] = {}
    if upcoming_event_name:
        try:
            lab_upcoming_result = run_lab_snapshot_analysis(
                tour=tour,
                event_id=str(upcoming_row.get("event_id") or "") or None,
                tournament_name=upcoming_event_name,
                course_name=upcoming_course,
                mode="full",
                enable_ai=False,
                enable_backfill=False,
            )
        except Exception as exc:
            _logger.warning("Lab upcoming snapshot recompute failed: %s", exc)
            lab_upcoming_result = {}

    if lab_upcoming_result:
        lab_up = _build_upcoming_section_from_result(
            lab_upcoming_result,
            upcoming_row=upcoming_row,
            upcoming_event_name=upcoming_event_name,
            upcoming_event_id=upcoming_event_id,
            upcoming_course=upcoming_course,
            ingest_summary=ingest_summary,
            tour=tour,
            lane_prefix="lab_event_model",
        )
        snapshot["lab_upcoming_tournament"] = {
            **lab_up,
            "active": True,
            "data_mode": "full",
            "source": "lab_upcoming_event_model",
        }
        lab_up_sec = dict(snapshot["lab_upcoming_tournament"])
        lab_up_sec["matchup_bets_all_books"] = (
            lab_upcoming_result.get("matchup_bets_all_books")
            or lab_upcoming_result.get("matchup_bets")
            or []
        )
        lab_up_sec["all_value_bets"] = lab_upcoming_result.get("value_bets") or {}
        lab_up_sec["all_failed_candidates"] = (
            (lab_upcoming_result.get("matchup_diagnostics") or {}).get("failed_candidates") or []
        )
        rows_extra.extend(
            _build_market_prediction_rows(
                snapshot_id=snapshot_id,
                generated_at=generated_at,
                tour=tour,
                section_name="lab_upcoming",
                section_payload=lab_up_sec,
            )
        )
    else:
        snapshot["lab_upcoming_tournament"] = None

    lab_live_result: dict[str, Any] = {}
    try:
        lab_live_result = run_lab_snapshot_analysis(
            tour=tour,
            event_id=str(ingest_summary.get("event_id") or "") or None,
            tournament_name=str(ingest_summary.get("event_name") or "").strip() or None,
            course_name=live_course,
            mode=mode,
            enable_ai=False,
            enable_backfill=False,
        )
    except Exception as exc:
        _logger.warning("Lab live snapshot recompute failed: %s", exc)
        lab_live_result = {}

    if not lab_live_result:
        snapshot["lab_live_tournament"] = None
        diag = snapshot.setdefault("diagnostics", {})
        diag["lab_upcoming_state"] = (
            (snapshot.get("lab_upcoming_tournament") or {}).get("diagnostics") or {}
        ).get("state")
        diag["lab_live_state"] = None
        return rows_extra

    lab_board = _board_section_from_analysis(
        lab_live_result,
        source_event_id=live_source_event_id,
        tour=tour,
        finish_states=finish_states,
        exclude_cut_players=live_is_active,
    )
    lab_diag = lab_live_result.get("matchup_diagnostics") or {}
    lab_selection_counts = lab_diag.get("selection_counts") or {}
    lab_selected_rows = int(
        lab_selection_counts.get("all_qualifying_rows", lab_selection_counts.get("selected_rows", 0))
    )
    lab_eligibility = lab_board.get("eligibility") or {}
    lab_is_team_event = lab_live_result.get("event_format") == "team"
    if lab_is_team_event:
        lab_live_state = "team_event"
    else:
        lab_live_state = _classify_matchup_state(
            market_counts=ingest_summary.get("market_counts"),
            diagnostics_state=lab_diag.get("state"),
            selected_rows=lab_selected_rows,
            errors=lab_diag.get("errors"),
        )
    _, lab_live_value_filters = _extract_board_value_bets(
        lab_live_result.get("value_bets") or {},
        return_diagnostics=True,
    )
    if not lab_is_team_event and not lab_eligibility.get("verified"):
        lab_live_state = "eligibility_failed"

    lab_leaderboard = dg_leaderboard if dg_leaderboard else _load_event_leaderboard_rows(
        live_source_event_id,
        year=live_source_event_year,
    )
    lab_pre_tournament_rankings = _extract_rankings(
        lab_live_result.get("composite_results") or [],
        finish_states=finish_states,
        exclude_cut_players=live_is_active,
    )
    lab_rankings = lab_pre_tournament_rankings
    lab_live_rankings = lab_pre_tournament_rankings
    lab_point_in_time_source: str | None = None
    lab_ranking_source = "lab_current_event_model"
    if (
        live_is_active
        and lab_eligibility.get("verified")
        and (lab_live_result.get("composite_results") or [])
    ):
        lab_live_rankings, pit_source = _build_live_point_in_time_rankings(
            lab_live_result.get("composite_results") or [],
            lab_leaderboard,
            finish_states=finish_states,
            exclude_cut_players=live_is_active,
            dg_win_prob=dg_win_prob if dg_win_prob else None,
        )
        lab_rankings = lab_live_rankings
        lab_point_in_time_source = pit_source
        lab_ranking_source = f"lab_{pit_source}"

    lab_matchups = lab_board.get("matchups") or []
    lab_board_matchup_bets = lab_board.get("matchup_bets") or []
    lab_board_matchup_bets_all_books = (
        lab_board.get("matchup_bets_all_books") or lab_board.get("matchup_bets") or []
    )
    lab_value_bets = lab_board.get("value_bets") or {}
    lab_verification_error = lab_board.get("verification_error")

    if not lab_is_team_event and not lab_eligibility.get("verified"):
        lab_rankings = []
        lab_live_rankings = []
        lab_matchups = []
        lab_board_matchup_bets = []
        lab_board_matchup_bets_all_books = []
        lab_value_bets = {}
        lab_ranking_source = "lab_eligibility_failed"

    lab_diag_errors = list(lab_diag.get("errors") or [])
    if not lab_eligibility.get("verified"):
        lab_diag_errors = lab_diag_errors + [
            lab_eligibility.get("summary"),
            lab_eligibility.get("action"),
        ]

    snapshot["lab_live_tournament"] = {
        **live_template,
        "event_name": lab_live_result.get("event_name") or live_event_name,
        "active": live_is_active,
        "leaderboard": lab_leaderboard,
        "leaderboard_source": leaderboard_source,
        "in_play_parse_note": in_play_parse_note,
        "rankings": lab_rankings,
        "live_rankings": lab_live_rankings,
        "pre_tournament_rankings": lab_pre_tournament_rankings,
        "live_point_in_time_source": lab_point_in_time_source,
        "matchups": lab_matchups,
        "matchup_bets": lab_board_matchup_bets,
        "matchup_bets_all_books": lab_board_matchup_bets_all_books,
        "value_bets": lab_value_bets,
        "source_event_id": live_source_event_id,
        "source_event_name": live_event_name or str(ingest_summary.get("event_name") or ""),
        "data_mode": mode,
        "source": "lab_current_event_model",
        "source_card_path": lab_board.get("source_card_path"),
        "ranking_source": lab_ranking_source,
        "generated_from": "lab_current_event_model" if live_is_active else lab_ranking_source,
        "eligibility": lab_eligibility,
        "verification_error": lab_verification_error,
        "model_variant": (lab_live_result.get("strategy_meta") or {}).get("model_variant") or lab_mv,
        "strategy_meta": lab_live_result.get("strategy_meta"),
        "lab_champion_id": (lab_live_result.get("strategy_meta") or {}).get("lab_champion_id"),
        "diagnostics": {
            "market_counts": ingest_summary.get("market_counts") or {},
            "selection_counts": lab_diag.get("selection_counts") or {},
            "adaptation_state": lab_diag.get("adaptation_state", "normal"),
            "reason_codes": lab_diag.get("reason_codes") or {},
            "value_filters": lab_live_value_filters,
            "books_seen": lab_diag.get("books_seen") or [],
            "books_with_qualifying_edges": lab_diag.get("books_with_qualifying_edges") or [],
            "books_after_card_caps": lab_diag.get("books_after_card_caps") or [],
            "book_stats": lab_diag.get("book_stats") or {},
            "failed_candidates": lab_diag.get("failed_candidates") or [],
            "state": lab_live_state,
            "errors": [err for err in lab_diag_errors if err],
        },
    }

    lab_live_sec = dict(snapshot["lab_live_tournament"])
    lab_live_sec["matchup_bets_all_books"] = (
        lab_live_result.get("matchup_bets_all_books") or lab_live_result.get("matchup_bets") or []
    )
    lab_live_sec["all_value_bets"] = lab_live_result.get("value_bets") or {}
    lab_live_sec["all_failed_candidates"] = lab_diag.get("failed_candidates") or []
    rows_extra.extend(
        _build_market_prediction_rows(
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            tour=tour,
            section_name="lab_live",
            section_payload=lab_live_sec,
        )
    )

    diag = snapshot.setdefault("diagnostics", {})
    diag["lab_upcoming_state"] = (
        (snapshot.get("lab_upcoming_tournament") or {}).get("diagnostics") or {}
    ).get("state")
    diag["lab_live_state"] = (snapshot["lab_live_tournament"].get("diagnostics") or {}).get("state")

    return rows_extra


def _run_recompute(tour: str, cadence_mode: str, ingest_summary: dict[str, Any]) -> dict[str, Any]:
    mode = "full" if cadence_mode != "live_window" else "round-matchups"
    live_is_active_early = bool(ingest_summary.get("live_event_active"))
    live_course = str(ingest_summary.get("course") or "").split(";")[0].strip() or None
    if live_is_active_early:
        live_result = run_snapshot_analysis(
            tour=tour,
            event_id=str(ingest_summary.get("event_id") or "") or None,
            tournament_name=str(ingest_summary.get("event_name") or "").strip() or None,
            course_name=live_course,
            mode=mode,
            enable_ai=False,
            enable_backfill=False,
            model_variant=config.COCKPIT_SNAPSHOT_MODEL_VARIANT,
        )
    else:
        live_result = {}
    generated_at = _iso_now()
    snapshot_id = uuid.uuid4().hex
    event_name = live_result.get("event_name") or ingest_summary.get("event_name")
    live_event_id = str(ingest_summary.get("event_id") or "")
    finish_states = _load_finish_state_map(
        ingest_summary.get("event_id"),
        year=ingest_summary.get("event_year"),
    )
    previous_snapshot = read_snapshot()
    base_value_bets, base_value_filters = _extract_board_value_bets(
        live_result.get("value_bets") or {},
        return_diagnostics=True,
    )
    base_section = {
        "event_name": event_name,
        "course_name": live_result.get("course_name"),
        "field_size": live_result.get("field_size"),
        "tournament_id": live_result.get("tournament_id"),
        "course_num": live_result.get("course_num"),
        "model_variant": live_result.get("model_variant", config.COCKPIT_SNAPSHOT_MODEL_VARIANT),
        "event_format": live_result.get("event_format"),
        "skipped_reason": live_result.get("skipped_reason"),
        "rankings": _extract_rankings(
            live_result.get("composite_results") or [],
            finish_states=finish_states,
            exclude_cut_players=False,
        ),
        "leaderboard": _load_event_leaderboard_rows(
            ingest_summary.get("event_id"),
            year=ingest_summary.get("event_year"),
        ),
        "matchups": _extract_matchups(live_result.get("matchup_bets") or []),
        "matchup_bets": _extract_board_matchup_bets(live_result.get("matchup_bets") or []),
        "matchup_bets_all_books": _extract_board_matchup_bets(
            live_result.get("matchup_bets_all_books") or live_result.get("matchup_bets") or []
        ),
        "value_bets": base_value_bets,
        "card_path": live_result.get("output_file") or live_result.get("card_filepath"),
        "source_card_path": live_result.get("output_file") or live_result.get("card_filepath"),
        "eligibility": _build_section_eligibility(
            live_result,
            source_event_id=live_event_id,
            tour=tour,
        ),
        "verification_error": live_result.get("verification_error"),
    }
    schedule_names = ingest_summary.get("upcoming_event_names") or []
    live_is_active = bool(ingest_summary.get("live_event_active"))
    upcoming_row = ingest_summary.get("upcoming_event_row") or {}
    upcoming_event_name = str(upcoming_row.get("event_name") or "").strip()
    upcoming_event_id = str(upcoming_row.get("event_id") or "")
    upcoming_course = str(upcoming_row.get("course") or "").split(";")[0].strip() or None
    if not upcoming_event_name:
        upcoming_event_name = schedule_names[1] if live_is_active and len(schedule_names) > 1 else (schedule_names[0] if schedule_names else event_name)

    resolved_completed_event_name = str(ingest_summary.get("latest_completed_event_name") or "").strip() or None
    resolved_completed_event_id = str(ingest_summary.get("latest_completed_event_id") or "").strip() or None
    resolved_completed_event_course = str(ingest_summary.get("latest_completed_event_course") or "").strip() or None
    # Live section is always built from `live_result`, which targets ingest `event_id` / `event_name`.
    # During off-air weeks we used to substitute latest_completed_* for labels while still serving
    # the next-event model rows — that produced mismatched titles vs course/rankings/tournament_id.
    live_event_name = str(event_name or ingest_summary.get("event_name") or "").strip()
    live_source_event_id = str(ingest_summary.get("event_id") or "").strip()
    live_source_event_year_raw = ingest_summary.get("event_year")
    try:
        live_source_event_year = int(live_source_event_year_raw) if live_source_event_year_raw is not None else None
    except (TypeError, ValueError):
        live_source_event_year = None
    frozen_pre_teeoff_section = (
        db.get_pre_teeoff_frozen_payload(live_source_event_id)
        if live_source_event_id
        else None
    )

    upcoming_result = {}
    if upcoming_event_name:
        try:
            upcoming_result = run_snapshot_analysis(
                tour=tour,
                event_id=str(upcoming_row.get("event_id") or "") or None,
                tournament_name=upcoming_event_name,
                course_name=upcoming_course,
                mode="full",
                enable_ai=False,
                enable_backfill=False,
                model_variant=config.COCKPIT_SNAPSHOT_MODEL_VARIANT,
            )
        except Exception as exc:
            _logger.warning("Upcoming snapshot recompute failed; attempting verified snapshot fallback: %s", exc)
            upcoming_result = {}

    if upcoming_result:
        upcoming_section = _build_upcoming_section_from_result(
            upcoming_result,
            upcoming_row=upcoming_row,
            upcoming_event_name=upcoming_event_name,
            upcoming_event_id=upcoming_event_id,
            upcoming_course=upcoming_course,
            ingest_summary=ingest_summary,
            tour=tour,
            lane_prefix="upcoming_event_model",
        )
    else:
        upcoming_fallback = _load_verified_section_fallback(
            previous_snapshot,
            section_key="upcoming_tournament",
            expected_event_id=upcoming_event_id,
            expected_tour=tour,
        )
        if upcoming_fallback:
            upcoming_section = {
                **upcoming_fallback,
                "generated_from": "verified_snapshot_fallback",
                "ranking_source": "verified_snapshot_fallback",
            }
            fallback_errors = ((upcoming_section.get("diagnostics") or {}).get("errors") or [])
            upcoming_section.setdefault("diagnostics", {})
            upcoming_section["diagnostics"]["state"] = "pipeline_error"
            upcoming_section["diagnostics"]["errors"] = fallback_errors + [
                "Upcoming recompute unavailable; serving last verified snapshot for the same event.",
            ]
            upcoming_section["diagnostics"].setdefault(
                "value_filters",
                {
                    "missing_display_odds": 0,
                    "ev_cap_filtered": 0,
                    "probability_inconsistency_filtered": 0,
                },
            )
        else:
            upcoming_section = {
                **base_section,
                "event_name": upcoming_event_name,
                "source_event_id": str(upcoming_row.get("event_id") or ""),
                "source_event_name": upcoming_event_name,
                "generated_from": "upcoming_event_model_unavailable",
                "ranking_source": "eligibility_failed",
                "leaderboard": _load_event_leaderboard_rows(
                    upcoming_event_id,
                    year=upcoming_row.get("year"),
                ),
                "rankings": [],
                "matchups": [],
                "matchup_bets": [],
                "matchup_bets_all_books": [],
                "value_bets": {},
                "eligibility": {
                    "verified": False,
                    "field_event_id": upcoming_event_id,
                    "field_player_count": 0,
                    "field_source": "unavailable",
                    "failed_invariants": ["analysis_unavailable"],
                    "summary": "Upcoming field verification unavailable; rankings withheld.",
                    "details": "Upcoming model run did not return a verifiable snapshot.",
                    "action": "Retry refresh after Data Golf updates are available.",
                    "code": "upcoming_analysis_unavailable",
                    "retryable": True,
                    "major_event": False,
                    "cross_tour_backfill_used": False,
                    "observed_tour": tour,
                },
                "verification_error": {
                    "code": "upcoming_analysis_unavailable",
                    "summary": "Upcoming event recompute unavailable.",
                    "details": "Could not produce a verifiable upcoming snapshot in this cycle.",
                    "action": "Retry refresh once upstream data is available.",
                    "retryable": True,
                    "observed_event_id": upcoming_event_id,
                    "observed_tour": tour,
                },
                "diagnostics": {
                    "market_counts": ingest_summary.get("market_counts") or {},
                    "selection_counts": {"selected_rows": 0, "all_qualifying_rows": 0},
                    "adaptation_state": "unknown",
                    "reason_codes": {},
                "value_filters": {
                    "missing_display_odds": 0,
                    "ev_cap_filtered": 0,
                    "probability_inconsistency_filtered": 0,
                },
                    "state": "eligibility_failed",
                    "errors": ["Upcoming model unavailable and no verified fallback exists."],
                },
            }
        if upcoming_fallback:
            upcoming_section["source_event_id"] = str(upcoming_section.get("source_event_id") or upcoming_event_id)
            upcoming_section["source_event_name"] = str(upcoming_section.get("source_event_name") or upcoming_event_name)
            upcoming_section["event_name"] = str(upcoming_section.get("event_name") or upcoming_event_name)
            upcoming_section["leaderboard"] = (
                upcoming_section.get("leaderboard")
                or _load_event_leaderboard_rows(upcoming_event_id, year=upcoming_row.get("year"))
            )
            upcoming_section["matchup_bets_all_books"] = (
                upcoming_section.get("matchup_bets_all_books")
                or upcoming_section.get("matchup_bets")
                or []
            )

    # Legacy baseline lane for fallback inspection in Research.
    legacy_target_name = (
        upcoming_section.get("event_name")
        or upcoming_event_name
        or live_event_name
        or event_name
    )
    legacy_target_event_id = (
        str(upcoming_section.get("source_event_id") or "").strip()
        or upcoming_event_id
        or live_source_event_id
    )
    legacy_target_course = (
        upcoming_section.get("course_name")
        or upcoming_course
        or live_course
    )
    legacy_result: dict[str, Any] = {}
    if legacy_target_name:
        reuse_legacy_from_upcoming = (
            config.COCKPIT_SNAPSHOT_MODEL_VARIANT == config.LEGACY_MODEL_VARIANT
            and bool(upcoming_result)
            and str(legacy_target_event_id or "").strip() == str(upcoming_event_id or "").strip()
            and str(legacy_target_name or "").strip() == str(upcoming_event_name or "").strip()
        )
        if reuse_legacy_from_upcoming:
            legacy_result = upcoming_result
        else:
            try:
                legacy_result = run_snapshot_analysis(
                    tour=tour,
                    event_id=legacy_target_event_id or None,
                    tournament_name=str(legacy_target_name).strip() or None,
                    course_name=str(legacy_target_course).strip() or None,
                    mode=mode if live_is_active else "full",
                    enable_ai=False,
                    enable_backfill=False,
                    model_variant=config.LEGACY_MODEL_VARIANT,
                )
            except Exception as exc:
                _logger.warning("Legacy baseline snapshot recompute failed: %s", exc)
                legacy_result = {}

    if legacy_result:
        legacy_value_bets, legacy_value_filters = _extract_board_value_bets(
            legacy_result.get("value_bets") or {},
            return_diagnostics=True,
        )
        legacy_diag = legacy_result.get("matchup_diagnostics") or {}
        legacy_selection_counts = legacy_diag.get("selection_counts") or {}
        legacy_selected_rows = int(
            legacy_selection_counts.get("all_qualifying_rows", legacy_selection_counts.get("selected_rows", 0))
        )
        legacy_eligibility = _build_section_eligibility(
            legacy_result,
            source_event_id=legacy_target_event_id,
            tour=tour,
        )
        legacy_state = _classify_matchup_state(
            market_counts=ingest_summary.get("market_counts"),
            diagnostics_state=legacy_diag.get("state"),
            selected_rows=legacy_selected_rows,
            errors=legacy_diag.get("errors"),
        )
        if not legacy_eligibility.get("verified"):
            legacy_state = "eligibility_failed"
        legacy_section = {
            "event_name": legacy_result.get("event_name") or legacy_target_name,
            "course_name": legacy_result.get("course_name") or legacy_target_course,
            "field_size": legacy_result.get("field_size"),
            "leaderboard": _load_event_leaderboard_rows(
                legacy_target_event_id,
                year=upcoming_row.get("year") or ingest_summary.get("event_year"),
            ),
            "rankings": (
                _extract_rankings(legacy_result.get("composite_results") or [], exclude_cut_players=False)
                if legacy_eligibility.get("verified")
                else []
            ),
            "matchups": (
                _extract_matchups(legacy_result.get("matchup_bets") or [])
                if legacy_eligibility.get("verified")
                else []
            ),
            "matchup_bets": (
                _extract_board_matchup_bets(legacy_result.get("matchup_bets") or [])
                if legacy_eligibility.get("verified")
                else []
            ),
            "matchup_bets_all_books": (
                _extract_board_matchup_bets(
                    legacy_result.get("matchup_bets_all_books") or legacy_result.get("matchup_bets") or []
                )
                if legacy_eligibility.get("verified")
                else []
            ),
            "value_bets": (legacy_value_bets if legacy_eligibility.get("verified") else {}),
            "card_path": legacy_result.get("output_file") or legacy_result.get("card_filepath"),
            "source_event_id": str(legacy_target_event_id or ""),
            "source_event_name": str(legacy_target_name or ""),
            "generated_from": "legacy_baseline_model",
            "source_card_path": legacy_result.get("output_file") or legacy_result.get("card_filepath"),
            "ranking_source": "legacy_baseline_model",
            "model_variant": config.LEGACY_MODEL_VARIANT,
            "eligibility": legacy_eligibility,
            "verification_error": legacy_result.get("verification_error"),
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": legacy_diag.get("selection_counts") or {},
                "adaptation_state": legacy_diag.get("adaptation_state", "normal"),
                "reason_codes": legacy_diag.get("reason_codes") or {},
                "value_filters": legacy_value_filters,
                "state": legacy_state,
                "errors": (
                    (legacy_diag.get("errors") or [])
                    + (
                        []
                        if legacy_eligibility.get("verified")
                        else [
                            legacy_eligibility.get("summary"),
                            legacy_eligibility.get("action"),
                        ]
                    )
                ),
            },
            "strategy_meta": legacy_result.get("strategy_meta"),
        }
    else:
        legacy_section = {
            "event_name": str(legacy_target_name or ""),
            "course_name": str(legacy_target_course or ""),
            "field_size": 0,
            "leaderboard": [],
            "rankings": [],
            "matchups": [],
            "matchup_bets": [],
            "matchup_bets_all_books": [],
            "value_bets": {},
            "source_event_id": str(legacy_target_event_id or ""),
            "source_event_name": str(legacy_target_name or ""),
            "generated_from": "legacy_baseline_unavailable",
            "ranking_source": "legacy_baseline_unavailable",
            "model_variant": config.LEGACY_MODEL_VARIANT,
            "eligibility": {
                "verified": False,
                "field_event_id": str(legacy_target_event_id or ""),
                "field_player_count": 0,
                "field_source": "unavailable",
                "failed_invariants": ["analysis_unavailable"],
                "summary": "Legacy baseline analysis unavailable.",
                "details": "Could not produce a legacy baseline snapshot in this cycle.",
                "action": "Retry refresh after data sync completes.",
                "code": "legacy_analysis_unavailable",
                "retryable": True,
                "major_event": False,
                "cross_tour_backfill_used": False,
                "observed_tour": tour,
            },
            "verification_error": {
                "code": "legacy_analysis_unavailable",
                "summary": "Legacy baseline analysis unavailable.",
                "details": "Could not produce a legacy baseline snapshot in this cycle.",
                "action": "Retry refresh after data sync completes.",
                "retryable": True,
                "observed_event_id": str(legacy_target_event_id or ""),
                "observed_tour": tour,
            },
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": {"selected_rows": 0, "all_qualifying_rows": 0},
                "adaptation_state": "unknown",
                "reason_codes": {},
                "value_filters": {
                    "missing_display_odds": 0,
                    "ev_cap_filtered": 0,
                    "probability_inconsistency_filtered": 0,
                },
                "state": "pipeline_error",
                "errors": ["Legacy baseline recompute failed."],
            },
        }

    live_diag = live_result.get("matchup_diagnostics") or {}
    live_selection_counts = live_diag.get("selection_counts") or {}
    live_selected_rows = int(live_selection_counts.get("all_qualifying_rows", live_selection_counts.get("selected_rows", 0)))
    # Team-format events (e.g. Zurich Classic) are short-circuited upstream by
    # GolfModelService.run_analysis (see src/event_format.py). The service
    # returns status='complete' with event_format='team' but no eligibility /
    # composite_results, which would otherwise be misclassified as
    # eligibility_failed / pipeline_error here. Surface a dedicated 'team_event'
    # state instead so the dashboard renders the TeamEventNotice rather than
    # the degraded-pipeline banner.
    live_is_team_event = live_result.get("event_format") == "team"
    if live_is_team_event:
        live_state = "team_event"
    else:
        live_state = _classify_matchup_state(
            market_counts=ingest_summary.get("market_counts"),
            diagnostics_state=live_diag.get("state"),
            selected_rows=live_selected_rows,
            errors=live_diag.get("errors"),
        )
    live_eligibility = base_section.get("eligibility") or {}
    live_ranking_source = "current_event_model"
    live_point_in_time_source: str | None = None
    dg_win_prob: dict[str, float] = {}
    leaderboard_source = "rounds_table"
    in_play_parse_note: str | None = None
    dg_leaderboard: list[dict] = []
    raw_in_play: dict | list | None = None
    live_stats_by_player: dict[str, dict[str, Any]] = {}
    live_stats_meta: dict[str, Any] = {
        "live_stats_source": "datagolf_in_play",
        "live_stats_fetched_at": generated_at,
        "live_stats_age_seconds": None,
        "live_stats_fresh": False,
        "live_model_mode": "leaderboard_only",
        "live_stats_warning": None,
    }
    if live_is_active:
        try:
            raw_in_play = fetch_in_play_predictions(tour=tour)
            dg_leaderboard, dg_win_prob, in_play_parse_note = parse_in_play_leaderboard(raw_in_play)
            if dg_leaderboard:
                leaderboard_source = "datagolf_in_play"
            finish_states = _merge_in_play_finish_states(finish_states, dg_leaderboard)
            if getattr(config, "LIVE_STATS_MODEL_REFRESH_ENABLED", True):
                from datetime import datetime, timezone

                fetched_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                live_stats_by_player, live_stats_meta = parse_live_stats_from_in_play(
                    raw_in_play,
                    fetched_at=fetched_at,
                )
            elif dg_leaderboard or dg_win_prob:
                live_stats_meta["live_model_mode"] = "leaderboard_only"
                live_stats_meta["live_stats_warning"] = (
                    "Live stats model refresh disabled; using leaderboard and win probability only."
                )
        except Exception as exc:
            _logger.warning("Data Golf in-play fetch failed: %s", exc)
            in_play_parse_note = str(exc)
            live_stats_meta["live_model_mode"] = "no_live_stats"
            live_stats_meta["live_stats_warning"] = str(exc)
    live_leaderboard = dg_leaderboard if dg_leaderboard else _load_event_leaderboard_rows(
        live_source_event_id,
        year=live_source_event_year,
    )
    pre_tournament_rankings = _extract_rankings(
        live_result.get("composite_results") or [],
        finish_states=finish_states,
        exclude_cut_players=live_is_active,
    )
    live_rankings = pre_tournament_rankings
    eliminated_players = _extract_eliminated_players(
        live_result.get("composite_results") or [],
        finish_states=finish_states,
    )
    live_stats_fresh = bool(live_stats_meta.get("live_stats_fresh"))
    if live_stats_meta.get("live_model_mode") == "no_live_stats" and (dg_leaderboard or dg_win_prob):
        live_stats_meta["live_model_mode"] = "leaderboard_only"
    if (
        live_is_active
        and live_eligibility.get("verified")
        and (live_result.get("composite_results") or [])
    ):
        pit_rankings, pit_source = _build_live_point_in_time_rankings(
            live_result.get("composite_results") or [],
            live_leaderboard,
            finish_states=finish_states,
            exclude_cut_players=live_is_active,
            dg_win_prob=dg_win_prob if dg_win_prob else None,
            live_stats_by_player=live_stats_by_player if live_stats_fresh else None,
            live_stats_fresh=live_stats_fresh,
        )
        live_rankings = pit_rankings
        live_point_in_time_source = pit_source
        live_ranking_source = pit_source
    live_source_card_path = base_section.get("source_card_path")
    live_matchups = base_section.get("matchups") or []
    live_board_matchup_bets = base_section.get("matchup_bets") or []
    live_board_matchup_bets_all_books = (
        base_section.get("matchup_bets_all_books")
        or base_section.get("matchup_bets")
        or []
    )
    live_value_bets = base_section.get("value_bets") or {}
    live_verification_error = base_section.get("verification_error")

    if not live_is_active:
        live_state = "no_live_event"
        live_rankings = []
        pre_tournament_rankings = []
        live_matchups = []
        live_board_matchup_bets = []
        live_board_matchup_bets_all_books = []
        live_value_bets = {}
        live_leaderboard = []
        eliminated_players = []
        live_ranking_source = "no_live_event"
        live_event_name = ""
        live_source_event_id = ""
        live_diag = {
            **(live_diag or {}),
            "next_event_name": upcoming_event_name or None,
        }
    elif not live_is_team_event and not live_eligibility.get("verified"):
        live_state = "eligibility_failed"
        live_rankings = []
        live_matchups = []
        live_board_matchup_bets = []
        live_board_matchup_bets_all_books = []
        live_value_bets = {}
        live_ranking_source = "eligibility_failed"
        fallback_live = _load_verified_section_fallback(
            previous_snapshot,
            section_key="live_tournament",
            expected_event_id=live_event_id,
            expected_tour=tour,
        )
        if fallback_live:
            live_rankings = fallback_live.get("rankings") or []
            live_matchups = fallback_live.get("matchups") or []
            live_board_matchup_bets = fallback_live.get("matchup_bets") or []
            live_board_matchup_bets_all_books = (
                fallback_live.get("matchup_bets_all_books")
                or fallback_live.get("matchup_bets")
                or []
            )
            live_value_bets = fallback_live.get("value_bets") or {}
            live_eligibility = fallback_live.get("eligibility") or live_eligibility
            live_verification_error = fallback_live.get("verification_error") or live_verification_error
            live_leaderboard = fallback_live.get("leaderboard") or live_leaderboard
            live_ranking_source = "verified_snapshot_fallback"
            live_source_card_path = fallback_live.get("source_card_path") or live_source_card_path
            live_state = "pipeline_error"
            live_diag = {
                **(live_diag or {}),
                "errors": (
                    (live_diag.get("errors") or [])
                    + ["Current recompute failed verification; serving last verified same-event snapshot."]
                ),
            }

    live_diag_errors = live_diag.get("errors") or []
    if live_is_active and not live_eligibility.get("verified"):
        live_diag_errors = live_diag_errors + [
            live_eligibility.get("summary"),
            live_eligibility.get("action"),
        ]

    snapshot = {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "data_source": _resolve_data_source(),
        "cadence_mode": cadence_mode,
        "event_context": {
            "tour": tour,
            "event_name": event_name,
            "event_id": ingest_summary.get("event_id"),
            "course": ingest_summary.get("course"),
            "upcoming_event_names": schedule_names,
            "resolved_completed_event_id": resolved_completed_event_id,
            "resolved_completed_event_name": resolved_completed_event_name,
            "resolved_completed_event_course": resolved_completed_event_course,
        },
        "live_tournament": {
            **base_section,
            "event_name": live_event_name,
            "active": live_is_active,
            "leaderboard": live_leaderboard,
            "leaderboard_source": leaderboard_source,
            "in_play_parse_note": in_play_parse_note,
            "rankings": live_rankings,
            "live_rankings": live_rankings,
            "pre_tournament_rankings": pre_tournament_rankings,
            "frozen_pre_teeoff_rankings": [],
            "live_point_in_time_source": live_point_in_time_source,
            "eliminated_players": eliminated_players,
            "live_stats_by_player": live_stats_by_player,
            "live_stats_source": live_stats_meta.get("live_stats_source"),
            "live_stats_fetched_at": live_stats_meta.get("live_stats_fetched_at"),
            "live_stats_age_seconds": live_stats_meta.get("live_stats_age_seconds"),
            "live_stats_fresh": live_stats_meta.get("live_stats_fresh"),
            "live_model_mode": live_stats_meta.get("live_model_mode"),
            "live_stats_warning": live_stats_meta.get("live_stats_warning"),
            "live_groups_shadow": _build_live_groups_shadow(
                dg_win_prob=dg_win_prob,
                generated_at=generated_at,
                snapshot_id=snapshot_id,
            ),
            "live_player_markets_shadow": _build_live_player_markets_shadow(
                dg_win_prob=dg_win_prob,
                generated_at=generated_at,
                snapshot_id=snapshot_id,
            ),
            "live_groups_display_enabled": bool(getattr(config, "LIVE_GROUPS_DISPLAY_ENABLED", False)),
            "live_player_markets_display_enabled": bool(
                getattr(config, "LIVE_PLAYER_MARKETS_DISPLAY_ENABLED", False)
            ),
            "matchups": live_matchups,
            "matchup_bets": live_board_matchup_bets,
            "matchup_bets_all_books": live_board_matchup_bets_all_books,
            "value_bets": live_value_bets,
            "source_event_id": live_source_event_id,
            "source_event_name": live_event_name or str(ingest_summary.get("event_name") or ""),
            "data_mode": mode,
            "source": "current_event_model",
            "source_card_path": live_source_card_path,
            "ranking_source": live_ranking_source,
            "generated_from": "current_event_model" if live_is_active else live_ranking_source,
            "eligibility": live_eligibility,
            "verification_error": live_verification_error,
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": live_diag.get("selection_counts") or {},
                "adaptation_state": live_diag.get("adaptation_state", "normal"),
                "reason_codes": live_diag.get("reason_codes") or {},
                "value_filters": base_value_filters,
                "books_seen": live_diag.get("books_seen") or [],
                "books_with_qualifying_edges": live_diag.get("books_with_qualifying_edges") or [],
                "books_after_card_caps": live_diag.get("books_after_card_caps") or [],
                "book_stats": live_diag.get("book_stats") or {},
                "failed_candidates": live_diag.get("failed_candidates") or [],
                "state": live_state,
                "next_event_name": live_diag.get("next_event_name"),
                "errors": [err for err in live_diag_errors if err],
            },
        },
        "upcoming_tournament": {
            **upcoming_section,
            "active": True,
            "event_name": upcoming_section.get("event_name") or upcoming_event_name,
            "data_mode": "full",
            "source": "upcoming_event_model",
        },
        "legacy_tournament": {
            **legacy_section,
            "active": True,
            "event_name": legacy_section.get("event_name") or upcoming_section.get("event_name") or upcoming_event_name,
            "data_mode": "full",
            "source": "legacy_baseline_model",
        },
        "lab_upcoming_tournament": None,
        "lab_live_tournament": None,
        "diagnostics": {
            "market_counts": ingest_summary.get("market_counts") or {},
            "live_state": live_state,
            "upcoming_state": (upcoming_section.get("diagnostics") or {}).get("state"),
            "legacy_state": (legacy_section.get("diagnostics") or {}).get("state"),
        },
    }
    lab_rows_extra: list[dict[str, Any]] = []
    lr_cfg = (get_settings().get("live_refresh") or {})
    if lr_cfg.get("lab_profile_enabled"):
        profile_name = str(lr_cfg.get("lab_profile_name") or "lab_sandbox").strip()
        lab_mv = resolve_lab_model_variant(profile_name)
        try:
            lab_rows_extra = _build_lab_tournament_sections(
                snapshot,
                tour=tour,
                mode=mode,
                ingest_summary=ingest_summary,
                upcoming_row=upcoming_row,
                upcoming_event_name=upcoming_event_name,
                upcoming_event_id=upcoming_event_id,
                upcoming_course=upcoming_course,
                live_course=live_course,
                live_event_name=live_event_name,
                live_source_event_id=live_source_event_id,
                live_source_event_year=live_source_event_year,
                live_is_active=live_is_active,
                finish_states=finish_states,
                dg_leaderboard=dg_leaderboard,
                dg_win_prob=dg_win_prob,
                leaderboard_source=leaderboard_source,
                in_play_parse_note=in_play_parse_note,
                lab_mv=lab_mv,
                snapshot_id=snapshot_id,
                generated_at=generated_at,
            )
        except Exception as exc:
            _logger.warning("Parallel lab snapshot lane failed: %s", exc)
            snapshot["lab_upcoming_tournament"] = None
            snapshot["lab_live_tournament"] = None
            lab_rows_extra = []

    try:
        upcoming_payload = snapshot.get("upcoming_tournament") or {}
        upcoming_eid = str(upcoming_payload.get("source_event_id") or "").strip()
        if upcoming_eid and (upcoming_payload.get("eligibility") or {}).get("verified"):
            db.upsert_pre_teeoff_candidate(
                upcoming_eid,
                tour=tour,
                event_name=str(upcoming_payload.get("event_name") or "").strip() or None,
                section_payload=dict(upcoming_payload),
            )
    except Exception as exc:
        _logger.warning("pre-teeoff candidate upsert failed: %s", exc)

    if live_is_active and live_source_event_id:
        try:
            _maybe_freeze_pre_teeoff(
                live_event_id=str(live_source_event_id),
                tour=tour,
                live_event_name=live_event_name,
                snapshot_id=snapshot_id,
                previous_snapshot=previous_snapshot,
            )
        except Exception as exc:
            _logger.warning("pre-teeoff freeze failed: %s", exc)

    if live_source_event_id:
        frozen_pre_teeoff_section = (
            db.get_pre_teeoff_frozen_payload(live_source_event_id)
            or frozen_pre_teeoff_section
        )

    _enrich_live_section(
        snapshot.get("live_tournament") or {},
        event_id=live_source_event_id,
        generated_at=generated_at,
        previous_section=(previous_snapshot or {}).get("live_tournament"),
        frozen_section=frozen_pre_teeoff_section,
        history_section="live",
        snapshot_id=snapshot_id,
        live_is_active=live_is_active,
    )
    if isinstance(snapshot.get("lab_live_tournament"), dict):
        _enrich_live_section(
            snapshot["lab_live_tournament"],
            event_id=live_source_event_id,
            generated_at=generated_at,
            previous_section=(previous_snapshot or {}).get("lab_live_tournament"),
            frozen_section=frozen_pre_teeoff_section,
            history_section="live",
            snapshot_id=snapshot_id,
            live_is_active=live_is_active,
        )

    for section_key in (
        "live_tournament",
        "upcoming_tournament",
        "legacy_tournament",
        "lab_live_tournament",
        "lab_upcoming_tournament",
    ):
        section_payload = snapshot.get(section_key)
        if isinstance(section_payload, dict):
            snapshot[section_key] = _trim_snapshot_section_for_memory(section_payload)
    _touch_progress(phase="publish", phase_detail="writing live snapshot")
    _write_snapshot(snapshot)
    try:
        _touch_progress(phase="persist", phase_detail="sqlite history + market rows")
        history_count = db.store_live_snapshot_sections(
            snapshot_id,
            generated_at=generated_at,
            tour=tour,
            cadence_mode=cadence_mode,
            live_section=snapshot.get("live_tournament"),
            upcoming_section=snapshot.get("upcoming_tournament"),
        )
        snapshot.setdefault("diagnostics", {})["history_rows_written"] = history_count
    except Exception as exc:
        _logger.warning("Failed to persist snapshot history rows: %s", exc)
        snapshot.setdefault("diagnostics", {})["history_rows_written"] = 0
        snapshot.setdefault("diagnostics", {})["history_write_error"] = str(exc)
    try:
        market_rows = []
        live_market_section = dict(snapshot.get("live_tournament") or {})
        live_market_section["matchup_bets_all_books"] = (
            live_result.get("matchup_bets_all_books") or live_result.get("matchup_bets") or []
        )
        live_market_section["all_value_bets"] = live_result.get("value_bets") or {}
        live_market_section["all_failed_candidates"] = (live_diag or {}).get("failed_candidates") or []
        upcoming_market_section = dict(snapshot.get("upcoming_tournament") or {})
        upcoming_market_section["matchup_bets_all_books"] = (
            (upcoming_result or {}).get("matchup_bets_all_books")
            or (upcoming_result or {}).get("matchup_bets")
            or []
        )
        upcoming_market_section["all_value_bets"] = (upcoming_result or {}).get("value_bets") or {}
        upcoming_market_section["all_failed_candidates"] = (
            ((upcoming_result or {}).get("matchup_diagnostics") or {}).get("failed_candidates") or []
        )
        legacy_market_section = dict(snapshot.get("legacy_tournament") or {})
        legacy_market_section["matchup_bets_all_books"] = (
            (legacy_result or {}).get("matchup_bets_all_books")
            or (legacy_result or {}).get("matchup_bets")
            or []
        )
        legacy_market_section["all_value_bets"] = (legacy_result or {}).get("value_bets") or {}
        legacy_market_section["all_failed_candidates"] = (
            ((legacy_result or {}).get("matchup_diagnostics") or {}).get("failed_candidates") or []
        )
        market_rows.extend(
            _build_market_prediction_rows(
                snapshot_id=snapshot_id,
                generated_at=generated_at,
                tour=tour,
                section_name="live",
                section_payload=live_market_section,
            )
        )
        market_rows.extend(
            _build_market_prediction_rows(
                snapshot_id=snapshot_id,
                generated_at=generated_at,
                tour=tour,
                section_name="upcoming",
                section_payload=upcoming_market_section,
            )
        )
        market_rows.extend(
            _build_market_prediction_rows(
                snapshot_id=snapshot_id,
                generated_at=generated_at,
                tour=tour,
                section_name="legacy",
                section_payload=legacy_market_section,
            )
        )
        if lab_rows_extra:
            market_rows.extend(lab_rows_extra)
        market_rows_written = db.store_market_prediction_rows(market_rows)
        snapshot.setdefault("diagnostics", {})["market_rows_written"] = market_rows_written
        try:
            from src.pick_ledger import persist_pick_ledger_from_market_rows

            ledger_written = persist_pick_ledger_from_market_rows(
                market_rows,
                lifecycle="generated",
                source_origin="live_refresh",
            )
            snapshot.setdefault("diagnostics", {})["pick_ledger_written"] = ledger_written
        except Exception as ledger_exc:
            _logger.warning("Failed to persist pick ledger rows: %s", ledger_exc)
            snapshot.setdefault("diagnostics", {})["pick_ledger_write_error"] = str(ledger_exc)
    except Exception as exc:
        _logger.warning("Failed to persist market prediction rows: %s", exc)
        snapshot.setdefault("diagnostics", {})["market_rows_written"] = 0
        snapshot.setdefault("diagnostics", {})["market_rows_write_error"] = str(exc)
    _maybe_prune_snapshot_history_tables(snapshot)
    try:
        _touch_progress(phase="shadow_mc", phase_detail="shadow monte carlo batch")
        shadow_n = _run_shadow_monte_carlo_with_timeout(
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            tour=tour,
            snapshot=snapshot,
        )
        snapshot.setdefault("diagnostics", {})["shadow_mc_rows_written"] = shadow_n
    except Exception as exc:
        _logger.warning("shadow Monte Carlo v1 batch failed: %s", exc)
        snapshot.setdefault("diagnostics", {})["shadow_mc_rows_written"] = 0
    return snapshot


def generate_snapshot_once(*, tour: str = "pga") -> dict[str, Any]:
    """Run one ingest+recompute cycle synchronously and return the snapshot."""
    warn_if_low_disk(str(get_data_dir()), context="live_refresh_manual_cycle")
    if not _recompute_lock.acquire(blocking=False):
        raise LiveRefreshRecomputeBusy("Live refresh recompute is already in progress")
    if not _cross_process_cycle_lock.acquire(blocking=False):
        _recompute_lock.release()
        raise LiveRefreshRecomputeBusy("Live refresh cycle lock is held by another process")
    err: BaseException | None = None
    try:
        _touch_progress(refresh_state="running", phase="ingest", phase_detail="ingest: schedule + markets")
        settings = get_settings().get("live_refresh", {})
        cadence = resolve_cadence(settings)
        ingest_summary = _run_ingest(tour)
        _touch_progress(refresh_state="running", phase="recompute", phase_detail="snapshot pipeline")
        snapshot = _run_recompute_with_timeout(tour, cadence.mode, ingest_summary)
        with _state_lock:
            _state["tour"] = tour
            _state["cadence_mode"] = cadence.mode
            _state["ingest_seconds"] = cadence.ingest_seconds
            _state["recompute_seconds"] = cadence.recompute_seconds
            _state["run_count"] += 1
            _state["last_started_at"] = _iso_now()
            _state["last_finished_at"] = _iso_now()
            _state["last_error"] = None
            _state["last_ingest_summary"] = ingest_summary
            _state["last_snapshot_generated_at"] = snapshot.get("generated_at")
        return snapshot
    except BaseException as exc:
        err = exc
        _touch_progress(idle=True, last_error=str(exc))
        raise
    finally:
        _recompute_lock.release()
        _cross_process_cycle_lock.release()
        if err is None:
            _touch_progress(idle=True)


def _run_loop(tour: str) -> None:
    next_ingest = 0.0
    next_recompute = 0.0
    ingest_summary: dict[str, Any] = {}
    while not _stop_event.is_set():
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
        manual_trigger = consume_manual_trigger()
        if manual_trigger:
            next_recompute = now_epoch
            _logger.info("Manual refresh trigger consumed: %s", manual_trigger.get("request_id"))
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
                if not _recompute_lock.acquire(blocking=False):
                    next_recompute = now_epoch + 15.0
                    continue
                if not _cross_process_cycle_lock.acquire(blocking=False):
                    _recompute_lock.release()
                    next_recompute = now_epoch + 15.0
                    continue
                slot_err: BaseException | None = None
                try:
                    _touch_progress(
                        refresh_state="running",
                        phase="recompute",
                        phase_detail="scheduled snapshot pipeline",
                    )
                    if not _ingest_has_event_context(ingest_summary):
                        _touch_progress(phase="ingest", phase_detail="catch-up ingest before recompute")
                        ingest_summary = _run_ingest(tour)
                        with _state_lock:
                            _state["last_ingest_summary"] = ingest_summary
                    snapshot = _run_recompute_with_timeout(tour, cadence.mode, ingest_summary)
                except BaseException as exc:
                    slot_err = exc
                    _touch_progress(idle=True, last_error=str(exc))
                    raise
                finally:
                    _recompute_lock.release()
                    _cross_process_cycle_lock.release()
                    if slot_err is None:
                        _touch_progress(idle=True)
                finished_at = _iso_now()
                with _state_lock:
                    _state["run_count"] += 1
                    _state["last_finished_at"] = finished_at
                    _state["last_snapshot_generated_at"] = snapshot.get("generated_at")
                    _state["next_recompute_at"] = datetime.fromtimestamp(now_epoch + cadence.recompute_seconds, timezone.utc).isoformat()
                next_recompute = now_epoch + cadence.recompute_seconds
                try:
                    auto_grade_result = _maybe_auto_grade_completed_event(ingest_summary)
                    with _state_lock:
                        _state["last_auto_grade_at"] = _iso_now()
                        _state["last_auto_grade_status"] = auto_grade_result
                except Exception as exc:  # pragma: no cover - defensive
                    _logger.warning("Auto-grading check failed: %s", exc)
                    with _state_lock:
                        _state["last_auto_grade_at"] = _iso_now()
                        _state["last_auto_grade_status"] = {"status": "error", "message": str(exc)}
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
    _write_heartbeat()
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
    _write_heartbeat(running=False)
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
    status["progress"] = {
        "refresh_state": status.get("refresh_state") or "idle",
        "phase": status.get("phase"),
        "phase_detail": status.get("phase_detail"),
        "progress_updated_at": status.get("progress_updated_at"),
        "progress_started_at": status.get("progress_started_at"),
        "percent": status.get("recompute_percent"),
        "last_error": status.get("last_error"),
    }
    identity = get_runtime_identity()
    split = detect_split_brain()
    status["runtime_identity"] = identity
    status["split_brain_suspected"] = split["split_brain_suspected"]
    status["split_brain_reasons"] = split["reasons"]
    status["heartbeat_age_seconds"] = split["heartbeat_age_seconds"]
    return status


def build_current_board_contract(
    snapshot: dict[str, Any] | None,
    *,
    age_seconds: int | None,
    stale_after_seconds: int,
    split_brain_suspected: bool = False,
    split_brain_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Fail-closed envelope for current live/upcoming boards (never serve stale rows as healthy)."""
    reasons = list(split_brain_reasons or [])
    if split_brain_suspected:
        return {
            "ok": False,
            "data_state": "split_brain",
            "snapshot": None,
            "stale_reason": (
                "Dashboard and live-refresh worker may be reading different data folders. "
                + " ".join(reasons)
            ).strip(),
            "operator_message": (
                "Data path mismatch detected. Rankings and picks are hidden until the server "
                "uses one canonical data folder (/opt/golf-model/data)."
            ),
        }
    if not snapshot:
        return {
            "ok": False,
            "data_state": "missing",
            "snapshot": None,
            "stale_reason": "No snapshot generated yet.",
            "operator_message": "No live data snapshot is available yet.",
        }
    if age_seconds is not None and age_seconds > stale_after_seconds:
        return {
            "ok": False,
            "data_state": "stale",
            "snapshot": None,
            "generated_at": snapshot.get("generated_at"),
            "age_seconds": age_seconds,
            "stale_after_seconds": stale_after_seconds,
            "stale_reason": (
                f"Snapshot is too old ({age_seconds // 60} minutes). "
                "Current rankings and picks are hidden until a fresh recompute finishes."
            ),
            "operator_message": (
                "Live data is stale. The board stays empty until the live-refresh worker "
                "writes a fresh snapshot."
            ),
        }
    live_section = snapshot.get("live_tournament", {}) if isinstance(snapshot, dict) else {}
    upcoming_section = snapshot.get("upcoming_tournament", {}) if isinstance(snapshot, dict) else {}
    live_state = (live_section.get("diagnostics") or {}).get("state")
    upcoming_state = (upcoming_section.get("diagnostics") or {}).get("state")
    has_pipeline_degradation = live_state in {"pipeline_error", "eligibility_failed"} or upcoming_state in {
        "pipeline_error",
        "eligibility_failed",
    }
    fallback_sources = {"live_fallback", "verified_snapshot_fallback"}
    active_section = live_section if live_section.get("active") else upcoming_section
    fallback_active = active_section.get("ranking_source") in fallback_sources
    verification_messages: list[str] = []
    for label, section in (("Live", live_section), ("Upcoming", upcoming_section)):
        eligibility = (section or {}).get("eligibility") or {}
        if eligibility.get("verified") is False:
            summary = str(eligibility.get("summary") or "Field verification failed").strip()
            action = str(eligibility.get("action") or "").strip()
            verification_messages.append(f"{label}: {summary}{' ' + action if action else ''}")
    stale_reason = (
        " | ".join(verification_messages)
        if verification_messages
        else (
            "Live snapshot indicates a degraded pipeline state."
            if has_pipeline_degradation
            else None
        )
    )
    return {
        "ok": True,
        "data_state": "fresh",
        "snapshot": snapshot,
        "generated_at": snapshot.get("generated_at"),
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "stale_reason": stale_reason,
        "fallback_reason": ("Showing fallback rankings source." if fallback_active else None),
        "operator_message": None,
    }

