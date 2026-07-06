"""Shared helpers for acquiring and normalizing tournament results."""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.datagolf import _call_api, auto_ingest_results
from src.player_normalizer import display_name, normalize_name

logger = logging.getLogger(__name__)


def fetch_event_results(event_id: str, year: int) -> list[dict]:
    """Fetch final results from DG historical-event-data/events."""
    raw = _call_api(
        "historical-event-data/events",
        {
            "tour": "pga",
            "event_id": event_id,
            "year": year,
        },
    )
    if not raw:
        return []

    results: list[dict] = []
    players = raw if isinstance(raw, list) else raw.get("results", raw.get("players", []))
    if isinstance(raw, dict) and not players:
        for key in raw:
            if isinstance(raw[key], list) and len(raw[key]) > 0:
                players = raw[key]
                break

    for player in players:
        fin_text = str(player.get("fin_text", "")).strip()
        player_name = player.get("player_name", "")
        dg_id = player.get("dg_id")

        if not player_name or not fin_text:
            continue

        finish_pos = None
        made_cut = 1
        fin_upper = fin_text.upper().replace(" ", "")

        if fin_upper in ("CUT", "MC"):
            made_cut = 0
        elif fin_upper in ("WD", "W/D", "DQ"):
            made_cut = 0
        else:
            try:
                finish_pos = int(fin_upper.replace("T", ""))
            except ValueError:
                pass

        player_key = normalize_name(player_name)
        results.append(
            {
                "player_key": player_key,
                "player_display": display_name(player_name),
                "dg_id": dg_id,
                "finish_position": finish_pos,
                "finish_text": fin_text,
                "made_cut": made_cut,
            }
        )

    return results


def acquire_event_results(
    event_id: str,
    year: int,
    *,
    tournament_id: int,
) -> dict[str, Any]:
    """Fetch DG results or fall back to rounds-derived results and persist them."""
    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        return {"status": "no_data", "reason": "missing_event_id"}

    results = fetch_event_results(normalized_event_id, year)
    if results:
        db.store_results(tournament_id, results)
        return {
            "status": "ok",
            "source": "dg_api",
            "results_stored": len(results),
        }

    rounds_summary = auto_ingest_results(tournament_id, normalized_event_id, year)
    stored = int(rounds_summary.get("results_stored") or 0)
    if rounds_summary.get("status") == "ok" and stored > 0:
        return {
            "status": "ok",
            "source": "rounds",
            "results_stored": stored,
            "rounds_summary": rounds_summary,
        }

    return {
        "status": "no_data",
        "source": None,
        "dg_count": 0,
        "rounds_summary": rounds_summary,
    }
