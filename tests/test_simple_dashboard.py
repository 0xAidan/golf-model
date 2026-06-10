"""Tests for the simplified dashboard and one-click actions."""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import optuna
from fastapi.testclient import TestClient
from optuna.trial import TrialState

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_home_page_serves_built_react_shell():
    """The root dashboard serves the built React SPA."""
    import app as app_module

    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert '<div id="root"></div>' in text
    assert "Continuous Optimizer" not in text


def test_upcoming_prediction_endpoint_returns_output_file(monkeypatch):
    """Simple prediction endpoint should run the prediction service and return the markdown path."""
    import app as app_module

    class FakeService:
        def __init__(self, tour="pga", strategy_config=None):
            self.tour = tour
            self.strategy_config = strategy_config or {}

        def run_analysis(self, **kwargs):
            return {
                "status": "complete",
                "event_name": "Arnold Palmer Invitational",
                "field_size": 72,
                "value_bets": {"win": []},
                "output_file": "output/test_prediction.md",
            }

    monkeypatch.setattr("src.services.golf_model_service.GolfModelService", FakeService)

    client = TestClient(app_module.app)
    response = client.post(
        "/api/simple/upcoming-prediction",
        json={"tour": "pga", "tournament": "Arnold Palmer Invitational", "course": "Bay Hill"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["output_file"] == "output/test_prediction.md"


def test_upcoming_prediction_endpoint_normalizes_card_filepath(monkeypatch):
    """Simple prediction endpoint should expose a consistent output_file for the UI."""
    import app as app_module

    class FakeService:
        def __init__(self, tour="pga", strategy_config=None):
            self.tour = tour
            self.strategy_config = strategy_config or {}

        def run_analysis(self, **kwargs):
            return {
                "status": "complete",
                "event_name": "Arnold Palmer Invitational",
                "field_size": 72,
                "card_filepath": "output/test_card.md",
            }

    monkeypatch.setattr("src.services.golf_model_service.GolfModelService", FakeService)

    client = TestClient(app_module.app)
    response = client.post(
        "/api/simple/upcoming-prediction",
        json={"tour": "pga", "tournament": "Arnold Palmer Invitational", "course": "Bay Hill"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["output_file"] == "output/test_card.md"


def test_backtest_endpoint_writes_plain_english_markdown_report(monkeypatch, tmp_path):
    """Simple backtest endpoint should produce a readable candidate-vs-baseline report."""
    import app as app_module
    from backtester.strategy import StrategyConfig

    monkeypatch.setattr(
        "backtester.experiments.get_active_strategy",
        lambda scope="global": StrategyConfig(name="baseline", min_ev=0.05),
    )
    monkeypatch.setattr(
        "backtester.weighted_walkforward.evaluate_weighted_walkforward",
        lambda **kwargs: {
            "summary_metrics": {
                "events_evaluated": 3,
                "total_bets": 10,
                "weighted_roi_pct": 2.5,
                "unweighted_roi_pct": 2.0,
                "weighted_clv_avg": 0.012,
                "weighted_calibration_error": 0.08,
                "max_drawdown_pct": 6.0,
            },
            "baseline_summary_metrics": {
                "weighted_roi_pct": 1.0,
                "unweighted_roi_pct": 1.1,
                "weighted_clv_avg": 0.01,
                "weighted_calibration_error": 0.09,
                "max_drawdown_pct": 7.0,
            },
            "guardrail_results": {
                "passed": True,
                "reasons": [],
                "verdict": "promising",
            },
            "segmented_metrics": {
                "major": {"weighted_roi_pct": 3.2, "events_evaluated": 1}
            },
            "splits": [],
        },
    )
    monkeypatch.setattr(app_module, "SIMPLE_OUTPUT_DIR", str(tmp_path))

    client = TestClient(app_module.app)
    response = client.post(
        "/api/simple/backtest",
        json={"name": "ui_test", "years": [2024, 2025], "min_ev": 0.05, "window": 24},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["report_path"].endswith(".md")
    assert os.path.exists(body["report_path"])
    assert body["verdict"] == "better than baseline"

    with open(body["report_path"], "r", encoding="utf-8") as handle:
        markdown = handle.read()

    assert "What We Tested" in markdown
    assert "Is It Better Than The Baseline?" in markdown
    assert "Recommendation" in markdown
    assert "Synthetic Odds Warning" in markdown
    assert "better than baseline" in markdown.lower()


def test_dashboard_state_endpoint_exposes_actionable_status(monkeypatch):
    """Dashboard state should expose AI mode, model lanes, and latest output paths."""
    import app as app_module
    from backtester.strategy import StrategyConfig

    monkeypatch.setattr(
        app_module,
        "_latest_output_file",
        lambda *args, **kwargs: {
            ("", ".md"): "/tmp/latest_prediction.md",
            ("backtests", ".md"): "/tmp/latest_backtest.md",
            ("research", ".md"): "/tmp/latest_research.md",
        }.get((kwargs.get("subdir", ""), kwargs.get("suffix", ".md"))),
    )
    monkeypatch.setattr(
        "src.ai_brain.get_ai_status",
        lambda: {"provider": "openai", "available": False, "model": "gpt-4o"},
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_live_weekly_model",
        lambda scope="global": StrategyConfig(name="live_model", min_ev=0.05),
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_research_champion",
        lambda scope="global": StrategyConfig(name="research_model", min_ev=0.07),
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_live_weekly_model_record",
        lambda scope="global": {"id": 1, "scope": "global"},
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_research_champion_record",
        lambda scope="global": {"id": 2, "scope": "global"},
    )

    client = TestClient(app_module.app)
    response = client.get("/api/dashboard/state")

    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"]["available"] is False
    assert body["effective_live_weekly_model"]["name"] == "live_model"
    assert body["effective_research_champion"]["name"] == "research_model"
    assert body["latest_outputs"]["prediction_markdown_path"] == "/tmp/latest_prediction.md"
    assert body["latest_outputs"]["backtest_markdown_path"] == "/tmp/latest_backtest.md"
    assert body["latest_outputs"]["research_markdown_path"] == "/tmp/latest_research.md"


def test_output_latest_returns_content(tmp_path, monkeypatch):
    """GET /api/output/latest?type=backtest returns markdown content when file exists under output/."""
    import app as app_module

    output_backtests = tmp_path / "backtests"
    output_backtests.mkdir(parents=True)
    backtest_file = output_backtests / "test_20260101_120000.md"
    backtest_file.write_text("# Backtest: test\n\nVerdict: better than baseline.")

    output_abs = str(tmp_path)
    monkeypatch.setattr(app_module, "_output_dir_absolute", lambda: output_abs)
    monkeypatch.setattr(
        app_module,
        "_latest_output_file",
        lambda *args, subdir="", suffix=".md": str(backtest_file) if subdir == "backtests" else None,
    )

    client = TestClient(app_module.app)
    r = client.get("/api/output/latest?type=backtest")
    assert r.status_code == 200
    data = r.json()
    assert data.get("not_found") is False
    assert "Backtest: test" in (data.get("content") or "")
    assert "path" in data


def test_output_latest_not_found(monkeypatch):
    """GET /api/output/latest returns not_found when no file exists for type."""
    import app as app_module

    monkeypatch.setattr(app_module, "_latest_output_file", lambda *args, **kwargs: None)
    client = TestClient(app_module.app)
    r = client.get("/api/output/latest?type=prediction")
    assert r.status_code == 200
    assert r.json().get("not_found") is True


def test_live_refresh_snapshot_endpoint_exposes_fallback_metadata(monkeypatch):
    import app as app_module

    # Use a recent timestamp so the fail-closed staleness contract treats the
    # snapshot as fresh; this test asserts that a *fresh* snapshot carrying a
    # degraded pipeline state still surfaces a stale_reason while staying ok.
    # (Previously hardcoded to 2026-04-06, which rotted into staleness.)
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.dashboard_runtime.get_live_refresh_status", lambda: {"running": True})
    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: {
            "generated_at": recent,
            "live_tournament": {
                "ranking_source": "current_event_model_fallback",
                "diagnostics": {"state": "pipeline_error"},
            },
            "upcoming_tournament": {"diagnostics": {"state": "edges_available"}},
        },
    )
    monkeypatch.setattr("backtester.dashboard_runtime.generate_snapshot_once", lambda tour="pga": {})

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["snapshot"] is not None
    assert body["stale_reason"] is not None
    assert body["fallback_reason"] is None


def test_live_refresh_snapshot_endpoint_surfaces_field_verification_error(monkeypatch):
    import app as app_module

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.dashboard_runtime.get_live_refresh_status", lambda: {"running": True})
    monkeypatch.setattr(
        "backtester.dashboard_runtime.read_snapshot",
        lambda: {
            "generated_at": "2099-01-01T00:00:00+00:00",
            "live_tournament": {
                "ranking_source": "eligibility_failed",
                "eligibility": {
                    "verified": False,
                    "summary": "Field verification failed: no confirmed tournament field available.",
                    "action": "Wait for Data Golf field updates.",
                },
                "diagnostics": {"state": "eligibility_failed"},
            },
            "upcoming_tournament": {
                "diagnostics": {"state": "edges_available"},
            },
        },
    )
    monkeypatch.setattr("backtester.dashboard_runtime.generate_snapshot_once", lambda tour="pga": {})

    client = TestClient(app_module.app)
    response = client.get("/api/live-refresh/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "Field verification failed" in (body["stale_reason"] or "")
    assert body["fallback_reason"] is None


def test_latest_completed_event_endpoint_prefers_completed_schedule_event(monkeypatch):
    """The dashboard should expose the most recently completed event, not the next upcoming one."""
    import app as app_module

    monkeypatch.setattr(
        "src.datagolf._call_api",
        lambda endpoint, params=None: {
            "schedule": [
                {"event_id": "501", "event_name": "Masters Tournament", "start_date": "2099-04-09", "end_date": "2099-04-12"},
                {"event_id": "500", "event_name": "Valero Texas Open", "start_date": "2026-04-02", "end_date": "2026-04-05"},
                {"event_id": "499", "event_name": "Texas Children's Houston Open", "start_date": "2026-03-26", "end_date": "2026-03-29"},
            ]
        },
    )

    client = TestClient(app_module.app)
    response = client.get("/api/events/latest-completed")

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "500"
    assert body["event_name"] == "Valero Texas Open"
    assert body["year"] == 2026


def test_events_schedule_endpoint_returns_selectable_events_for_tour(monkeypatch):
    """The dashboard should expose schedule events for dropdown-based run controls."""
    import app as app_module

    monkeypatch.setattr(
        "src.datagolf._call_api",
        lambda endpoint, params=None: {
            "schedule": [
                {
                    "event_id": "501",
                    "event_name": "Masters Tournament",
                    "course": "Augusta National",
                    "start_date": "2026-04-09",
                    "end_date": "2026-04-12",
                },
                {
                    "event_id": "500",
                    "event_name": "Valero Texas Open",
                    "course": "TPC San Antonio",
                    "start_date": "2026-04-02",
                    "end_date": "2026-04-05",
                },
            ]
        },
    )

    client = TestClient(app_module.app)
    response = client.get("/api/events/schedule?tour=pga")

    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 2
    assert body["events"][0]["event_id"] == "501"
    assert body["events"][0]["event_name"] == "Masters Tournament"
    assert body["events"][0]["course"] == "Augusta National"


def test_dashboard_state_includes_latest_completed_event_and_relative_prediction_path(monkeypatch, tmp_path):
    """Dashboard state should expose stable event/output metadata for refresh-safe UI state."""
    import app as app_module
    from backtester.strategy import StrategyConfig

    prediction_file = tmp_path / "valero_texas_open_20260405.md"
    prediction_file.write_text("# Valero Texas Open — Betting Card")

    monkeypatch.setattr(app_module, "_output_dir_absolute", lambda: str(tmp_path))
    monkeypatch.setattr(
        app_module,
        "_latest_output_file",
        lambda *args, **kwargs: {
            ("", ".md"): str(prediction_file),
            ("backtests", ".md"): None,
            ("research", ".md"): None,
        }.get((kwargs.get("subdir", ""), kwargs.get("suffix", ".md"))),
    )
    monkeypatch.setattr(
        "src.ai_brain.get_ai_status",
        lambda: {"provider": "openai", "available": True, "model": "gpt-4o"},
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_live_weekly_model",
        lambda scope="global": StrategyConfig(name="live_model", min_ev=0.05),
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_research_champion",
        lambda scope="global": StrategyConfig(name="research_model", min_ev=0.07),
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_live_weekly_model_record",
        lambda scope="global": {"id": 1, "scope": "global"},
    )
    monkeypatch.setattr(
        "backtester.model_registry.get_research_champion_record",
        lambda scope="global": {"id": 2, "scope": "global"},
    )
    monkeypatch.setattr(
        "backtester.optimizer_runtime.get_optimizer_status",
        lambda: {"running": False, "run_count": 0},
    )
    monkeypatch.setattr(
        "src.datagolf.get_datagolf_throttle_status",
        lambda: {"status": "ok"},
    )
    monkeypatch.setattr(
        app_module,
        "_latest_completed_event_summary",
        lambda: {"event_id": "500", "event_name": "Valero Texas Open", "year": 2026},
    )
    monkeypatch.setattr(
        app_module,
        "_latest_graded_tournament_summary",
        lambda: {"name": "Valero Texas Open", "total_profit": 1.5, "graded_pick_count": 4},
    )
    app_module._dashboard_state_cache.clear()

    client = TestClient(app_module.app)
    response = client.get("/api/dashboard/state")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_completed_event"]["event_id"] == "500"
    assert body["latest_prediction_artifact"]["path"] == "output/valero_texas_open_20260405.md"
    assert body["latest_graded_tournament"]["name"] == "Valero Texas Open"


def test_grading_history_endpoint_returns_scored_tournament_summaries(monkeypatch, tmp_path):
    """The dashboard should expose durable grading history from SQLite, not just transient DOM state."""
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "grading_history.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (1, "Valero Texas Open", "TPC San Antonio", 2026, "500"),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display, market_odds, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "v5", "ui_display", "matchup", "ludvig_aberg", "Ludvig Aberg", "-110", 0.52, 0.12),
    )
    conn.execute(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_text, made_cut) VALUES (?, ?, ?, ?, ?)",
        (1, "ludvig_aberg", "Ludvig Aberg", "T5", 1),
    )
    conn.execute(
        """INSERT INTO pick_outcomes
           (pick_id, hit, actual_finish, odds_decimal, stake, profit, entered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "T5", 1.91, 1.0, 0.91, "2026-04-05 18:45:00"),
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/grading/history")

    assert response.status_code == 200
    body = response.json()
    assert len(body["tournaments"]) == 1
    assert body["tournaments"][0]["event_id"] == "500"
    assert body["tournaments"][0]["graded_pick_count"] == 1
    assert body["tournaments"][0]["hits"] == 1
    assert body["tournaments"][0]["total_profit"] == 0.91
    assert body["tournaments"][0]["variant_stats"]["v5"]["picks"] == 1
    assert body["tournaments"][0]["variant_stats"]["v5"]["hits"] == 1
    assert body["tournaments"][0]["picks"][0]["model_variant"] == "v5"
    assert body["tournaments"][0]["picks"][0]["outcome"] == "win"
    assert body["tournaments"][0]["picks"][0]["model_prob"] == 0.52
    assert body["tournaments"][0]["picks"][0]["ev"] == 0.12


def test_grading_history_summary_splits_1u_record_by_market_without_result_fanout(monkeypatch, tmp_path):
    """Past KPI math should use one graded pick once, split into matchup and non-matchup buckets."""
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "grading_history_market_summary.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (1, "RBC Heritage", "Harbour Town", 2026, "512"),
    )
    # Multiple results rows used to multiply SUM(po.profit) in the old history query.
    conn.executemany(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_text, made_cut) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "player_a", "Player A", "1", 1),
            (1, "player_b", "Player B", "T5", 1),
            (1, "player_c", "Player C", "CUT", 0),
        ],
    )
    picks = [
        (1, "cockpit", "matchup", "matchup_win", "Matchup Win", "opp_1", "Opponent 1", "-125", "Book A", 1.80, 1, 0.80),
        (2, "cockpit", "matchup", "matchup_loss", "Matchup Loss", "opp_2", "Opponent 2", "+120", "Book A", 2.20, 0, -1.00),
        (3, "cockpit", "matchup", "matchup_push", "Matchup Push", "opp_3", "Opponent 3", "-110", "Book A", 1.91, 0, 0.00),
        (4, "cockpit", "outright", "outright_win", "Outright Win", None, None, "+400", "Book A", 5.00, 1, 4.00),
        (5, "cockpit", "top5", "placement_loss", "Placement Loss", None, None, "+200", "Book A", 3.00, 0, -1.00),
        (6, "cockpit", "top10", "placement_push", "Placement Push", None, None, "+150", "Book A", 2.50, 0, 0.00),
        # Same generated matchup as pick 1, but a better line. Record math must keep this one only.
        (7, "cockpit", "matchup", "matchup_win", "Matchup Win", "opp_1", "Opponent 1", "-105", "Book B", 1.95, 1, 0.95),
        # Lab rows must not leak into dashboard/cockpit summaries.
        (8, "lab_sandbox", "matchup", "lab_win", "Lab Win", "lab_opp", "Lab Opp", "+100", "Book A", 2.00, 1, 1.00),
    ]
    for pick_id, source, bet_type, player_key, player_display, opponent_key, opponent_display, odds, book, odds_decimal, hit, profit in picks:
        conn.execute(
            """INSERT INTO picks
               (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
                opponent_key, opponent_display, market_odds, market_book, model_prob, ev)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pick_id,
                1,
                "v5",
                source,
                bet_type,
                player_key,
                player_display,
                opponent_key,
                opponent_display,
                odds,
                book,
                0.52,
                0.12,
            ),
        )
        conn.execute(
            """INSERT INTO pick_outcomes
               (pick_id, hit, model_hit, actual_finish, odds_decimal, stake, profit, entered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pick_id, hit, hit, "graded", odds_decimal, 1.0, profit, "2026-04-20 18:45:00"),
        )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/grading/history?pick_source=cockpit")

    assert response.status_code == 200
    body = response.json()
    event = body["tournaments"][0]
    assert event["graded_pick_count"] == 6
    assert event["total_profit"] == 2.95
    assert [pick["market_book"] for pick in event["picks"] if pick["player_display"] == "Matchup Win"] == ["Book B"]
    assert event["market_stats"]["matchups"] == {
        "picks": 3,
        "wins": 1,
        "losses": 1,
        "pushes": 1,
        "profit": -0.05,
        "hit_rate": 0.333,
    }
    assert event["market_stats"]["outrights"] == {
        "picks": 3,
        "wins": 1,
        "losses": 1,
        "pushes": 1,
        "profit": 3.0,
        "hit_rate": 0.333,
    }
    assert body["summary"]["combined"] == {
        "picks": 6,
        "wins": 2,
        "losses": 2,
        "pushes": 2,
        "profit": 2.95,
        "hit_rate": 0.333,
    }

    lab_response = client.get("/api/grading/history?pick_source=lab")
    assert lab_response.status_code == 200
    assert lab_response.json()["summary"]["combined"] == {
        "picks": 1,
        "wins": 1,
        "losses": 0,
        "pushes": 0,
        "profit": 1.0,
        "hit_rate": 1.0,
    }


def test_grading_history_coalesces_event_id_from_rounds_when_tournament_null(monkeypatch, tmp_path):
    """Past-tab fallback uses event_id; legacy rows with NULL t.event_id still resolve from rounds."""
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "grading_history_event_id_fallback.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (1, "Valero Texas Open", "TPC San Antonio", 2026, None),
    )
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name,
            event_completed, course_name, course_num, course_par, round_num, score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            100,
            "Test Player",
            "test_player",
            "pga",
            2026,
            2026,
            "401155999",
            "Valero Texas Open",
            "2026-04-06",
            "TPC San Antonio",
            1,
            72,
            4,
            68,
        ),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display, market_odds, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "v5", "cockpit", "matchup", "test_player", "Test Player", "-110", 0.52, 0.12),
    )
    conn.execute(
        "INSERT INTO results (tournament_id, player_key, player_display, finish_text, made_cut) VALUES (?, ?, ?, ?, ?)",
        (1, "test_player", "Test Player", "T5", 1),
    )
    conn.execute(
        """INSERT INTO pick_outcomes
           (pick_id, hit, actual_finish, odds_decimal, stake, profit, entered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "T5", 1.91, 1.0, 0.91, "2026-04-06 18:45:00"),
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/grading/history?pick_source=cockpit")
    assert response.status_code == 200
    body = response.json()
    assert len(body["tournaments"]) == 1
    assert body["tournaments"][0]["event_id"] == "401155999"


def test_track_record_endpoint_returns_pick_details_with_edge_and_lane(monkeypatch, tmp_path):
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "track_record.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (2, "RBC Heritage", "Harbour Town", 2026, "512"),
    )
    conn.executemany(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
            opponent_key, opponent_display, market_odds, market_book, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (2, 2, "baseline", "ui_display", "matchup", "tom_hoge", "Tom Hoge", "sungjae_im", "Sungjae Im", "-125", "Book A", 0.51, 0.117),
            (3, 2, "baseline", "ui_display", "matchup", "tom_hoge", "Tom Hoge", "sungjae_im", "Sungjae Im", "-105", "Book B", 0.51, 0.117),
        ],
    )
    conn.executemany(
        """INSERT INTO pick_outcomes
           (pick_id, hit, actual_finish, odds_decimal, stake, profit, entered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (2, 0, "T36 vs T18", 1.80, 1.0, -1.0, "2026-04-20 18:45:00"),
            (3, 0, "T36 vs T18", 1.95, 1.0, -1.0, "2026-04-20 18:46:00"),
        ],
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/track-record")
    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["graded_pick_count"] == 1
    pick = body["events"][0]["picks"][0]
    assert pick["model_variant"] == "baseline"
    assert pick["market_book"] == "Book B"
    assert pick["model_prob"] == 0.51
    assert pick["ev"] == 0.117
    assert pick["outcome"] == "loss"
    assert pick["actual_finish"] == "T36 vs T18"


def test_player_profile_endpoint_returns_recent_rounds_course_history_and_linked_bets(monkeypatch, tmp_path):
    """Player intelligence should expose a deep profile payload for frontend drill-downs."""
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "player_profile.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (7, "Masters Tournament", "Augusta National", 2026, "501"),
    )
    conn.execute(
        """INSERT INTO metrics
           (tournament_id, player_key, player_display, metric_category, metric_name, metric_value)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (7, "jon_rahm", "Jon Rahm", "dg_skill", "sg_total", 1.82),
    )
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed,
            course_name, course_num, course_par, round_num, score, sg_total, fin_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (123, "Jon Rahm", "jon_rahm", "alt", 2026, 2026, "480", "LIV Miami", "2026-04-01", "Augusta National", 10, 72, 4, 69, 2.4, "T3"),
    )
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed,
            course_name, course_num, course_par, round_num, score, sg_total, fin_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (123, "Jon Rahm", "jon_rahm", "alt", 2026, 2026, "479", "LIV Singapore", "2026-03-22", "Sentosa", 44, 72, 4, 71, 1.1, "T8"),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, bet_type, player_key, player_display, opponent_key, opponent_display, market_odds, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (11, 7, "matchup", "jon_rahm", "Jon Rahm", "scottie_scheffler", "Scottie Scheffler", "-110", 0.08),
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/players/jon_rahm/profile?tournament_id=7&course_num=10")

    assert response.status_code == 200
    body = response.json()
    assert body["player_key"] == "jon_rahm"
    assert body["player_display"] == "Jon Rahm"
    assert len(body["recent_rounds"]) == 2
    assert len(body["course_history"]) == 1
    assert len(body["linked_bets"]) == 1
    assert body["current_metrics"]["dg_skill"]["sg_total"] == 1.82
    assert body["sections_version"] == 1
    assert body["header"]["field_size"] == 1
    assert body["header"]["dg_rank"] is None
    assert body["skill_breakdown"]["primary"]
    assert body["rolling_form"]["windows"]["10"] is not None
    assert body["rolling_form"]["window_source_map"]["25"] == "24"
    assert body["course_event_context"]["course_summary"]["rounds_tracked"] == 1
    assert body["betting_context"]["summary"]["linked_bet_count"] == 1


def test_standalone_player_profile_exposes_rich_event_round_payload(monkeypatch, tmp_path):
    """Standalone player profile should return event-level SG splits and round samples."""
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "standalone_profile.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed,
            course_name, course_num, course_par, round_num, score, sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, fin_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (456, "Collin Morikawa", "collin_morikawa", "pga", 2026, 2026, "501", "Masters Tournament", "2026-04-12",
         "Augusta National", 10, 72, 4, 69, 1.7, 0.3, 0.8, 0.2, 0.4, 1.3, "T3"),
    )
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed,
            course_name, course_num, course_par, round_num, score, sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, fin_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (456, "Collin Morikawa", "collin_morikawa", "pga", 2026, 2026, "501", "Masters Tournament", "2026-04-12",
         "Augusta National", 10, 72, 3, 70, 1.1, 0.1, 0.6, 0.1, 0.3, 0.8, "T3"),
    )
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed,
            course_name, course_num, course_par, round_num, score, sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, fin_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (456, "Collin Morikawa", "collin_morikawa", "pga", 2026, 2026, "500", "Valero Texas Open", "2026-04-05",
         "TPC San Antonio", 20, 72, 4, 72, 0.2, -0.1, 0.2, 0.0, 0.1, 0.1, "T18"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "src.datagolf.fetch_skill_ratings",
        lambda: [{"player_name": "Collin Morikawa", "sg_total": 1.2, "sg_ott": 0.2, "sg_app": 0.7, "sg_arg": 0.1, "sg_putt": 0.2}],
    )
    monkeypatch.setattr(
        "src.datagolf.fetch_dg_rankings",
        lambda: [{"player_name": "Collin Morikawa", "datagolf_rank": 4, "owgr_rank": 6, "dg_skill_estimate": 1.25, "primary_tour": "PGA Tour"}],
    )
    monkeypatch.setattr("src.datagolf.fetch_approach_skill", lambda period="l24": [])

    client = TestClient(app_module.app)
    response = client.get("/api/players/collin_morikawa/standalone-profile")

    assert response.status_code == 200
    body = response.json()
    assert body["player_key"] == "collin_morikawa"
    assert len(body["recent_events"]) == 2
    masters = body["recent_events"][0]
    assert masters["event_name"] == "Masters Tournament"
    assert masters["avg_sg_total"] == 1.4
    assert masters["avg_sg_app"] == 0.7
    assert masters["avg_sg_t2g"] == 1.05
    assert masters["avg_to_par"] == -2.5
    assert masters["rounds_played"] == 2
    assert body["rolling_windows_expanded"]["sg_app"]["10"] == 0.533
    assert len(body["recent_rounds_sample"]) == 3
    assert body["recent_rounds_sample"][0]["event_name"] == "Masters Tournament"
    assert body["course_summaries"][0]["course_name"] == "Augusta National"
    assert body["ranking_card"]["dg_rank"] == 4
    assert body["header"]["events_tracked"] == 2


def test_output_list_and_content_endpoints_are_safe(tmp_path, monkeypatch):
    """The dashboard should list output files and safely read them by output-relative path."""
    import app as app_module

    output_dir = tmp_path / "output"
    research_dir = output_dir / "research"
    research_dir.mkdir(parents=True)
    artifact = research_dir / "candidate.md"
    artifact.write_text("# Candidate\n\nLooks promising.")

    monkeypatch.setattr(app_module, "_output_dir_absolute", lambda: str(output_dir))

    client = TestClient(app_module.app)
    listed = client.get("/api/output/list?type=research")
    assert listed.status_code == 200
    path = listed.json()["files"][0]["path"]
    assert path == "output/research/candidate.md"

    content = client.get("/api/output/content?path=" + path)
    assert content.status_code == 200
    assert "Looks promising." in content.json()["content"]


def test_latest_output_summaries_endpoint_returns_compact_cards(tmp_path, monkeypatch):
    """The dashboard should expose plain-English summaries for the latest artifacts."""
    import app as app_module

    output_dir = tmp_path / "output"
    backtests_dir = output_dir / "backtests"
    research_dir = output_dir / "research"
    backtests_dir.mkdir(parents=True)
    research_dir.mkdir(parents=True)

    (output_dir / "prediction.md").write_text(
        "# Arnold Palmer Invitational — Betting Card\n"
        "**AI Analysis:** Enabled (88% confidence)\n\n"
        "## 3 Best Bets\n\n"
        "| Pick | Market | Odds | EV% | Tier | Stake |\n"
        "|------|--------|------|-----|------|--------|\n"
        "| **Matt Fitzpatrick** | top10 | +1000 | 199.0% | — | 1.00u |\n"
    )
    (backtests_dir / "weekly.md").write_text(
        "# Backtest Evaluation: debug\n\n"
        "## What We Tested\n"
        "We tested `debug` against the current baseline `opt_0217_1` on years [2024].\n\n"
        "## Is It Better Than The Baseline?\n"
        "**Verdict: worse than baseline.**\n\n"
        "- Candidate weighted ROI: -8.01%\n"
        "- Baseline weighted ROI: -7.81%\n"
        "- CLV delta: -0.00\n\n"
        "## Guardrails\n"
        "- Passed: True\n\n"
        "## Recommendation\n"
        "Keep the current baseline. This test did not beat it.\n"
    )
    (research_dir / "weekly.md").write_text(
        "# Autoresearch Run: candidate_a\n\n"
        "- Decision: kept\n"
        "- Why: Beat the baseline on the fixed benchmark and passed guardrails.\n\n"
        "## Hypothesis\n"
        "Raise EV threshold to reduce noise.\n"
    )

    monkeypatch.setattr(app_module, "_output_dir_absolute", lambda: str(output_dir))

    client = TestClient(app_module.app)
    response = client.get("/api/output/latest-summaries")

    assert response.status_code == 200
    body = response.json()
    assert body["prediction"]["summary"]["event"] == "Arnold Palmer Invitational"
    assert body["backtest"]["summary"]["candidate_tested"] == "debug"
    assert body["research"]["summary"]["candidate_title"] == "candidate_a"


def test_home_page_renders_react_shell_root():
    """The home page should render the React SPA shell."""
    import app as app_module

    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert '<div id="root"></div>' in text


def test_home_page_prefers_built_react_dashboard_when_frontend_dist_exists(tmp_path, monkeypatch):
    """The app should serve the built React dashboard when a frontend dist is available."""
    import app as app_module

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        "<!doctype html><html><body><div id='root'></div><script type='module' src='/assets/index.js'></script></body></html>",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_module, "FRONTEND_DIST_DIR", dist_dir)
    monkeypatch.setattr(app_module, "FRONTEND_DIST_INDEX", dist_dir / "index.html")

    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "<div id='root'></div>" in response.text
    assert "/assets/index.js" in response.text


def test_simple_autoresearch_control_flow_uses_scalar_defaults(monkeypatch):
    import app as app_module

    current_state = {
        "running": False,
        "run_count": 0,
        "last_run_started_at": None,
        "last_run_finished_at": None,
        "last_error": None,
        "engine_mode": "optuna_scalar",
        "scalar_objective": "weighted_roi_pct",
        "optuna_scalar_study_name": "golf_scalar_simple",
        "optuna_trials_per_cycle": 3,
        "last_result": {},
    }

    def _fake_start(**kwargs):
        assert kwargs["scope"] == "global"
        assert kwargs["interval_seconds"] == 300
        assert kwargs["engine_mode"] == "optuna_scalar"
        assert kwargs["scalar_objective"] == "weighted_roi_pct"
        assert kwargs["optuna_scalar_study_name"] == "golf_scalar_simple"
        assert kwargs["optuna_trials_per_cycle"] == 3
        current_state.update(
            {
                "running": True,
                "last_run_started_at": "2026-03-14T00:00:00Z",
                "engine_mode": kwargs["engine_mode"],
                "scalar_objective": kwargs["scalar_objective"],
                "optuna_scalar_study_name": kwargs["optuna_scalar_study_name"],
                "optuna_trials_per_cycle": kwargs["optuna_trials_per_cycle"],
            }
        )
        return dict(current_state)

    def _fake_stop():
        current_state["running"] = False
        current_state["last_run_finished_at"] = "2026-03-14T00:05:00Z"
        return dict(current_state)

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr("backtester.optimizer_runtime.start_continuous_optimizer", _fake_start)
    monkeypatch.setattr("backtester.optimizer_runtime.stop_continuous_optimizer", _fake_stop)
    monkeypatch.setattr("backtester.optimizer_runtime.get_optimizer_status", lambda: dict(current_state))

    client = TestClient(app_module.app)
    start_response = client.post("/api/simple/autoresearch/start")
    status_response = client.get("/api/simple/autoresearch/status")
    stop_response = client.post("/api/simple/autoresearch/stop")

    assert start_response.status_code == 200
    assert start_response.json()["mode"] == "simple_scalar"
    assert start_response.json()["is_running"] is True
    assert status_response.status_code == 200
    assert status_response.json()["objective"] == "weighted_roi_pct"
    assert status_response.json()["report_only"] is True
    assert stop_response.status_code == 200
    assert stop_response.json()["is_running"] is False


def test_simple_autoresearch_status_cycle_in_progress(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        "backtester.optimizer_runtime.get_optimizer_status",
        lambda: {
            "running": True,
            "last_run_started_at": "2026-03-23T20:00:00+00:00",
            "last_run_finished_at": "2026-03-23T19:30:00+00:00",
            "last_error": None,
            "scalar_objective": "weighted_roi_pct",
            "last_result": {},
        },
    )
    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)

    client = TestClient(app_module.app)
    response = client.get("/api/simple/autoresearch/status")

    assert response.status_code == 200
    body = response.json()
    assert body["cycle_in_progress"] is True
    assert "walk-forward" in body["headline"].lower()


def test_simple_autoresearch_run_once_returns_plain_best_improvement(monkeypatch):
    import app as app_module
    from backtester.strategy import StrategyConfig

    captured = {}
    study = optuna.create_study(direction="maximize")
    study.add_trial(
        optuna.trial.create_trial(
            params={},
            distributions={},
            value=8.8,
            user_attrs={
                "feasible": False,
                "guardrail_passed": False,
                "weighted_roi_pct": 8.8,
                "weighted_clv_avg": 0.03,
                "blended_score": 8.8,
            },
            state=TrialState.COMPLETE,
        )
    )
    study.add_trial(
        optuna.trial.create_trial(
            params={},
            distributions={},
            value=4.4,
            user_attrs={
                "feasible": True,
                "guardrail_passed": True,
                "weighted_roi_pct": 4.4,
                "weighted_clv_avg": 0.05,
                "blended_score": 4.4,
            },
            state=TrialState.COMPLETE,
        )
    )

    def _fake_run_scalar_study(**kwargs):
        captured.update(kwargs)
        return study

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "backtester.model_registry.get_research_champion",
        lambda scope="global": StrategyConfig(name="research_baseline", min_ev=0.06),
    )
    monkeypatch.setattr("backtester.model_registry.get_live_weekly_model", lambda scope="global": None)
    monkeypatch.setattr("backtester.experiments.get_active_strategy", lambda scope="global": None)
    monkeypatch.setattr("backtester.research_lab.mo_study.run_scalar_study", _fake_run_scalar_study)

    client = TestClient(app_module.app)
    response = client.post("/api/simple/autoresearch/run-once")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["mode"] == "simple_scalar"
    assert body["report_only"] is True
    assert body["objective"] == "weighted_roi_pct"
    assert body["best_improvement"]["metric_value"] == 4.4
    assert body["best_improvement"]["guardrails_passed"] is True
    assert body["recent_attempts"][0]["trial_number"] == 1
    assert len(body["recent_attempts"]) == 2
    assert captured["study_name"] == "golf_scalar_simple"
    assert captured["scalar_metric"] == "weighted_roi_pct"


def test_simple_autoresearch_status_surfaces_recent_scalar_attempts(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        "backtester.optimizer_runtime.get_optimizer_status",
        lambda: {
            "running": False,
            "scope": "global",
            "last_run_finished_at": "2026-03-14T00:05:00Z",
            "engine_mode": "optuna_scalar",
            "scalar_objective": "weighted_roi_pct",
            "optuna_scalar_study_name": "golf_scalar_simple",
            "last_result": {
                "evaluation_mode": "optuna_scalar",
                "optuna_scalar_summary": {
                    "best_promotable_trial": {
                        "number": 4,
                        "value": 4.4,
                        "user_attrs": {
                            "feasible": True,
                            "guardrail_passed": True,
                            "weighted_roi_pct": 4.4,
                            "weighted_clv_avg": 0.05,
                            "blended_score": 4.4,
                        },
                    },
                    "recent_trials": [
                        {
                            "number": 4,
                            "value": 4.4,
                            "user_attrs": {
                                "feasible": True,
                                "guardrail_passed": True,
                                "weighted_roi_pct": 4.4,
                                "weighted_clv_avg": 0.05,
                                "blended_score": 4.4,
                            },
                        },
                        {
                            "number": 3,
                            "value": 6.6,
                            "user_attrs": {
                                "feasible": False,
                                "guardrail_passed": False,
                                "weighted_roi_pct": 6.6,
                                "weighted_clv_avg": 0.03,
                                "blended_score": 6.6,
                            },
                        },
                    ],
                },
            },
        },
    )

    client = TestClient(app_module.app)
    response = client.get("/api/simple/autoresearch/status")

    assert response.status_code == 200
    body = response.json()
    assert body["best_improvement"]["trial_number"] == 4
    assert [attempt["trial_number"] for attempt in body["recent_attempts"]] == [4, 3]
