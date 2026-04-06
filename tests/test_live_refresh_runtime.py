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
                "matchup_diagnostics": {
                    "market_counts": {"tournament_matchups": {"raw_rows": 4, "reason_code": "ok"}},
                    "selection_counts": {"input_rows": 4, "selected_rows": 1},
                    "reason_codes": {"below_ev_threshold": 3},
                    "state": "edges_available",
                    "errors": [],
                },
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
            "matchup_diagnostics": {
                "market_counts": {"round_matchups": {"raw_rows": 2, "reason_code": "ok"}},
                "selection_counts": {"input_rows": 2, "selected_rows": 1},
                "reason_codes": {"below_ev_threshold": 1},
                "state": "edges_available",
                "errors": [],
            },
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
            "market_counts": {"tournament_matchups": {"raw_rows": 3, "reason_code": "ok"}},
        },
    )

    assert len(calls) == 2
    assert calls[0]["mode"] == "round-matchups"
    assert calls[1]["mode"] == "full"
    assert calls[1]["tournament_name"] == "Next Event"
    assert snapshot["upcoming_tournament"]["event_name"] == "Next Event"
    assert snapshot["upcoming_tournament"]["generated_from"] == "upcoming_event_model"
    assert snapshot["upcoming_tournament"]["ranking_source"] == "upcoming_event_model"
    assert snapshot["upcoming_tournament"]["diagnostics"]["state"] == "edges_available"


def test_run_recompute_uses_previous_card_rankings_when_not_live(monkeypatch, tmp_path):
    from backtester import dashboard_runtime as runtime

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    card_path = output_dir / "valero_texas_open_20260405.md"
    card_path.write_text(
        "\n".join(
            [
                "# Valero Texas Open — Betting Card",
                "## Model Rankings (Top 20)",
                "| Rank | Player | Composite | Course Fit | Form | Momentum | Trend |",
                "|------|--------|-----------|------------|------|----------|-------|",
                "| 1 | Rory McIlroy | 84.2 | 79.0 | 82.1 | 77.4 | ↑ |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime, "_OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        runtime,
        "run_snapshot_analysis",
        lambda **kwargs: {
            "event_name": "Current Event",
            "course_name": "Current Course",
            "field_size": 70,
            "composite_results": [],
            "matchup_bets": [],
            "output_file": "output/current_event.md",
            "matchup_diagnostics": {
                "market_counts": {"tournament_matchups": {"raw_rows": 0, "reason_code": "empty_match_list"}},
                "selection_counts": {"input_rows": 0, "selected_rows": 0},
                "reason_codes": {},
                "state": "no_market_posted_yet",
                "errors": [],
            },
        },
    )
    monkeypatch.setattr(runtime, "_load_finish_state_map", lambda event_id, year=None: {})
    monkeypatch.setattr(runtime, "_write_snapshot", lambda payload: None)

    snapshot = runtime._run_recompute(
        "pga",
        "off_window",
        {
            "event_name": "Current Event",
            "event_id": "700",
            "course": "Current Course",
            "upcoming_event_names": ["Current Event"],
            "live_event_active": False,
            "latest_completed_event_name": "Valero Texas Open",
            "latest_completed_event_id": "500",
            "market_counts": {"tournament_matchups": {"raw_rows": 0, "reason_code": "empty_match_list"}},
        },
    )

    live = snapshot["live_tournament"]
    assert live["event_name"] == "Valero Texas Open"
    assert live["ranking_source"] == "previous_card_snapshot"
    assert live["source_card_path"] == str(card_path)
    assert live["rankings"][0]["player"] == "Rory McIlroy"


def test_run_recompute_completed_event_never_equals_upcoming_when_completed_missing(monkeypatch, tmp_path):
    from backtester import dashboard_runtime as runtime

    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    manual_card = downloads_dir / "valero_texas_open_20260331.md"
    manual_card.write_text(
        "\n".join(
            [
                "# Valero Texas Open — Betting Card",
                "## Model Rankings (Top 20)",
                "| Rank | Player | Composite | Course Fit | Form | Momentum | Trend |",
                "|------|--------|-----------|------------|------|----------|-------|",
                "| 1 | Ludvig Aberg | 57.6 | 67.3 | 91.8 | 69.1 | ↑↑ |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime, "_DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(runtime, "_OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(
        runtime,
        "run_snapshot_analysis",
        lambda **kwargs: {
            "event_name": "Masters Tournament",
            "course_name": "Augusta National",
            "field_size": 70,
            "composite_results": [],
            "matchup_bets": [],
            "output_file": "output/current_event.md",
            "matchup_diagnostics": {
                "market_counts": {"tournament_matchups": {"raw_rows": 0, "reason_code": "empty_match_list"}},
                "selection_counts": {"input_rows": 0, "selected_rows": 0},
                "reason_codes": {},
                "state": "no_market_posted_yet",
                "errors": [],
            },
        },
    )
    monkeypatch.setattr(runtime, "_load_finish_state_map", lambda event_id, year=None: {})
    monkeypatch.setattr(runtime, "_write_snapshot", lambda payload: None)

    snapshot = runtime._run_recompute(
        "pga",
        "off_window",
        {
            "event_name": "Masters Tournament",
            "event_id": "999",
            "course": "Augusta National",
            "upcoming_event_names": ["Masters Tournament"],
            "live_event_active": False,
            "latest_completed_event_name": "",
            "latest_completed_event_id": "",
            "upcoming_event_row": {"event_id": "1000", "event_name": "Masters Tournament", "course": "Augusta National"},
            "market_counts": {"tournament_matchups": {"raw_rows": 0, "reason_code": "empty_match_list"}},
        },
    )

    assert snapshot["live_tournament"]["event_name"] == "Valero Texas Open"
    assert snapshot["upcoming_tournament"]["event_name"] == "Masters Tournament"
    assert snapshot["live_tournament"]["event_name"] != snapshot["upcoming_tournament"]["event_name"]


def test_run_recompute_excludes_upcoming_card_when_selecting_completed(monkeypatch, tmp_path):
    from backtester import dashboard_runtime as runtime

    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    (downloads_dir / "masters_tournament_20260408.md").write_text(
        "\n".join(
            [
                "# Masters Tournament — Betting Card",
                "## Model Rankings (Top 20)",
                "| Rank | Player | Composite | Course Fit | Form | Momentum | Trend |",
                "|------|--------|-----------|------------|------|----------|-------|",
                "| 1 | Xander Schauffele | 70.0 | 71.0 | 82.0 | 65.0 | ↑ |",
            ]
        ),
        encoding="utf-8",
    )
    (downloads_dir / "valero_texas_open_20260331.md").write_text(
        "\n".join(
            [
                "# Valero Texas Open — Betting Card",
                "## Model Rankings (Top 20)",
                "| Rank | Player | Composite | Course Fit | Form | Momentum | Trend |",
                "|------|--------|-----------|------------|------|----------|-------|",
                "| 1 | Ludvig Aberg | 57.6 | 67.3 | 91.8 | 69.1 | ↑↑ |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime, "_DOWNLOADS_DIR", downloads_dir)
    monkeypatch.setattr(runtime, "_OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(
        runtime,
        "run_snapshot_analysis",
        lambda **kwargs: {
            "event_name": "Masters Tournament",
            "course_name": "Augusta National",
            "field_size": 70,
            "composite_results": [],
            "matchup_bets": [],
            "output_file": "output/current_event.md",
            "matchup_diagnostics": {
                "market_counts": {"tournament_matchups": {"raw_rows": 0, "reason_code": "empty_match_list"}},
                "selection_counts": {"input_rows": 0, "selected_rows": 0},
                "reason_codes": {},
                "state": "no_market_posted_yet",
                "errors": [],
            },
        },
    )
    monkeypatch.setattr(runtime, "_load_finish_state_map", lambda event_id, year=None: {})
    monkeypatch.setattr(runtime, "_write_snapshot", lambda payload: None)

    snapshot = runtime._run_recompute(
        "pga",
        "off_window",
        {
            "event_name": "Masters Tournament",
            "event_id": "999",
            "course": "Augusta National",
            "upcoming_event_names": ["Masters Tournament"],
            "live_event_active": False,
            "latest_completed_event_name": "Masters Tournament",
            "latest_completed_event_id": "999",
            "upcoming_event_row": {"event_id": "999", "event_name": "Masters Tournament", "course": "Augusta National"},
            "market_counts": {"tournament_matchups": {"raw_rows": 0, "reason_code": "empty_match_list"}},
        },
    )

    assert snapshot["live_tournament"]["event_name"] == "Valero Texas Open"
    assert "valero_texas_open" in (snapshot["live_tournament"]["source_card_path"] or "")

