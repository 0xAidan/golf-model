"""Tests for live refresh policy and API endpoints."""

import json
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
    monkeypatch.setattr("backtester.dashboard_runtime.get_live_refresh_status", lambda: {"running": True})
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {})
    monkeypatch.setattr("backtester.dashboard_runtime.generate_snapshot_once", lambda tour="pga": {})

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["snapshot"] is None


def test_live_refresh_snapshot_endpoint_generates_snapshot_on_demand(monkeypatch):
    import app as app_module

    generated_snapshot = {
        "generated_at": "2099-01-01T00:00:00+00:00",
        "live_tournament": {"event_name": "Future Open", "diagnostics": {"state": "edges_available"}},
        "upcoming_tournament": {"event_name": "Future Open", "diagnostics": {"state": "edges_available"}},
    }
    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.dashboard_runtime.get_live_refresh_status", lambda: {"running": True})
    monkeypatch.setattr("backtester.dashboard_runtime.read_snapshot", lambda: {})
    monkeypatch.setattr("backtester.dashboard_runtime.generate_snapshot_once", lambda tour="pga": generated_snapshot)

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["snapshot"]["live_tournament"]["event_name"] == "Future Open"


def test_live_refresh_refresh_endpoint_forces_recompute(monkeypatch):
    import app as app_module

    generated_snapshot = {
        "generated_at": "2099-01-01T00:00:00+00:00",
        "live_tournament": {"event_name": "Force Refresh Open", "diagnostics": {"state": "edges_available"}},
        "upcoming_tournament": {"event_name": "Force Refresh Open", "diagnostics": {"state": "edges_available"}},
    }
    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.dashboard_runtime.get_live_refresh_status", lambda: {"running": True})
    monkeypatch.setattr("backtester.dashboard_runtime.generate_snapshot_once", lambda tour="pga": generated_snapshot)

    client = TestClient(app_module.app)
    response = client.post("/api/live-refresh/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["snapshot"]["live_tournament"]["event_name"] == "Force Refresh Open"


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


def test_extract_board_matchup_bets_preserves_all_books_and_filters_non_books():
    from backtester import dashboard_runtime as runtime

    rows = runtime._extract_board_matchup_bets(
        [
            {
                "pick": "Player A",
                "pick_key": "player_a",
                "opponent": "Player B",
                "opponent_key": "player_b",
                "book": "bet365",
                "odds": "+112",
                "model_win_prob": 0.58,
                "implied_prob": 0.47,
                "ev": 0.09,
                "ev_pct": "9.0%",
                "reason": "Strong form edge",
            },
            {
                "pick": "Player A",
                "pick_key": "player_a",
                "opponent": "Player B",
                "opponent_key": "player_b",
                "book": "bovada",
                "odds": "+118",
                "model_win_prob": 0.58,
                "implied_prob": 0.46,
                "ev": 0.11,
                "ev_pct": "11.0%",
                "reason": "Best number posted",
            },
            {
                "pick": "Player A",
                "pick_key": "player_a",
                "opponent": "Player B",
                "opponent_key": "player_b",
                "book": "datagolf",
                "odds": "+120",
                "model_win_prob": 0.58,
                "implied_prob": 0.45,
                "ev": 0.12,
                "ev_pct": "12.0%",
                "reason": "Non-bettable reference",
            },
        ]
    )

    assert [row["book"] for row in rows] == ["bovada", "bet365"]
    assert [row["ev"] for row in rows] == [0.11, 0.09]


def test_extract_board_value_bets_keeps_value_rows_across_books():
    from backtester import dashboard_runtime as runtime

    rows = runtime._extract_board_value_bets(
        {
            "top10": [
                {
                    "player_display": "Player A",
                    "player_key": "player_a",
                    "bet_type": "top10",
                    "odds": "+175",
                    "book": "betonline",
                    "ev": 0.14,
                    "ev_pct": "14.0%",
                    "is_value": True,
                },
                {
                    "player_display": "Player A",
                    "player_key": "player_a",
                    "bet_type": "top10",
                    "odds": "+170",
                    "book": "bet365",
                    "ev": 0.12,
                    "ev_pct": "12.0%",
                    "is_value": True,
                },
                {
                    "player_display": "Player A",
                    "player_key": "player_a",
                    "bet_type": "top10",
                    "odds": "+190",
                    "book": "datagolf",
                    "ev": 0.18,
                    "ev_pct": "18.0%",
                    "is_value": True,
                },
                {
                    "player_display": "Player B",
                    "player_key": "player_b",
                    "bet_type": "top10",
                    "odds": "+220",
                    "book": "fanduel",
                    "ev": 0.01,
                    "ev_pct": "1.0%",
                    "is_value": False,
                },
            ]
        }
    )

    assert list(rows) == ["top10"]
    assert [row["book"] for row in rows["top10"]] == ["betonline", "bet365"]
    assert [row["ev"] for row in rows["top10"]] == [0.14, 0.12]


def test_run_recompute_builds_true_upcoming_section(monkeypatch):
    from backtester import dashboard_runtime as runtime

    calls = []

    def _fake_run_snapshot_analysis(**kwargs):
        calls.append(kwargs)
        event_name = kwargs.get("tournament_name") or "Current Event"
        if event_name == "Next Event":
            return {
                "status": "complete",
                "event_name": "Next Event",
                "course_name": "Next Course",
                "field_size": 70,
                "field_validation": {
                    "strict_field_verified": True,
                    "field_source": "datagolf_field_updates",
                    "expected_event_id": "456",
                    "failed_invariants": [],
                    "major_event": False,
                    "cross_tour_backfill_used": False,
                },
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
                    },
                    {
                        "pick": "Next Player",
                        "pick_key": "n_player",
                        "opponent": "Opp Player",
                        "opponent_key": "opp_player",
                        "book": "betonline",
                        "odds": "+118",
                        "model_win_prob": 0.56,
                        "ev": 0.09,
                    },
                ],
                "matchup_bets_all_books": [
                    {
                        "pick": "Next Player",
                        "pick_key": "n_player",
                        "opponent": "Opp Player",
                        "opponent_key": "opp_player",
                        "book": "betonline",
                        "odds": "+118",
                        "model_win_prob": 0.56,
                        "ev": 0.09,
                    },
                    {
                        "pick": "Next Player",
                        "pick_key": "n_player",
                        "opponent": "Opp Player",
                        "opponent_key": "opp_player",
                        "book": "draftkings",
                        "odds": "+110",
                        "model_win_prob": 0.56,
                        "ev": 0.07,
                    },
                    {
                        "pick": "Next Player",
                        "pick_key": "n_player",
                        "opponent": "Opp Player",
                        "opponent_key": "opp_player",
                        "book": "fanduel",
                        "odds": "+108",
                        "model_win_prob": 0.56,
                        "ev": 0.06,
                    },
                ],
                "value_bets": {
                    "top10": [
                        {
                            "player_display": "Next Player",
                            "player_key": "n_player",
                            "bet_type": "top10",
                            "odds": "+200",
                            "book": "bovada",
                            "ev": 0.13,
                            "ev_pct": "13.0%",
                            "is_value": True,
                        }
                    ]
                },
                "output_file": "output/next_event.md",
                "matchup_diagnostics": {
                    "market_counts": {"tournament_matchups": {"raw_rows": 4, "reason_code": "ok"}},
                    "selection_counts": {"input_rows": 4, "selected_rows": 2, "all_qualifying_rows": 3},
                    "reason_codes": {"below_ev_threshold": 2},
                    "state": "edges_available",
                    "errors": [],
                },
            }
        return {
            "status": "complete",
            "event_name": "Current Event",
            "course_name": "Current Course",
            "field_size": 80,
            "field_validation": {
                "strict_field_verified": True,
                "field_source": "datagolf_field_updates",
                "expected_event_id": "123",
                "failed_invariants": [],
                "major_event": False,
                "cross_tour_backfill_used": False,
            },
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
            "matchup_bets_all_books": [
                {
                    "pick": "Current Player",
                    "pick_key": "c_player",
                    "opponent": "Opp Current",
                    "opponent_key": "opp_current",
                    "book": "bet365",
                    "odds": "-105",
                    "model_win_prob": 0.55,
                    "ev": 0.05,
                },
                {
                    "pick": "Current Player",
                    "pick_key": "c_player",
                    "opponent": "Opp Current",
                    "opponent_key": "opp_current",
                    "book": "fanduel",
                    "odds": "+100",
                    "model_win_prob": 0.55,
                    "ev": 0.04,
                },
            ],
            "value_bets": {"top20": []},
            "output_file": "output/current_event.md",
            "matchup_diagnostics": {
                "market_counts": {"round_matchups": {"raw_rows": 2, "reason_code": "ok"}},
                "selection_counts": {"input_rows": 2, "selected_rows": 1, "all_qualifying_rows": 2},
                "reason_codes": {"below_ev_threshold": 1},
                "state": "edges_available",
                "errors": [],
            },
        }

    monkeypatch.setattr(runtime, "run_snapshot_analysis", _fake_run_snapshot_analysis)
    monkeypatch.setattr(runtime, "_load_finish_state_map", lambda event_id, year=None: {})
    monkeypatch.setattr(runtime, "_write_snapshot", lambda payload: None)
    monkeypatch.setattr(runtime, "read_snapshot", lambda: {})

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
    assert [row["book"] for row in snapshot["upcoming_tournament"]["matchup_bets"]] == ["betonline", "draftkings"]
    assert [row["book"] for row in snapshot["upcoming_tournament"]["matchup_bets_all_books"]] == ["betonline", "draftkings", "fanduel"]
    assert snapshot["upcoming_tournament"]["value_bets"]["top10"][0]["book"] == "bovada"


def test_run_recompute_withholds_unverified_rankings_when_not_live(monkeypatch, tmp_path):
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
                "",
                "## Matchup Value Bets",
                "| Pick | vs | Odds | Model Win% | EV | Conviction | Tier | Book | Why |",
                "|------|----|------|------------|----|------------|------|------|-----|",
                "| **Rory McIlroy** | Scottie Scheffler | +110 | 56.0% | 7.0% | 21 | GOOD | fanduel | Better number |",
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
    monkeypatch.setattr(runtime, "read_snapshot", lambda: {})

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
    assert live["ranking_source"] == "eligibility_failed"
    assert live["rankings"] == []
    assert live["matchups"] == []
    assert live["matchup_bets"] == []
    assert live["eligibility"]["verified"] is False
    assert "field" in live["eligibility"]["summary"].lower()


def test_run_recompute_completed_event_withholds_when_event_context_unverified(monkeypatch, tmp_path):
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
    monkeypatch.setattr(runtime, "read_snapshot", lambda: {})

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

    live = snapshot["live_tournament"]
    assert live["rankings"] == []
    assert live["eligibility"]["verified"] is False
    assert live["diagnostics"]["state"] == "eligibility_failed"


def test_run_recompute_does_not_use_markdown_card_rankings_for_live_surface(monkeypatch, tmp_path):
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
    monkeypatch.setattr(runtime, "read_snapshot", lambda: {})

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

    live = snapshot["live_tournament"]
    assert live["ranking_source"] == "eligibility_failed"
    assert live["rankings"] == []
    assert live["source_card_path"] == "output/current_event.md"


def test_extract_board_value_bets_reports_filter_counters():
    from backtester import dashboard_runtime as runtime

    value_bets, diagnostics = runtime._extract_board_value_bets(
        {
            "top10": [
                {
                    "player_display": "Valid Player",
                    "book": "bet365",
                    "odds": "+180",
                    "ev": 0.16,
                    "is_value": True,
                },
                {
                    "player_display": "Missing Odds",
                    "book": "bet365",
                    "ev": 0.14,
                    "is_value": True,
                },
                {
                    "player_display": "Capped Edge",
                    "book": "bet365",
                    "odds": "+220",
                    "ev": 0.50,
                    "ev_capped": True,
                    "is_value": True,
                },
                {
                    "player_display": "Suspicious Divergence",
                    "book": "bet365",
                    "odds": "+400",
                    "ev": 0.20,
                    "suspicious": True,
                    "is_value": True,
                },
            ]
        },
        return_diagnostics=True,
    )

    assert list(value_bets) == ["top10"]
    assert len(value_bets["top10"]) == 1
    assert value_bets["top10"][0]["player_display"] == "Valid Player"
    assert diagnostics["missing_display_odds"] == 1
    assert diagnostics["ev_cap_filtered"] == 1
    assert diagnostics["probability_inconsistency_filtered"] == 1


def test_run_recompute_records_snapshot_history_and_market_rows(monkeypatch):
    from backtester import dashboard_runtime as runtime

    captured = {"history_calls": [], "market_rows": []}

    monkeypatch.setattr(
        runtime,
        "run_snapshot_analysis",
        lambda **kwargs: {
            "status": "complete",
            "event_name": kwargs.get("tournament_name") or "Test Event",
            "course_name": kwargs.get("course_name") or "Test Course",
            "field_size": 40,
            "field_validation": {
                "strict_field_verified": True,
                "field_source": "datagolf_field_updates",
                "expected_event_id": kwargs.get("event_id") or "123",
                "failed_invariants": [],
                "major_event": False,
                "cross_tour_backfill_used": False,
            },
            "composite_results": [
                {
                    "player_key": "a_player",
                    "player_display": "A Player",
                    "composite": 75.0,
                    "course_fit": 70.0,
                    "form": 68.0,
                    "momentum": 64.0,
                }
            ],
            "matchup_bets": [
                {
                    "pick": "A Player",
                    "pick_key": "a_player",
                    "opponent": "B Player",
                    "opponent_key": "b_player",
                    "book": "fanduel",
                    "odds": "+105",
                    "model_win_prob": 0.54,
                    "implied_prob": 0.49,
                    "ev": 0.08,
                }
            ],
            "matchup_bets_all_books": [
                {
                    "pick": "A Player",
                    "pick_key": "a_player",
                    "opponent": "B Player",
                    "opponent_key": "b_player",
                    "book": "fanduel",
                    "odds": "+105",
                    "model_win_prob": 0.54,
                    "implied_prob": 0.49,
                    "ev": 0.08,
                }
            ],
            "value_bets": {
                "top10": [
                    {
                        "player_key": "a_player",
                        "player_display": "A Player",
                        "book": "fanduel",
                        "odds": "+220",
                        "model_prob": 0.21,
                        "market_prob": 0.17,
                        "ev": 0.12,
                        "is_value": True,
                    }
                ]
            },
            "output_file": "output/test_event.md",
            "matchup_diagnostics": {
                "market_counts": {"tournament_matchups": {"raw_rows": 1, "reason_code": "ok"}},
                "selection_counts": {"input_rows": 1, "selected_rows": 1, "all_qualifying_rows": 1},
                "reason_codes": {},
                "state": "edges_available",
                "errors": [],
            },
        },
    )
    monkeypatch.setattr(runtime, "_load_finish_state_map", lambda event_id, year=None: {})
    monkeypatch.setattr(
        runtime,
        "_load_event_leaderboard_rows",
        lambda event_id, year=None, limit=30: [{"rank": 1, "position": "1", "player": "A Player", "total_to_par": -6}],
    )
    monkeypatch.setattr(runtime, "read_snapshot", lambda: {})
    monkeypatch.setattr(
        runtime.db,
        "store_live_snapshot_sections",
        lambda *args, **kwargs: captured["history_calls"].append((args, kwargs)) or 2,
    )
    monkeypatch.setattr(
        runtime.db,
        "store_market_prediction_rows",
        lambda rows: captured["market_rows"].append(rows) or len(rows),
    )
    monkeypatch.setattr(runtime, "_write_snapshot", lambda payload: None)

    snapshot = runtime._run_recompute(
        "pga",
        "live_window",
        {
            "event_name": "Test Event",
            "event_id": "123",
            "event_year": 2026,
            "course": "Test Course",
            "upcoming_event_names": ["Test Event", "Future Event"],
            "upcoming_event_row": {"event_id": "124", "event_name": "Future Event", "course": "Future Course", "year": 2026},
            "live_event_active": True,
            "market_counts": {"tournament_matchups": {"raw_rows": 1, "reason_code": "ok"}},
        },
    )

    assert snapshot.get("snapshot_id")
    assert snapshot["diagnostics"]["history_rows_written"] == 2
    assert snapshot["diagnostics"]["market_rows_written"] >= 2
    assert snapshot["live_tournament"]["leaderboard"][0]["player"] == "A Player"
    assert captured["history_calls"], "Expected immutable snapshot rows to be persisted."
    assert captured["market_rows"], "Expected market prediction rows to be persisted."


def test_live_refresh_past_snapshot_endpoints(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        app_module,
        "list_past_snapshot_events",
        lambda limit=40: [{"event_id": "18", "event_name": "Zurich Classic", "latest_generated_at": "2026-04-17T20:00:00+00:00"}],
    )
    monkeypatch.setattr(
        app_module,
        "get_latest_snapshot_section",
        lambda event_id, section="live": {
            "snapshot_id": "snap_123",
            "generated_at": "2026-04-17T20:00:00+00:00",
            "tour": "pga",
            "section": section,
            "snapshot": {"event_name": "Zurich Classic", "rankings": [], "matchup_bets_all_books": []},
        },
    )

    client = TestClient(app_module.app)
    events_response = client.get("/api/live-refresh/past-events")
    snapshot_response = client.get("/api/live-refresh/past-snapshot?event_id=18&section=live")

    assert events_response.status_code == 200
    events_body = events_response.json()
    assert events_body["events"][0]["event_id"] == "18"

    assert snapshot_response.status_code == 200
    snapshot_body = snapshot_response.json()
    assert snapshot_body["ok"] is True
    assert snapshot_body["snapshot"]["event_name"] == "Zurich Classic"


def test_list_snapshot_timeline_points_summarizes_history_rows_defensively(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute(
        """
        INSERT INTO live_snapshot_history
            (snapshot_id, generated_at, tour, cadence_mode, section, event_id, event_name,
             source_event_id, source_event_name, active, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "snap_new",
            "2026-04-17T20:05:00+00:00",
            "pga",
            "live_window",
            "live",
            "evt_18",
            "Zurich Classic",
            "evt_18",
            "Zurich Classic",
            1,
            json.dumps(
                {
                    "event_name": "Zurich Classic",
                    "source_event_id": "evt_18",
                    "active": True,
                    "diagnostics": {"state": "edges_available"},
                    "leaderboard": [{"player": "Player A"}],
                    "rankings": [{"player": "Player A"}, {"player": "Player B"}],
                    "matchup_bets_all_books": [{"ev": 0.07}, {"ev": 0.11}],
                    "value_bets": {
                        "top10": [{"ev": 0.08}, {"ev": 0.04}],
                        "top20": [{"ev": 0.05}],
                    },
                }
            ),
        ),
    )
    conn.execute(
        """
        INSERT INTO live_snapshot_history
            (snapshot_id, generated_at, tour, cadence_mode, section, event_id, event_name,
             source_event_id, source_event_name, active, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "snap_old",
            "2026-04-17T19:55:00+00:00",
            "pga",
            "live_window",
            "live",
            "evt_18",
            "Zurich Classic",
            "evt_18",
            "Zurich Classic",
            0,
            json.dumps(
                {
                    "event_name": "Zurich Classic",
                    "source_event_id": "evt_18",
                    "active": False,
                    "diagnostics": {},
                    "leaderboard": None,
                    "rankings": None,
                    "value_bets": {"top10": None},
                }
            ),
        ),
    )
    conn.commit()
    conn.close()

    points = tmp_db.list_snapshot_timeline_points("evt_18", section="live", limit=10)

    assert [point["snapshot_id"] for point in points] == ["snap_new", "snap_old"]
    assert points[0]["diagnostics_state"] == "edges_available"
    assert points[0]["leaderboard_count"] == 1
    assert points[0]["rankings_count"] == 2
    assert points[0]["matchup_count"] == 2
    assert points[0]["value_pick_count"] == 3
    assert points[0]["best_edge"] == 0.11
    assert points[1]["diagnostics_state"] is None
    assert points[1]["leaderboard_count"] == 0
    assert points[1]["rankings_count"] == 0
    assert points[1]["matchup_count"] == 0
    assert points[1]["value_pick_count"] == 0
    assert points[1]["best_edge"] is None


def test_live_refresh_past_timeline_endpoint(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        app_module,
        "list_snapshot_timeline_points",
        lambda event_id, section="live", limit=120: [
            {
                "snapshot_id": "snap_123",
                "generated_at": "2026-04-17T20:00:00+00:00",
                "tour": "pga",
                "cadence_mode": "live_window",
                "section": section,
                "event_id": event_id,
                "event_name": "Zurich Classic",
                "active": True,
                "diagnostics_state": "edges_available",
                "leaderboard_count": 4,
                "rankings_count": 20,
                "matchup_count": 6,
                "value_pick_count": 3,
                "best_edge": 0.14,
            }
        ],
    )

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/past-timeline?event_id=18&section=live&limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event_id"] == "18"
    assert body["section"] == "live"
    assert body["point_count"] == 1
    assert body["points"][0]["snapshot_id"] == "snap_123"
    assert body["points"][0]["best_edge"] == 0.14


def test_live_refresh_past_market_rows_endpoint_returns_stable_contract(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        app_module,
        "get_market_prediction_rows_for_event",
        lambda event_id, market_family=None, section=None, limit=2000: [
            {
                "id": 7,
                "snapshot_id": "snap_123",
                "generated_at": "2026-04-17T20:00:00+00:00",
                "tour": "pga",
                "section": "live",
                "event_id": event_id,
                "event_name": "Zurich Classic",
                "market_family": market_family or "matchup",
                "market_type": "tournament_matchups",
                "player_key": "player_a",
                "player_display": "Player A",
                "opponent_key": "player_b",
                "opponent_display": "Player B",
                "book": "fanduel",
                "odds": "+112",
                "model_prob": 0.58,
                "implied_prob": 0.47,
                "ev": 0.09,
                "is_value": 1,
                "payload": {"pick": "Player A", "opponent": "Player B"},
            }
        ],
    )

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/past-market-rows?event_id=18&market_family=matchup&section=live")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event_id"] == "18"
    assert body["market_family"] == "matchup"
    assert body["section"] == "live"
    assert body["row_count"] == 1
    assert body["rows"][0]["snapshot_id"] == "snap_123"
    assert body["rows"][0]["is_value"] == 1
    assert body["rows"][0]["is_value_bool"] is True
    assert body["rows"][0]["payload"]["pick"] == "Player A"


def test_live_refresh_replay_endpoints_reject_invalid_section_consistently(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)

    client = TestClient(app_module.app)
    snapshot_response = client.get("/api/live-refresh/past-snapshot?event_id=18&section=bad")
    timeline_response = client.get("/api/live-refresh/past-timeline?event_id=18&section=bad")
    market_rows_response = client.get("/api/live-refresh/past-market-rows?event_id=18&section=bad")

    for response in (snapshot_response, timeline_response, market_rows_response):
        assert response.status_code == 400
        assert response.json() == {
            "ok": False,
            "error": "section must be one of: live, upcoming",
        }


def test_live_refresh_replay_endpoints_treat_empty_section_as_live(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        app_module,
        "get_latest_snapshot_section",
        lambda event_id, section="live": {
            "snapshot_id": "snap_empty",
            "generated_at": "2026-04-17T20:00:00+00:00",
            "tour": "pga",
            "section": section,
            "snapshot": {"event_name": "Zurich Classic"},
        },
    )
    monkeypatch.setattr(
        app_module,
        "list_snapshot_timeline_points",
        lambda event_id, section="live", limit=120: [
            {
                "snapshot_id": "snap_empty",
                "generated_at": "2026-04-17T20:00:00+00:00",
                "tour": "pga",
                "cadence_mode": "live_window",
                "section": section,
                "event_id": event_id,
                "event_name": "Zurich Classic",
                "active": True,
                "diagnostics_state": "edges_available",
                "leaderboard_count": 1,
                "rankings_count": 1,
                "matchup_count": 1,
                "value_pick_count": 1,
                "best_edge": 0.11,
            }
        ],
    )
    monkeypatch.setattr(
        app_module,
        "get_market_prediction_rows_for_event",
        lambda event_id, market_family=None, section=None, limit=2000: [
            {
                "snapshot_id": "snap_empty",
                "generated_at": "2026-04-17T20:00:00+00:00",
                "tour": "pga",
                "section": section,
                "event_id": event_id,
                "event_name": "Zurich Classic",
                "market_family": market_family or "matchup",
                "is_value": 1,
            }
        ],
    )

    client = TestClient(app_module.app)
    snapshot_response = client.get("/api/live-refresh/past-snapshot?event_id=18&section=")
    timeline_response = client.get("/api/live-refresh/past-timeline?event_id=18&section=")
    market_rows_response = client.get("/api/live-refresh/past-market-rows?event_id=18&section=")

    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["section"] == "live"

    assert timeline_response.status_code == 200
    assert timeline_response.json()["section"] == "live"
    assert timeline_response.json()["points"][0]["section"] == "live"

    assert market_rows_response.status_code == 200
    assert market_rows_response.json()["section"] == "live"
    assert market_rows_response.json()["rows"][0]["section"] == "live"

