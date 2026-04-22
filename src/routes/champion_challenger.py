"""Champion-challenger evaluation API routes (defect 3.3.1)."""

from fastapi import APIRouter

from src.db import ensure_initialized
from src.evaluation.champion_challenger import summarize_all

router = APIRouter(tags=["champion-challenger"])


@router.get("/api/champion-challenger/summary")
async def get_champion_challenger_summary():
    """Brier / matchup ROI / CLV per model for trailing 14d and 30d windows."""
    ensure_initialized()
    return summarize_all(windows_days=(14, 30))
