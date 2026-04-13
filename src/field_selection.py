"""Helpers for normalizing and enforcing strict tournament fields."""

from __future__ import annotations

from typing import Any

from src.player_normalizer import display_name, normalize_name


def normalize_field_entries(field_data: list | dict | None) -> list[dict[str, Any]]:
    """Normalize a DG field-updates payload into one row per player."""
    if isinstance(field_data, list):
        player_list = field_data
    elif isinstance(field_data, dict):
        player_list = []
        for key in ("field", "data", "players"):
            if isinstance(field_data.get(key), list):
                player_list = field_data[key]
                break
        if not player_list and field_data.get("player_name"):
            player_list = [field_data]
    else:
        player_list = []

    normalized: list[dict[str, Any]] = []
    for player in player_list:
        if not isinstance(player, dict):
            continue
        raw_name = str(player.get("player_name") or "").strip()
        player_key = normalize_name(raw_name)
        if not player_key:
            continue

        teetimes = player.get("teetimes")
        if not isinstance(teetimes, list):
            teetimes = []
        round_one_teetime = None
        for slot in teetimes:
            if not isinstance(slot, dict):
                continue
            if int(slot.get("round_num") or 0) == 1 and slot.get("teetime"):
                round_one_teetime = str(slot["teetime"])
                break
        if round_one_teetime is None:
            direct_teetime = player.get("tee_time") or player.get("teetime")
            if direct_teetime:
                round_one_teetime = str(direct_teetime)

        normalized.append(
            {
                "player_key": player_key,
                "player_display": display_name(raw_name),
                "raw_name": raw_name,
                "dg_id": player.get("dg_id"),
                "draftkings": player.get("dk_salary") or player.get("draftkings_salary"),
                "fanduel": player.get("fd_salary") or player.get("fanduel_salary"),
                "teetime": round_one_teetime,
                "teetimes": teetimes,
                "course_name": next(
                    (
                        str(slot.get("course_name"))
                        for slot in teetimes
                        if isinstance(slot, dict) and slot.get("course_name")
                    ),
                    "",
                ),
                "course_num": next(
                    (
                        slot.get("course_num")
                        for slot in teetimes
                        if isinstance(slot, dict) and slot.get("course_num") is not None
                    ),
                    None,
                ),
            }
        )
    return normalized


def extract_field_player_keys(field_data: list | dict | None) -> list[str]:
    """Return unique normalized player keys from a DG field payload."""
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in normalize_field_entries(field_data):
        key = entry["player_key"]
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def filter_rows_to_field(
    rows: list[dict[str, Any]] | None,
    field_keys: list[str] | set[str] | tuple[str, ...] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter ranked/value rows to the strict confirmed field."""
    normalized_field = sorted({str(key).strip().lower() for key in (field_keys or []) if str(key).strip()})
    if not normalized_field:
        # Fail closed: if we do not have a strict field list, do not surface
        # unvalidated players in rankings/value outputs.
        return [], {
            "field_size": 0,
            "kept_rows": 0,
            "extra_player_keys": [],
            "missing_player_keys": [],
            "strict_field_missing": True,
        }

    field_set = set(normalized_field)
    filtered: list[dict[str, Any]] = []
    seen_row_keys: set[str] = set()
    extra_row_keys: set[str] = set()

    for row in rows or []:
        row_key = str(row.get("player_key") or "").strip().lower()
        if not row_key:
            extra_row_keys.add("<missing_player_key>")
            continue
        seen_row_keys.add(row_key)
        if row_key not in field_set:
            extra_row_keys.add(row_key)
            continue
        filtered.append(row)

    missing_player_keys = sorted(field_set - seen_row_keys)
    return filtered, {
        "field_size": len(normalized_field),
        "kept_rows": len(filtered),
        "extra_player_keys": sorted(extra_row_keys),
        "missing_player_keys": missing_player_keys,
    }
