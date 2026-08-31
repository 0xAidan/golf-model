"""Map player_key → PGA Tour ID and cache headshots on disk.

Photos are served from this process. The frontend never hotlinks Cloudinary.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

from src import db
from src.player_normalizer import normalize_name

_logger = logging.getLogger("golf.player_photos")

PGA_DIRECTORY_URL = os.environ.get(
    "PGA_DIRECTORY_URL",
    "https://orchestrator.pgatour.com/graphql",
)
PGA_DIRECTORY_API_KEY = os.environ.get(
    "PGA_DIRECTORY_API_KEY",
    "da2-gsrx5bibzbb4njvhl7t37wqyl4",
)
HEADSHOT_URL_TEMPLATE = (
    "https://pga-tour-res.cloudinary.com/image/upload/"
    "c_fill,d_headshots_default.png,f_auto,g_face:center,h_200,q_auto,w_200/"
    "headshots_{pga_id}.png"
)
DEFAULT_TOUR_CODES = ("R", "K")
MIN_HEADSHOT_BYTES = 2048
DIRECTORY_TIMEOUT_S = 30
HEADSHOT_TIMEOUT_S = 20

_REPO_ROOT = Path(__file__).resolve().parents[1]
OVERRIDE_PATH = _REPO_ROOT / "data" / "player_photo_overrides.json"
PHOTO_DIR = _REPO_ROOT / "data" / "player_photos"

_DIRECTORY_QUERY = """
query PlayerDirectory($tourCode: TourCode!) {
  playerDirectory(tourCode: $tourCode) {
    tourCode
    players { id firstName lastName country countryFlag isActive }
  }
}
"""


def photo_cache_path(player_key: str) -> Path:
    safe = "".join(ch for ch in player_key if ch.isalnum() or ch in {"_", "-"})
    return PHOTO_DIR / f"{safe}.png"


def load_overrides(path: Path | None = None) -> dict[str, dict[str, str]]:
    target = path or OVERRIDE_PATH
    if not target.is_file():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        player_key = normalize_name(str(key))
        if not player_key:
            continue
        if isinstance(value, str):
            out[player_key] = {"pga_id": value.strip(), "source": "override"}
        elif isinstance(value, dict) and value.get("pga_id"):
            row = {
                "pga_id": str(value["pga_id"]).strip(),
                "source": "override",
            }
            if value.get("country"):
                row["country"] = str(value["country"]).strip()
            out[player_key] = row
    return out


def parse_directory_payload(payload: Any) -> list[dict[str, str]]:
    """Accept GraphQL or a flat {players: [...]} list."""
    players: list[Any] = []
    if isinstance(payload, list):
        players = payload
    elif isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        directory = data.get("playerDirectory") if isinstance(data, dict) else None
        if isinstance(directory, dict) and isinstance(directory.get("players"), list):
            players = directory["players"]
        elif isinstance(data, dict) and isinstance(data.get("players"), list):
            players = data["players"]
        elif isinstance(payload.get("players"), list):
            players = payload["players"]
    parsed: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in players:
        if not isinstance(row, dict):
            continue
        pga_id = str(row.get("id") or row.get("pga_id") or row.get("playerId") or "").strip()
        if not pga_id or pga_id in seen_ids:
            continue
        first = str(row.get("firstName") or row.get("first_name") or "").strip()
        last = str(row.get("lastName") or row.get("last_name") or "").strip()
        display = str(row.get("displayName") or row.get("name") or "").strip()
        if not display:
            display = " ".join(part for part in (first, last) if part)
        key = normalize_name(display)
        if not key:
            continue
        country = str(row.get("countryFlag") or row.get("country") or "").strip()
        seen_ids.add(pga_id)
        parsed.append(
            {
                "pga_id": pga_id,
                "player_key": key,
                "display": display,
                "country": country,
            }
        )
    return parsed


def fetch_pga_directory(tour_codes: tuple[str, ...] = DEFAULT_TOUR_CODES) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for tour_code in tour_codes:
        response = requests.post(
            PGA_DIRECTORY_URL,
            json={
                "operationName": "PlayerDirectory",
                "variables": {"tourCode": tour_code},
                "query": _DIRECTORY_QUERY,
            },
            headers={
                "Content-Type": "application/json",
                "User-Agent": "golf-model-photo-seed/1.0",
                "x-api-key": PGA_DIRECTORY_API_KEY,
            },
            timeout=DIRECTORY_TIMEOUT_S,
        )
        response.raise_for_status()
        merged.extend(parse_directory_payload(response.json()))
    # Prefer first tour (PGA) on duplicate keys.
    by_key: dict[str, dict[str, str]] = {}
    for row in merged:
        by_key.setdefault(row["player_key"], row)
    return list(by_key.values())


def known_player_rows(conn) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT player_key, MAX(player_name) AS player_name FROM (
            SELECT player_key, player_name FROM rounds
            WHERE player_key IS NOT NULL AND TRIM(player_key) != ''
            UNION ALL
            SELECT player_key, player_display AS player_name FROM metrics
            WHERE player_key IS NOT NULL AND TRIM(player_key) != ''
        )
        GROUP BY player_key
        """
    ).fetchall()
    out: list[tuple[str, str]] = []
    for row in rows:
        key = str(row["player_key"] if hasattr(row, "keys") else row[0]).strip()
        name = str((row["player_name"] if hasattr(row, "keys") else row[1]) or "")
        if key:
            out.append((key, name))
    return out


def match_directory(
    directory: list[dict[str, str]],
    known: list[tuple[str, str]],
    overrides: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Name-match local keys to PGA IDs. Overrides always win. Skip collisions."""
    overrides = overrides or {}
    by_key: dict[str, list[dict[str, str]]] = {}
    for row in directory:
        by_key.setdefault(row["player_key"], []).append(row)

    matched: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for player_key, display in known:
        if player_key in overrides:
            item = dict(overrides[player_key])
            item["player_key"] = player_key
            matched.append(item)
            used_ids.add(item["pga_id"])
            continue
        candidates = by_key.get(player_key) or []
        display_key = normalize_name(display)
        if not candidates and display_key and display_key != player_key:
            candidates = by_key.get(display_key) or []
        if len(candidates) != 1:
            continue
        row = candidates[0]
        if row["pga_id"] in used_ids:
            continue
        used_ids.add(row["pga_id"])
        matched.append(
            {
                "player_key": player_key,
                "pga_id": row["pga_id"],
                "country": row.get("country") or "",
                "source": "pga_directory",
            }
        )
    return matched


def upsert_photo_ids(conn, rows: list[dict[str, str]]) -> int:
    for row in rows:
        conn.execute(
            """
            INSERT INTO player_photo_ids (player_key, pga_id, source, country, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(player_key) DO UPDATE SET
                pga_id = excluded.pga_id,
                source = excluded.source,
                country = excluded.country,
                updated_at = datetime('now')
            """,
            (
                row["player_key"],
                row["pga_id"],
                row.get("source") or "pga_directory",
                row.get("country") or None,
            ),
        )
    conn.commit()
    return len(rows)


def seed_photo_ids(conn, directory: list[dict[str, str]] | None = None) -> dict[str, int]:
    overrides = load_overrides()
    directory = directory if directory is not None else fetch_pga_directory()
    known = known_player_rows(conn)
    matched = match_directory(directory, known, overrides)
    written = upsert_photo_ids(conn, matched)
    return {
        "directory": len(directory),
        "known_players": len(known),
        "matched": written,
        "overrides": len(overrides),
    }


def lookup_photo_id(conn, player_key: str) -> dict[str, str] | None:
    row = conn.execute(
        "SELECT player_key, pga_id, source, country FROM player_photo_ids WHERE player_key = ?",
        (player_key,),
    ).fetchone()
    if not row:
        return None
    return {
        "player_key": row["player_key"],
        "pga_id": row["pga_id"],
        "source": row["source"],
        "country": row["country"] or "",
    }


def photo_index(conn) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        "SELECT player_key, pga_id, country FROM player_photo_ids"
    ).fetchall()
    return {
        str(row["player_key"]): {
            "country": row["country"] or "",
            "has_photo": bool(row["pga_id"]),
        }
        for row in rows
    }


def download_headshot(pga_id: str) -> bytes | None:
    url = HEADSHOT_URL_TEMPLATE.format(pga_id=pga_id)
    response = requests.get(
        url,
        headers={"User-Agent": "golf-model-photo-cache/1.0"},
        timeout=HEADSHOT_TIMEOUT_S,
    )
    if response.status_code != 200:
        return None
    content_type = (response.headers.get("content-type") or "").lower()
    body = response.content or b""
    if "png" not in content_type and "jpeg" not in content_type and "jpg" not in content_type:
        if not body.startswith(b"\x89PNG") and not body.startswith(b"\xff\xd8"):
            return None
    if len(body) < MIN_HEADSHOT_BYTES:
        return None
    return body


def ensure_cached_photo(player_key: str, pga_id: str) -> Path | None:
    dest = photo_cache_path(player_key)
    if dest.is_file() and dest.stat().st_size >= MIN_HEADSHOT_BYTES:
        return dest
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    body = download_headshot(pga_id)
    if not body:
        return None
    tmp = dest.with_suffix(".png.tmp")
    tmp.write_bytes(body)
    tmp.replace(dest)
    return dest


def resolve_photo_file(player_key: str) -> Path | None:
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        row = lookup_photo_id(conn, player_key)
    finally:
        conn.close()
    if not row:
        return None
    return ensure_cached_photo(player_key, row["pga_id"])
