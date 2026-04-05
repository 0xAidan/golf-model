"""
Tournament-aware cadence policy for always-on dashboard refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

ET_ZONE = ZoneInfo("America/New_York")
VALID_MODES = ("off_window", "upcoming_window", "live_window", "settlement_window")


@dataclass(frozen=True)
class LiveRefreshCadence:
    mode: str
    ingest_seconds: int
    recompute_seconds: int


def default_live_refresh_settings() -> dict:
    return {
        "enabled": False,
        "tour": "pga",
        "autostart": False,
        "mode_override": None,
        "off_window": {
            "ingest_seconds": 1800,
            "recompute_seconds": 3600,
        },
        "upcoming_window": {
            "ingest_seconds": 300,
            "recompute_seconds": 900,
        },
        "live_window": {
            "ingest_seconds": 90,
            "recompute_seconds": 300,
        },
        "settlement_window": {
            "ingest_seconds": 600,
            "recompute_seconds": 1200,
        },
    }


def normalize_live_refresh_settings(raw: dict | None) -> dict:
    defaults = default_live_refresh_settings()
    payload = raw if isinstance(raw, dict) else {}
    out = {
        "enabled": bool(payload.get("enabled", defaults["enabled"])),
        "tour": str(payload.get("tour", defaults["tour"]) or "pga").strip().lower()[:20] or "pga",
        "autostart": bool(payload.get("autostart", defaults["autostart"])),
        "mode_override": None,
    }

    override = payload.get("mode_override")
    if isinstance(override, str):
        candidate = override.strip().lower()
        out["mode_override"] = candidate if candidate in VALID_MODES else None

    for mode in VALID_MODES:
        mode_payload = payload.get(mode) if isinstance(payload.get(mode), dict) else {}
        default_mode = defaults[mode]
        ingest = _bounded_int(mode_payload.get("ingest_seconds"), default_mode["ingest_seconds"], 30, 21600)
        recompute = _bounded_int(mode_payload.get("recompute_seconds"), default_mode["recompute_seconds"], 60, 43200)
        out[mode] = {
            "ingest_seconds": ingest,
            "recompute_seconds": recompute,
        }
    return out


def resolve_cadence(settings: dict | None, *, now: datetime | None = None) -> LiveRefreshCadence:
    cfg = normalize_live_refresh_settings(settings)
    mode = cfg.get("mode_override") or detect_window_mode(now=now)
    block = cfg.get(mode) or cfg["upcoming_window"]
    return LiveRefreshCadence(
        mode=mode,
        ingest_seconds=int(block["ingest_seconds"]),
        recompute_seconds=int(block["recompute_seconds"]),
    )


def detect_window_mode(*, now: datetime | None = None) -> str:
    current = now.astimezone(ET_ZONE) if now else datetime.now(ET_ZONE)
    weekday = current.weekday()  # Monday=0
    hour = current.hour

    # Live tournament window default: Thu-Sun daytime/evening ET.
    if weekday in (3, 4, 5, 6) and 5 <= hour <= 22:
        return "live_window"
    # Post-round settlement window (late nights during tournament days).
    if weekday in (3, 4, 5, 6) and (hour > 22 or hour < 5):
        return "settlement_window"
    # Monday-Wednesday is typically off-window research/maintenance.
    if weekday in (0, 1, 2):
        return "off_window"
    # Fallback upcoming prep cadence.
    return "upcoming_window"


def _bounded_int(value, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))

