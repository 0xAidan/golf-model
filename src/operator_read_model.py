"""Pure, fail-closed projections over live-refresh snapshot data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.operator_contract import (
    SCHEMA_VERSION,
    BoardContract,
    BoardMetadataContract,
    BootstrapContract,
    DataState,
    MarketCountContract,
    OperatorMode,
    OperatorTrack,
    ReasonContract,
)


_SECTION_BY_TRACK_AND_MODE: dict[tuple[OperatorTrack, OperatorMode], str] = {
    ("champion", "live"): "live_tournament",
    ("champion", "upcoming"): "upcoming_tournament",
    ("challenger", "live"): "lab_live_tournament",
    ("challenger", "upcoming"): "lab_upcoming_tournament",
}


def section_name_for(track: OperatorTrack, mode: OperatorMode) -> str:
    """Return the sole snapshot section allowed for a track and mode."""
    if mode == "past":
        return "completed"
    return _SECTION_BY_TRACK_AND_MODE[(track, mode)]


def _reason(code: str, message: str) -> ReasonContract:
    return {"code": code, "message": message}


def _parse_generated_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _snapshot_metadata(
    snapshot: dict[str, Any] | None,
    *,
    stale_after_seconds: int,
    now: datetime,
    require_timestamp: bool = True,
) -> tuple[dict[str, Any], DataState | None, ReasonContract | None]:
    if not isinstance(snapshot, dict) or not snapshot:
        return (
            {
                "snapshot_id": None,
                "generated_at": None,
                "age_seconds": None,
                "stale_after_seconds": stale_after_seconds,
            },
            DataState.UNAVAILABLE,
            _reason("snapshot_unavailable", "No live-refresh snapshot is available."),
        )

    generated_at = snapshot.get("generated_at")
    parsed_generated_at = _parse_generated_at(generated_at)
    age_seconds = None
    if parsed_generated_at:
        age_seconds = max(0, int((now - parsed_generated_at).total_seconds()))
    source = {
        "snapshot_id": _string_or_none(snapshot.get("snapshot_id")),
        "generated_at": _string_or_none(generated_at),
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
    }
    if parsed_generated_at is None and require_timestamp:
        return (
            source,
            DataState.UNAVAILABLE,
            _reason("snapshot_timestamp_invalid", "Snapshot time is missing or invalid; freshness cannot be verified."),
        )
    if age_seconds is not None and age_seconds > stale_after_seconds:
        return (
            source,
            DataState.STALE,
            _reason("snapshot_stale", "The snapshot is older than the operator freshness window."),
        )
    return source, None, None


def _string_or_none(value: object) -> str | None:
    value_as_string = str(value).strip() if value is not None else ""
    return value_as_string or None


def _section_event_id(section: dict[str, Any]) -> str | None:
    eligibility = section.get("eligibility")
    eligibility = eligibility if isinstance(eligibility, dict) else {}
    return _string_or_none(
        section.get("source_event_id")
        or section.get("tournament_id")
        or eligibility.get("field_event_id")
    )


def _eligible_section(
    section: dict[str, Any],
    *,
    requested_event_id: str | None,
) -> ReasonContract | None:
    eligibility = section.get("eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("verified") is not True:
        code = str(eligibility.get("code") or "field_verification_failed") if isinstance(eligibility, dict) else "field_verification_failed"
        return _reason(code, "Board rows are withheld until field verification succeeds.")

    section_event_id = _section_event_id(section)
    if requested_event_id and section_event_id and requested_event_id != section_event_id:
        return _reason(
            "event_identity_mismatch",
            "The requested event does not match the snapshot section event.",
        )
    return None


def _rows(section: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw_rows = section.get(key)
    if not isinstance(raw_rows, list):
        return []
    return [dict(row) for row in raw_rows if isinstance(row, dict)]


def _value_rows(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten display markets without changing any supplied pricing fields."""
    value_bets = section.get("value_bets")
    if not isinstance(value_bets, dict):
        return _rows(section, "value_bets")
    rows: list[dict[str, Any]] = []
    for market, raw_rows in value_bets.items():
        if not isinstance(market, str) or not market.strip() or not isinstance(raw_rows, list):
            continue
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            if not row.get("bet_type"):
                row["bet_type"] = market
            rows.append(row)
    return rows


def _display_metadata(section: dict[str, Any]) -> BoardMetadataContract:
    """Allowlist ingest counts; research rows never become executable picks."""
    metadata: BoardMetadataContract = {}
    diagnostics = section.get("diagnostics")
    market_counts = diagnostics.get("market_counts") if isinstance(diagnostics, dict) else None
    if isinstance(market_counts, dict):
        counts: dict[str, MarketCountContract] = {}
        for market, raw in market_counts.items():
            if not isinstance(market, str) or not isinstance(raw, dict):
                continue
            entry: MarketCountContract = {}
            raw_rows = raw.get("raw_rows")
            if type(raw_rows) is int and raw_rows >= 0:
                entry["raw_rows"] = raw_rows
            reason_code = raw.get("reason_code")
            if "reason_code" in raw and (reason_code is None or isinstance(reason_code, str)):
                entry["reason_code"] = reason_code
            if entry:
                counts[market] = entry
        metadata["market_counts"] = counts
    shadow_groups = section.get("live_groups_shadow")
    if isinstance(shadow_groups, list):
        metadata["research_counts"] = {
            "live_groups_shadow": sum(isinstance(row, dict) for row in shadow_groups),
        }
    return metadata


def _board(
    *,
    track: OperatorTrack,
    mode: OperatorMode,
    source: dict[str, Any],
    section: dict[str, Any] | None,
    state: DataState,
    reason: ReasonContract,
) -> BoardContract:
    safe_section = section or {}
    eligibility = safe_section.get("eligibility")
    return {
        "schema_version": SCHEMA_VERSION,
        "track": track,
        "mode": mode,
        "state": state.value,
        "reason": reason,
        "event": {
            "event_id": _section_event_id(safe_section),
            "event_name": _string_or_none(safe_section.get("event_name")),
            "course_name": _string_or_none(safe_section.get("course_name")),
        },
        "source": {**source, "section": section_name_for(track, mode)},
        "eligibility": dict(eligibility) if isinstance(eligibility, dict) else {},
        "rankings": [],
        "leaderboard": [],
        "picks": {"matchups": [], "value_bets": []},
    }


def build_board(
    snapshot: dict[str, Any] | None,
    *,
    track: OperatorTrack,
    mode: OperatorMode,
    event_id: str | None = None,
    stale_after_seconds: int = 900,
    split_brain_reasons: list[str] | None = None,
    refreshing: bool = False,
    now: datetime | None = None,
) -> BoardContract:
    """Project one track section without invoking model code or fallback lanes."""
    current_time = now or datetime.now(timezone.utc)
    source, snapshot_state, snapshot_reason = _snapshot_metadata(
        snapshot,
        stale_after_seconds=stale_after_seconds,
        now=current_time,
        require_timestamp=mode != "past",
    )
    if split_brain_reasons:
        return _board(
            track=track,
            mode=mode,
            source=source,
            section=None,
            state=DataState.UNAVAILABLE,
            reason=_reason("split_brain_detected", "Rows are withheld while runtime identity is inconsistent."),
        )
    if snapshot_state == DataState.UNAVAILABLE:
        return _board(
            track=track,
            mode=mode,
            source=source,
            section=None,
            state=snapshot_state,
            reason=snapshot_reason or _reason("snapshot_unavailable", "Snapshot unavailable."),
        )

    section_key = section_name_for(track, mode)
    section = (snapshot or {}).get(section_key)
    if not isinstance(section, dict):
        code = "challenger_lane_unavailable" if track == "challenger" else "section_unavailable"
        return _board(
            track=track,
            mode=mode,
            source=source,
            section=None,
            state=DataState.UNAVAILABLE,
            reason=_reason(code, "The requested track section is not available in this snapshot."),
        )

    eligibility_reason = _eligible_section(section, requested_event_id=event_id)
    if eligibility_reason:
        return _board(
            track=track,
            mode=mode,
            source=source,
            section=section,
            state=DataState.UNAVAILABLE,
            reason=eligibility_reason,
        )

    rankings = _rows(section, "rankings")
    leaderboard = _rows(section, "leaderboard")
    matchups = _rows(section, "matchup_bets_all_books") or _rows(section, "matchup_bets")
    value_bets = _value_rows(section)
    if snapshot_state == DataState.STALE:
        state = DataState.STALE
        reason = snapshot_reason or _reason("snapshot_stale", "Snapshot stale.")
    elif refreshing:
        state = DataState.REFRESHING
        reason = _reason("refresh_in_progress", "A newer snapshot is being prepared.")
    elif not rankings and not leaderboard and not matchups and not value_bets:
        state = DataState.EMPTY
        reason = _reason("no_display_rows", "The verified event currently has no display rows.")
    else:
        state = DataState.FRESH
        reason = _reason("ready", "The board is ready.")

    board = _board(
        track=track,
        mode=mode,
        source=source,
        section=section,
        state=state,
        reason=reason,
    )
    board["rankings"] = rankings
    board["leaderboard"] = leaderboard
    board["picks"] = {"matchups": matchups, "value_bets": value_bets}
    metadata = _display_metadata(section)
    if metadata:
        board["metadata"] = metadata
    return board


def build_bootstrap(
    snapshot: dict[str, Any] | None,
    *,
    stale_after_seconds: int = 900,
    split_brain_reasons: list[str] | None = None,
    refreshing: bool = False,
    now: datetime | None = None,
) -> BootstrapContract:
    """Return compact operator metadata using the same board eligibility gate."""
    current_time = now or datetime.now(timezone.utc)
    source, snapshot_state, snapshot_reason = _snapshot_metadata(
        snapshot,
        stale_after_seconds=stale_after_seconds,
        now=current_time,
    )
    boards = {
        track: {
            mode: build_board(
                snapshot,
                track=track,  # type: ignore[arg-type]
                mode=mode,  # type: ignore[arg-type]
                stale_after_seconds=stale_after_seconds,
                split_brain_reasons=split_brain_reasons,
                refreshing=refreshing,
                now=current_time,
            )
            for mode in ("live", "upcoming")
        }
        for track in ("champion", "challenger")
    }
    track_summary = {
        track: {
            mode: {
                "available": board["state"] not in {DataState.UNAVAILABLE.value, DataState.ERROR.value},
                "event_id": board["event"].get("event_id"),
                "event_name": board["event"].get("event_name"),
                "state": board["state"],
                "reason": board["reason"],
            }
            for mode, board in modes.items()
        }
        for track, modes in boards.items()
    }
    if split_brain_reasons:
        state = DataState.UNAVAILABLE
        reason = _reason("split_brain_detected", "Rows are withheld while runtime identity is inconsistent.")
    elif snapshot_state is not None:
        state = snapshot_state
        reason = snapshot_reason or _reason("snapshot_unavailable", "Snapshot unavailable.")
    elif refreshing:
        state = DataState.REFRESHING
        reason = _reason("refresh_in_progress", "A newer snapshot is being prepared.")
    else:
        state = DataState.FRESH
        reason = _reason("ready", "Operator metadata is ready.")
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state.value,
        "reason": reason,
        "source": source,
        "tracks": track_summary,
    }
