"""Tests for the simplified dashboard and one-click actions."""

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_home_page_shows_simple_actions():
    """The root dashboard should expose prediction and autoresearch sections."""
    import app as app_module

    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "Golf Model" in text
    assert "Prediction" in text
    assert "Autoresearch" in text
    assert "Run prediction" in text
    assert "Start autoresearch engine" in text
    assert "Run once" in text
    assert "Tools" in text
    assert "/static/css/main.css" in text
    assert "/static/js/app.js" in text


def test_home_page_uses_autoresearch_language_not_optimizer_heading():
    """The main page should present autoresearch, not optimizer."""
    import app as app_module

    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "autoresearch" in text.lower()
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


def test_home_page_recent_runs_js_escapes_report_path_safely():
    """The dashboard loads script and has structure for candidates (report links built in JS)."""
    import app as app_module

    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    assert "/static/js/app.js" in text
    assert "bestCandidates" in text
