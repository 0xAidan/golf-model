"""Player HTTP routes backed only by locally ingested data."""

from __future__ import annotations

from fastapi import APIRouter

from src import db
from src.player_profile import build_standalone_profile

router = APIRouter(tags=["players"])


@router.get("/api/players/{player_key}/standalone-profile")
async def get_player_standalone_profile(player_key: str) -> dict:
    """Return a local/cached player profile without a Data Golf request."""
    return build_standalone_profile(player_key)


@router.get("/api/players/search")
async def search_players(q: str = "") -> dict:
    """Search locally stored player names."""
    conn = db.get_conn()
    try:
        if q.strip():
            rows = conn.execute(
                """SELECT DISTINCT player_key, player_name AS player_display FROM rounds
                   WHERE lower(player_name) LIKE lower(?) OR lower(player_key) LIKE lower(?)
                   ORDER BY player_name LIMIT 40""",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT DISTINCT player_key, player_name AS player_display FROM rounds
                   ORDER BY player_name LIMIT 200""",
            ).fetchall()
        return {"players": [dict(row) for row in rows]}
    finally:
        conn.close()
