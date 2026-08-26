"""Durable, bounded-cost health-report caches for API read paths."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.db import get_app_metadata, set_app_metadata

OPS_GRADING_HEALTH_KEY = "ops_grading_health"
DATA_HEALTH_REPORT_KEY_PREFIX = "data_health_report"
OPS_GRADING_HEALTH_TTL_SECONDS = 15 * 60
DATA_HEALTH_REPORT_TTL_SECONDS = 6 * 60 * 60


def _cache_key(prefix: str, year: int | None = None) -> str:
    return prefix if year is None else f"{prefix}:{year}"


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _read_cached(key: str, ttl_seconds: int) -> dict[str, Any] | None:
    value = get_app_metadata(key)
    if not isinstance(value, dict):
        return None

    report = value.get("report")
    generated_at = value.get("generated_at")
    if not isinstance(report, dict) or not isinstance(generated_at, str):
        return None

    timestamp = _parse_timestamp(generated_at)
    age_seconds = (
        max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
        if timestamp is not None
        else float("inf")
    )
    return {
        "report": report,
        "generated_at": generated_at,
        "stale": age_seconds > ttl_seconds,
        "ttl_seconds": ttl_seconds,
    }


def _write_cached(key: str, report: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    value = {"report": report, "generated_at": timestamp}
    set_app_metadata(key, value)
    return value


def read_cached_ops_grading_health(
    ttl_seconds: int = OPS_GRADING_HEALTH_TTL_SECONDS,
) -> dict[str, Any] | None:
    return _read_cached(OPS_GRADING_HEALTH_KEY, ttl_seconds)


def write_cached_ops_grading_health(
    report: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return _write_cached(OPS_GRADING_HEALTH_KEY, report, generated_at)


def read_cached_data_health(
    year: int = 2026,
    ttl_seconds: int = DATA_HEALTH_REPORT_TTL_SECONDS,
) -> dict[str, Any] | None:
    return _read_cached(_cache_key(DATA_HEALTH_REPORT_KEY_PREFIX, year), ttl_seconds)


def write_cached_data_health(
    report: dict[str, Any],
    *,
    year: int = 2026,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return _write_cached(_cache_key(DATA_HEALTH_REPORT_KEY_PREFIX, year), report, generated_at)


def refresh_ops_grading_cache() -> dict[str, Any]:
    """Run expensive grading and track checks outside an API request."""
    from src.grading_reconciliation import reconcile_grading

    reconciliation = reconcile_grading(limit_events=5)
    events = reconciliation.get("events") or []
    leftover = next((event for event in events if event.get("has_discrepancy")), None)
    leftover_year = leftover.get("tournament_year") if leftover else None
    try:
        leftover_year_int = int(leftover_year) if leftover_year is not None else None
    except (TypeError, ValueError):
        leftover_year_int = None
    leftover_tid = leftover.get("tournament_id") if leftover else None
    try:
        leftover_tid_int = int(leftover_tid) if leftover_tid is not None else None
    except (TypeError, ValueError):
        leftover_tid_int = None
    leftover_event_id = leftover.get("event_id") if leftover else None
    leftover_event_id = str(leftover_event_id).strip() if leftover_event_id else None
    leftover_name = str(leftover.get("tournament_name") or "").strip() if leftover else None
    grading = {
        "status": reconciliation.get("status"),
        "events_with_ungraded_positive_ev": reconciliation.get("events_with_ungraded_positive_ev"),
        "orphan_outcomes": reconciliation.get("orphan_outcomes"),
        "void_positive_ev_picks": sum(int(event.get("void_positive_ev_picks") or 0) for event in events),
        "ungraded_positive_ev_picks": sum(
            int(event.get("ungraded_positive_ev_picks") or 0) for event in events
        ),
        "leftover_event_name": leftover_name or None,
        "leftover_event_id": leftover_event_id or None,
        "leftover_event_year": leftover_year_int,
        "leftover_tournament_id": leftover_tid_int,
    }

    try:
        from src import track_registry

        listing = track_registry.list_tracks(history_limit=1)
        tracks = {
            "active": {
                track: {
                    "config_hash": row.get("config_hash"),
                    "model_variant": row.get("model_variant"),
                }
                for track, row in (listing.get("tracks") or {}).items()
            },
            "effective_config_hash": listing.get("effective_config_hash"),
            "last_activation": (listing.get("history") or [{}])[0].get("activated_at"),
        }
    except Exception:
        tracks = {"error": "unavailable"}

    report = {"grading": grading, "tracks": tracks}
    write_cached_ops_grading_health(report)
    return report


def refresh_data_health_cache(year: int = 2026) -> dict[str, Any]:
    """Build and persist the full data-health audit outside the event loop."""
    from src.data_health import build_data_health_report
    from src.data_views import ensure_analytics_views

    ensure_analytics_views()
    report = build_data_health_report(year=year)
    write_cached_data_health(report, year=year)
    return report
