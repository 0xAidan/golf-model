"""Data Golf in-play live stats ingestion (E17)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src import config
from src.live_stats_source import live_sg_trajectory_trend, parse_live_stats_from_in_play


def test_parse_live_stats_accepts_representative_payload():
    fetched = datetime(2026, 6, 14, 16, 0, tzinfo=timezone.utc)
    raw = {
        "data": [
            {
                "player_name": "Scottie Scheffler",
                "thru": 14,
                "current_score": -8,
                "round": 3,
                "R3": 67,
                "sg_total": 2.4,
                "sg_ott": 0.8,
                "sg_app": 1.0,
                "sg_arg": 0.3,
                "sg_putt": 0.3,
                "sg_t2g": 2.1,
            }
        ]
    }
    by_player, meta = parse_live_stats_from_in_play(raw, fetched_at=fetched)
    assert meta["live_stats_fresh"] is True
    assert meta["live_model_mode"] == "full_live_stats"
    stats = by_player["scottie_scheffler"]
    assert stats["thru"] == 14
    assert stats["score"] == 67
    assert stats["round"] == 3
    assert stats["round_sg_total"] == 2.4
    assert stats["round_sg_ott"] == 0.8
    assert stats["round_sg_putt"] == 0.3


def test_stale_rows_rejected_by_ttl(monkeypatch):
    monkeypatch.setattr(config, "LIVE_STATS_FRESHNESS_TTL_SECONDS", 120.0)
    fetched = datetime(2026, 6, 14, 16, 0, tzinfo=timezone.utc)
    stale_ts = (fetched - timedelta(seconds=600)).isoformat()
    raw = {
        "data": [
            {
                "player_name": "Rory McIlroy",
                "thru": 10,
                "sg_total": 1.1,
                "updated_at": stale_ts,
            }
        ],
        "updated": stale_ts,
    }
    by_player, meta = parse_live_stats_from_in_play(raw, fetched_at=fetched)
    assert by_player == {}
    assert meta["live_stats_fresh"] is False
    assert meta["live_model_mode"] == "no_live_stats"
    assert meta["players_rejected_stale"] >= 1


def test_live_sg_trajectory_trend_maps_round_sg():
    trend = live_sg_trajectory_trend({"round_sg_total": 2.0})
    assert trend == 0.7
