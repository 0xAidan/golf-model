"""Tests for live refresh policy and API endpoints."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


def test_live_refresh_policy_detects_live_window():
    from src.live_refresh_policy import detect_window_mode

    dt = datetime(2026, 4, 9, 13, 0, tzinfo=ZoneInfo("America/New_York"))  # Thursday 1pm ET
    assert detect_window_mode(now=dt) == "live_window"


def test_live_refresh_policy_detects_off_window():
    from src.live_refresh_policy import detect_window_mode

    dt = datetime(2026, 4, 7, 11, 0, tzinfo=ZoneInfo("America/New_York"))  # Tuesday 11am ET
    assert detect_window_mode(now=dt) == "off_window"


def test_live_refresh_status_endpoint(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.dashboard_runtime.get_live_refresh_status",
        lambda: {"running": True, "cadence_mode": "live_window"},
    )
    monkeypatch.setattr(
        "src.autoresearch_settings.get_settings",
        lambda: {"live_refresh": {"enabled": True, "tour": "pga"}},
    )

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"]["running"] is True
    assert body["settings"]["tour"] == "pga"


def test_live_refresh_snapshot_endpoint_handles_missing_snapshot(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {})

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["snapshot"] is None


def test_live_refresh_start_and_stop_endpoints(monkeypatch):
    import app as app_module

    calls = {"set_settings": []}

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "src.autoresearch_settings.get_settings",
        lambda: {"live_refresh": {"enabled": False, "tour": "pga"}},
    )
    monkeypatch.setattr(
        "src.autoresearch_settings.set_settings",
        lambda payload: calls["set_settings"].append(payload) or payload,
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.start_live_refresh",
        lambda tour="pga": {"running": True, "tour": tour},
    )
    monkeypatch.setattr(
        "backtester.dashboard_runtime.stop_live_refresh",
        lambda: {"running": False},
    )

    client = TestClient(app_module.app)
    start_response = client.post("/api/live-refresh/start", json={"tour": "pga"})
    stop_response = client.post("/api/live-refresh/stop")

    assert start_response.status_code == 200
    assert start_response.json()["status"]["running"] is True
    assert stop_response.status_code == 200
    assert stop_response.json()["status"]["running"] is False
    assert calls["set_settings"], "Expected settings updates when starting/stopping live refresh."


def test_extract_matchups_normalizes_pick_schema():
    from backtester import dashboard_runtime as runtime

    rows = runtime._extract_matchups(
        [
            {
                "pick": "Player A",
                "pick_key": "player_a",
                "opponent": "Player B",
                "opponent_key": "player_b",
                "book": "fanduel",
                "odds": "+112",
                "model_win_prob": 0.58,
                "ev": 0.09,
                "market_type": "tournament_matchups",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["player"] == "Player A"
    assert rows[0]["bookmaker"] == "fanduel"
    assert rows[0]["market_odds"] == "+112"
    assert rows[0]["model_prob"] == 0.58


def test_run_recompute_builds_true_upcoming_section(monkeypatch):
    from backtester import dashboard_runtime as runtime

    calls = []

    def _fake_run_snapshot_analysis(**kwargs):
        calls.append(kwargs)
        event_name = kwargs.get("tournament_name") or "Current Event"
        if event_name == "Next Event":
            return {
                "event_name": "Next Event",
                "course_name": "Next Course",
                "field_size": 70,
                "composite_results": [
                    {
                        "player_key": "n_player",
                        "player_display": "Next Player",
                        "composite": 77.0,
                        "form": 66.0,
                        "course_fit": 70.0,
                        "momentum": 59.0,
                    }
                ],
                "matchup_bets": [
                    {
                        "pick": "Next Player",
                        "pick_key": "n_player",
                        "opponent": "Opp Player",
                        "opponent_key": "opp_player",
                        "book": "draftkings",
                        "odds": "+110",
                        "model_win_prob": 0.56,
                        "ev": 0.07,
                    }
                ],
                "output_file": "output/next_event.md",
            }
        return {
            "event_name": "Current Event",
            "course_name": "Current Course",
            "field_size": 80,
            "composite_results": [
                {
                    "player_key": "c_player",
                    "player_display": "Current Player",
                    "composite": 80.0,
                    "form": 70.0,
                    "course_fit": 72.0,
                    "momentum": 61.0,
                }
            ],
            "matchup_bets": [
                {
                    "pick": "Current Player",
                    "pick_key": "c_player",
                    "opponent": "Opp Current",
                    "opponent_key": "opp_current",
                    "book": "bet365",
                    "odds": "-105",
                    "model_win_prob": 0.55,
                    "ev": 0.05,
                }
            ],
            "output_file": "output/current_event.md",
        }

    monkeypatch.setattr(runtime, "run_snapshot_analysis", _fake_run_snapshot_analysis)
    monkeypatch.setattr(runtime, "_load_finish_state_map", lambda event_id, year=None: {})
    monkeypatch.setattr(runtime, "_write_snapshot", lambda payload: None)

    snapshot = runtime._run_recompute(
        "pga",
        "live_window",
        {
            "event_name": "Current Event",
            "event_id": "123",
            "course": "Current Course",
            "upcoming_event_names": ["Current Event", "Next Event"],
            "live_event_active": True,
            "latest_completed_event_name": "Previous Event",
            "upcoming_event_row": {"event_id": "456", "event_name": "Next Event", "course": "Next Course"},
        },
    )

    assert len(calls) == 2
    assert calls[0]["mode"] == "round-matchups"
    assert calls[1]["mode"] == "full"
    assert calls[1]["tournament_name"] == "Next Event"
    assert snapshot["upcoming_tournament"]["event_name"] == "Next Event"
    assert snapshot["upcoming_tournament"]["generated_from"] == "upcoming_event_model"

