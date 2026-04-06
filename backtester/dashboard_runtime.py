"""
Always-on live refresh runtime for dashboard snapshots.
"""

from __future__ import annotations

import json
import logging
import re
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
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
_DOWNLOADS_DIR = Path.home() / "Downloads"


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
    context_row = live_row if live_row else (upcoming_row or current_row or {})
    return {
        "event_name": context_row.get("event_name"),
        "event_id": context_row.get("event_id"),
        "course": context_row.get("course"),
        "schedule_count": len(upcoming_schedule),
        "live_event_active": live_event_active,
        "current_event_row": current_row,
        "upcoming_event_row": upcoming_row,
        "latest_completed_event_name": latest_completed.get("event_name"),
        "latest_completed_event_id": latest_completed.get("event_id"),
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
    base_section = {
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
        "source_card_path": live_result.get("output_file") or live_result.get("card_filepath"),
    }
    schedule_names = ingest_summary.get("upcoming_event_names") or []
    live_is_active = bool(ingest_summary.get("live_event_active"))
    upcoming_row = ingest_summary.get("upcoming_event_row") or {}
    upcoming_event_name = str(upcoming_row.get("event_name") or "").strip()
    upcoming_course = str(upcoming_row.get("course") or "").split(";")[0].strip() or None
    if not upcoming_event_name:
        upcoming_event_name = schedule_names[1] if live_is_active and len(schedule_names) > 1 else (schedule_names[0] if schedule_names else event_name)

    resolved_completed_event_name = str(ingest_summary.get("latest_completed_event_name") or "").strip()
    resolved_completed_event_id = str(ingest_summary.get("latest_completed_event_id") or "").strip()
    resolved_completed_event_course = str(ingest_summary.get("latest_completed_event_course") or "").strip()

    # Guardrail: completed event must never silently mirror upcoming.
    if (not resolved_completed_event_name) or (
        upcoming_event_name and resolved_completed_event_name.lower() == upcoming_event_name.lower()
    ):
        fallback_card_path = _discover_latest_card_path()
        fallback_event_name = _extract_event_name_from_card(fallback_card_path)
        if fallback_event_name and (not upcoming_event_name or fallback_event_name.lower() != upcoming_event_name.lower()):
            resolved_completed_event_name = fallback_event_name
            previous_event_card_path = fallback_card_path
        else:
            previous_event_card_path = _discover_event_card_path(resolved_completed_event_name or event_name)
    else:
        previous_event_card_path = _discover_event_card_path(resolved_completed_event_name)
    previous_event_rankings = _parse_rankings_from_card(previous_event_card_path)
    live_event_name = event_name if live_is_active else (resolved_completed_event_name or event_name)

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
        upcoming_diag = upcoming_result.get("matchup_diagnostics") or {}
        upcoming_selected_rows = int((upcoming_diag.get("selection_counts") or {}).get("selected_rows", 0))
        upcoming_state = _classify_matchup_state(
            market_counts=ingest_summary.get("market_counts"),
            diagnostics_state=upcoming_diag.get("state"),
            selected_rows=upcoming_selected_rows,
            errors=upcoming_diag.get("errors"),
        )
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
            "source_card_path": upcoming_result.get("output_file") or upcoming_result.get("card_filepath"),
            "ranking_source": "upcoming_event_model",
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": upcoming_diag.get("selection_counts") or {},
                "adaptation_state": upcoming_diag.get("adaptation_state", "normal"),
                "reason_codes": upcoming_diag.get("reason_codes") or {},
                "state": upcoming_state,
                "errors": upcoming_diag.get("errors") or [],
            },
        }
    else:
        upcoming_section = {
            **base_section,
            "event_name": upcoming_event_name,
            "source_event_id": str(upcoming_row.get("event_id") or ""),
            "source_event_name": upcoming_event_name,
            "generated_from": "live_fallback",
            "ranking_source": "live_fallback",
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": {"selected_rows": len(base_section.get("matchups") or [])},
                "adaptation_state": "unknown",
                "reason_codes": {},
                "state": "pipeline_error",
                "errors": ["Upcoming model unavailable; using live fallback."],
            },
        }

    live_diag = live_result.get("matchup_diagnostics") or {}
    live_selected_rows = int((live_diag.get("selection_counts") or {}).get("selected_rows", 0))
    live_state = _classify_matchup_state(
        market_counts=ingest_summary.get("market_counts"),
        diagnostics_state=live_diag.get("state"),
        selected_rows=live_selected_rows,
        errors=live_diag.get("errors"),
    )
    live_rankings = _extract_rankings(
        live_result.get("composite_results") or [],
        finish_states=finish_states,
        exclude_cut_players=True,
    )
    live_ranking_source = "current_event_model"
    live_source_card_path = base_section.get("source_card_path")
    if not live_is_active and previous_event_rankings:
        live_rankings = previous_event_rankings
        live_ranking_source = "previous_card_snapshot"
        live_source_card_path = previous_event_card_path
    elif not live_is_active:
        live_ranking_source = "current_event_model_fallback"

    snapshot = {
        "generated_at": generated_at,
        "cadence_mode": cadence_mode,
        "event_context": {
            "event_name": event_name,
            "event_id": ingest_summary.get("event_id"),
            "course": ingest_summary.get("course"),
            "upcoming_event_names": schedule_names,
            "resolved_completed_event_name": resolved_completed_event_name or None,
            "resolved_completed_event_course": resolved_completed_event_course or None,
        },
        "live_tournament": {
            **base_section,
            "event_name": live_event_name,
            "active": live_is_active,
            "rankings": live_rankings,
            "source_event_id": str(
                ingest_summary.get("event_id") if live_is_active else resolved_completed_event_id
            ),
            "source_event_name": event_name if live_is_active else (resolved_completed_event_name or event_name),
            "data_mode": mode,
            "source": "current_event_model",
            "source_card_path": live_source_card_path,
            "ranking_source": live_ranking_source,
            "generated_from": "current_event_model" if live_is_active else live_ranking_source,
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": live_diag.get("selection_counts") or {},
                "adaptation_state": live_diag.get("adaptation_state", "normal"),
                "reason_codes": live_diag.get("reason_codes") or {},
                "state": live_state,
                "errors": live_diag.get("errors") or [],
            },
        },
        "upcoming_tournament": {
            **upcoming_section,
            "active": True,
            "event_name": upcoming_section.get("event_name") or upcoming_event_name,
            "data_mode": "full",
            "source": "upcoming_event_model",
        },
        "diagnostics": {
            "market_counts": ingest_summary.get("market_counts") or {},
            "live_state": live_state,
            "upcoming_state": (upcoming_section.get("diagnostics") or {}).get("state"),
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

