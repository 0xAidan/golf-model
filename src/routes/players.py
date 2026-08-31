"""Player HTTP routes backed only by locally ingested data."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from src import db
from src.db import DatabaseUnavailable
from src.player_photos import photo_index, resolve_photo_file
from src.player_profile import build_standalone_profile

router = APIRouter(tags=["players"])


@router.get("/api/players/photo-index")
async def get_player_photo_index():
    """Country + photo availability for every mapped player_key."""
    db.ensure_initialized()
    if db.is_db_unavailable():
        return JSONResponse({"players": {}, "db_unavailable": True}, status_code=503)
    try:
        conn = db.get_conn()
        try:
            return {"players": photo_index(conn)}
        finally:
            conn.close()
    except DatabaseUnavailable:
        return JSONResponse({"players": {}, "db_unavailable": True}, status_code=503)


@router.get("/api/players/{player_key}/photo")
async def get_player_photo(player_key: str):
    """Serve a locally cached PGA Tour headshot. Never redirects to Cloudinary."""
    db.ensure_initialized()
    if db.is_db_unavailable():
        return JSONResponse({"detail": "database unavailable"}, status_code=503)
    try:
        path = resolve_photo_file(player_key)
    except DatabaseUnavailable:
        return JSONResponse({"detail": "database unavailable"}, status_code=503)
    except (OSError, ValueError) as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)
    if path is None:
        return JSONResponse({"detail": "no photo"}, status_code=404)
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
