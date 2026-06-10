"""Tests for the field-complete player board (engine-scale Wave 2)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.field_board import build_field_board


def _snapshot():
    return {
        "generated_at": "2026-06-10T00:00:00+00:00",
        "snapshot_id": "snap-1",
        "live_tournament": {"active": False},
        "upcoming_tournament": {
            "event_name": "RBC",
            "tournament_id": 42,
            "active": False,
            "rankings": [
                {"rank": 1, "player_key": "a", "player": "Player A", "composite": 80, "course_fit": 1, "form": 2, "momentum": 0.1},
                {"rank": 2, "player_key": "b", "player": "Player B", "composite": 78, "course_fit": 0, "form": 1, "momentum": 0.0},
            ],
            "matchup_bets": [
                {"pick_key": "a", "opponent_key": "b", "ev": 0.06},
            ],
            "value_bets": {"top10": [{"player_key": "b", "is_value": True, "ev": 0.09}]},
        },
        "lab_upcoming_tournament": {
            "event_name": "RBC",
            "tournament_id": 42,
            "active": False,
            "rankings": [
                {"rank": 5, "player_key": "a", "player": "Player A", "composite": 70},
                {"rank": 1, "player_key": "b", "player": "Player B", "composite": 83},
            ],
        },
    }


def test_field_board_is_field_complete_with_both_tracks():
    board = build_field_board(_snapshot(), section="upcoming")
    assert board["section"] == "upcoming"
    assert board["event_name"] == "RBC"
    assert board["tournament_id"] == 42
    assert board["lab_available"] is True
    assert board["player_count"] == 2

    by_key = {p["player_key"]: p for p in board["players"]}
    a = by_key["a"]
    assert a["champion_rank"] == 1
    assert a["challenger_rank"] == 5
    assert a["rank_delta"] == -4  # champion ranks A much higher than the challenger
    assert a["matchup_count"] == 1
    assert a["in_positive_ev"] is True  # pick side of a +EV matchup

    b = by_key["b"]
    assert b["in_positive_ev"] is True  # +EV value bet
    assert b["rank_delta"] == 1  # champion #2 vs challenger #1


def test_field_board_handles_missing_lab_lane():
    snap = _snapshot()
    snap.pop("lab_upcoming_tournament")
    board = build_field_board(snap, section="upcoming")
    assert board["lab_available"] is False
    assert all(p["challenger_rank"] is None for p in board["players"])


def test_field_board_sg_enrichment_passthrough():
    board = build_field_board(
        _snapshot(),
        section="upcoming",
        sg_by_player={"a": {"sg_ott": 0.5, "sg_app": 0.3}},
    )
    by_key = {p["player_key"]: p for p in board["players"]}
    assert by_key["a"]["has_sg"] is True
    assert by_key["a"]["sg"]["sg_ott"] == 0.5
    assert by_key["b"]["has_sg"] is False


def test_field_board_endpoint(tmp_db, monkeypatch):
    import app as app_module
    from fastapi.testclient import TestClient

    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: _snapshot())
    client = TestClient(app_module.app)
    resp = client.get("/api/players/field-board?section=upcoming")
    assert resp.status_code == 200
    body = resp.json()
    assert body["player_count"] == 2
    assert body["players"][0]["champion_rank"] == 1
