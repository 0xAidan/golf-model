"""
Always-on live refresh runtime for dashboard snapshots.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src import db
from src.atomic_io import atomic_write_json
from src.datagolf import fetch_in_play_predictions, parse_in_play_leaderboard
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
    atomic_write_json(_SNAPSHOT_PATH, payload)


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


def _is_cut_or_inactive(finish_state: str | None) -> bool:
    if not finish_state:
        return False
    state = str(finish_state).strip().upper()
    return state in {"CUT", "MDF", "WD", "DQ", "DNS"}


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
        if rank >= limit:
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
        scored.append((adjusted, base, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    rankings: list[dict] = []
    rank = 0
    for adjusted, base, row in scored[:30]:
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
    source_used = "live_point_in_time_model_dg_blend" if (
        dg_w
        and scored
        and any(str(r.get("player_key") or "").strip().lower() in dg_w for _, _, r in scored)
    ) else "live_point_in_time_model_tournament_state"
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
    matchup_rows = section.get("matchup_bets_all_books") or section.get("matchup_bets") or []
    for bet in matchup_rows:
        ev = float(bet.get("ev") or 0.0)
        model_prob = bet.get("model_win_prob")
        implied_prob = bet.get("implied_prob")
        odds = _normalize_market_odds(bet.get("odds"), bet.get("market_odds"))
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "generated_at": generated_at,
                "tour": str(tour or "").strip().lower() or None,
                "section": section_name,
                "event_id": event_id,
                "event_name": event_name,
                "market_family": "matchup",
                "market_type": str(bet.get("market_type") or "tournament_matchups"),
                "player_key": str(bet.get("pick_key") or bet.get("player_key") or "").strip() or None,
                "player_display": str(bet.get("pick") or bet.get("player") or "").strip() or None,
                "opponent_key": str(bet.get("opponent_key") or "").strip() or None,
                "opponent_display": str(bet.get("opponent") or "").strip() or None,
                "book": str(bet.get("book") or bet.get("bookmaker") or "").strip() or None,
                "odds": odds,
                "model_prob": float(model_prob) if model_prob is not None else None,
                "implied_prob": float(implied_prob) if implied_prob is not None else None,
                "ev": ev,
                "is_value": 1 if ev > 0 else 0,
                "payload_json": json.dumps(bet),
            }
        )

    for market_type, bets in (section.get("value_bets") or {}).items():
        for bet in bets or []:
            model_prob = bet.get("model_prob")
            implied_prob = bet.get("market_prob")
            ev = float(bet.get("ev") or 0.0)
            odds = _normalize_market_odds(bet.get("odds"), bet.get("best_odds"))
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "generated_at": generated_at,
                    "tour": str(tour or "").strip().lower() or None,
                    "section": section_name,
                    "event_id": event_id,
                    "event_name": event_name,
                    "market_family": "placement",
                    "market_type": str(market_type),
                    "player_key": str(bet.get("player_key") or "").strip() or None,
                    "player_display": str(bet.get("player_display") or bet.get("player") or "").strip() or None,
                    "opponent_key": None,
                    "opponent_display": None,
                    "book": str(bet.get("book") or bet.get("best_book") or "").strip() or None,
                    "odds": odds,
                    "model_prob": float(model_prob) if model_prob is not None else None,
                    "implied_prob": float(implied_prob) if implied_prob is not None else None,
                    "ev": ev,
                    "is_value": 1 if bool(bet.get("is_value")) else 0,
                    "payload_json": json.dumps(bet),
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


def _run_recompute(tour: str, cadence_mode: str, ingest_summary: dict[str, Any]) -> dict[str, Any]:
    mode = "full" if cadence_mode != "live_window" else "round-matchups"
    live_course = str(ingest_summary.get("course") or "").split(";")[0].strip() or None
    live_result = run_snapshot_analysis(
        tour=tour,
        event_id=str(ingest_summary.get("event_id") or "") or None,
        tournament_name=str(ingest_summary.get("event_name") or "").strip() or None,
        course_name=live_course,
        mode=mode,
        enable_ai=False,
        enable_backfill=False,
    )
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

    resolved_completed_event_name = str(ingest_summary.get("latest_completed_event_name") or event_name or "").strip()
    resolved_completed_event_id = str(ingest_summary.get("latest_completed_event_id") or live_event_id or "").strip()
    resolved_completed_event_course = str(ingest_summary.get("latest_completed_event_course") or "").strip()
    live_event_name = event_name if live_is_active else (resolved_completed_event_name or event_name)
    live_source_event_id = str(
        ingest_summary.get("event_id") if live_is_active else resolved_completed_event_id
    ).strip()
    live_source_event_year_raw = (
        ingest_summary.get("event_year")
        if live_is_active
        else (ingest_summary.get("latest_completed_event_year") or ingest_summary.get("event_year"))
    )
    try:
        live_source_event_year = int(live_source_event_year_raw) if live_source_event_year_raw is not None else None
    except (TypeError, ValueError):
        live_source_event_year = None

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
            )
        except Exception as exc:
            _logger.warning("Upcoming snapshot recompute failed; attempting verified snapshot fallback: %s", exc)
            upcoming_result = {}

    if upcoming_result:
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
        upcoming_state = _classify_matchup_state(
            market_counts=ingest_summary.get("market_counts"),
            diagnostics_state=upcoming_diag.get("state"),
            selected_rows=upcoming_selected_rows,
            errors=upcoming_diag.get("errors"),
        )
        if not upcoming_eligibility.get("verified"):
            upcoming_state = "eligibility_failed"
        upcoming_section = {
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
            "value_bets": (
                upcoming_value_bets
                if upcoming_eligibility.get("verified")
                else {}
            ),
            "card_path": upcoming_result.get("output_file") or upcoming_result.get("card_filepath"),
            "source_event_id": str(upcoming_row.get("event_id") or ""),
            "source_event_name": upcoming_event_name,
            "generated_from": "upcoming_event_model",
            "source_card_path": upcoming_result.get("output_file") or upcoming_result.get("card_filepath"),
            "ranking_source": "upcoming_event_model",
            "eligibility": upcoming_eligibility,
            "verification_error": upcoming_result.get("verification_error"),
            "diagnostics": {
                "market_counts": ingest_summary.get("market_counts") or {},
                "selection_counts": upcoming_diag.get("selection_counts") or {},
                "adaptation_state": upcoming_diag.get("adaptation_state", "normal"),
                "reason_codes": upcoming_diag.get("reason_codes") or {},
                "value_filters": upcoming_value_filters,
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

    live_diag = live_result.get("matchup_diagnostics") or {}
    live_selection_counts = live_diag.get("selection_counts") or {}
    live_selected_rows = int(live_selection_counts.get("all_qualifying_rows", live_selection_counts.get("selected_rows", 0)))
    live_state = _classify_matchup_state(
        market_counts=ingest_summary.get("market_counts"),
        diagnostics_state=live_diag.get("state"),
        selected_rows=live_selected_rows,
        errors=live_diag.get("errors"),
    )
    live_eligibility = base_section.get("eligibility") or {}
    pre_tournament_rankings = _extract_rankings(
        live_result.get("composite_results") or [],
        finish_states=finish_states,
        exclude_cut_players=live_is_active,
    )
    live_rankings = pre_tournament_rankings
    live_ranking_source = "current_event_model"
    live_point_in_time_source: str | None = None
    dg_win_prob: dict[str, float] = {}
    leaderboard_source = "rounds_table"
    in_play_parse_note: str | None = None
    dg_leaderboard: list[dict] = []
    if live_is_active:
        try:
            raw_in_play = fetch_in_play_predictions(tour=tour)
            dg_leaderboard, dg_win_prob, in_play_parse_note = parse_in_play_leaderboard(raw_in_play)
            if dg_leaderboard:
                leaderboard_source = "datagolf_in_play"
        except Exception as exc:
            _logger.warning("Data Golf in-play fetch failed: %s", exc)
            in_play_parse_note = str(exc)
    live_leaderboard = dg_leaderboard if dg_leaderboard else _load_event_leaderboard_rows(
        live_source_event_id,
        year=live_source_event_year,
    )
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

    if not live_eligibility.get("verified"):
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
    elif not live_is_active:
        # Non-live windows should still use current event model context, not older card parsing.
        live_ranking_source = "current_event_model_fallback"

    live_diag_errors = live_diag.get("errors") or []
    if not live_eligibility.get("verified"):
        live_diag_errors = live_diag_errors + [
            live_eligibility.get("summary"),
            live_eligibility.get("action"),
        ]

    snapshot = {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "cadence_mode": cadence_mode,
        "event_context": {
            "tour": tour,
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
            "leaderboard": live_leaderboard,
            "leaderboard_source": leaderboard_source,
            "in_play_parse_note": in_play_parse_note,
            "rankings": live_rankings,
            "live_rankings": live_rankings,
            "pre_tournament_rankings": pre_tournament_rankings,
            "live_point_in_time_source": live_point_in_time_source,
            "matchups": live_matchups,
            "matchup_bets": live_board_matchup_bets,
            "matchup_bets_all_books": live_board_matchup_bets_all_books,
            "value_bets": live_value_bets,
            "source_event_id": live_source_event_id,
            "source_event_name": event_name if live_is_active else (resolved_completed_event_name or event_name),
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
                "state": live_state,
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
        "diagnostics": {
            "market_counts": ingest_summary.get("market_counts") or {},
            "live_state": live_state,
            "upcoming_state": (upcoming_section.get("diagnostics") or {}).get("state"),
        },
    }
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
    try:
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
        market_rows.extend(
            _build_market_prediction_rows(
                snapshot_id=snapshot_id,
                generated_at=generated_at,
                tour=tour,
                section_name="live",
                section_payload=snapshot.get("live_tournament"),
            )
        )
        market_rows.extend(
            _build_market_prediction_rows(
                snapshot_id=snapshot_id,
                generated_at=generated_at,
                tour=tour,
                section_name="upcoming",
                section_payload=snapshot.get("upcoming_tournament"),
            )
        )
        market_rows_written = db.store_market_prediction_rows(market_rows)
        snapshot.setdefault("diagnostics", {})["market_rows_written"] = market_rows_written
    except Exception as exc:
        _logger.warning("Failed to persist market prediction rows: %s", exc)
        snapshot.setdefault("diagnostics", {})["market_rows_written"] = 0
        snapshot.setdefault("diagnostics", {})["market_rows_write_error"] = str(exc)
    _write_snapshot(snapshot)
    return snapshot


def generate_snapshot_once(*, tour: str = "pga") -> dict[str, Any]:
    """Run one ingest+recompute cycle synchronously and return the snapshot."""
    from src.autoresearch_settings import get_settings

    settings = get_settings().get("live_refresh", {})
    cadence = resolve_cadence(settings)
    ingest_summary = _run_ingest(tour)
    snapshot = _run_recompute(tour, cadence.mode, ingest_summary)
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

