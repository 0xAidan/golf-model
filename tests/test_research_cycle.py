"""Tests for the bounded manual research cycle."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.db as db

_original_path = db.DB_PATH


def setup_module():
    """Create a fresh temp DB for each test module run."""
    tmp = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp
    db._DB_INITIALIZED = False
    db.ensure_initialized()


def teardown_module():
    """Restore original DB path."""
    if os.path.exists(db.DB_PATH):
        os.unlink(db.DB_PATH)
    db.DB_PATH = _original_path
    db._DB_INITIALIZED = False


def test_run_research_cycle_creates_bounded_evaluated_proposals(monkeypatch, tmp_path):
    """Manual cycle should cap candidates and persist evaluated proposals."""
    from backtester.research_cycle import run_research_cycle
    from backtester.strategy import StrategyConfig

    monkeypatch.setenv("AUTORESEARCH_AUTO_APPLY", "1")
    seen = {}

    monkeypatch.setattr(
        "backtester.research_cycle.get_active_strategy",
        lambda scope="global": StrategyConfig(name="baseline"),
    )
    monkeypatch.setattr(
        "backtester.research_cycle.generate_candidate_theories",
        lambda base, max_candidates=5, **kwargs: [
            {
                "title": "c1 title",
                "hypothesis": "c1 theory",
                "why_it_may_work": "c1 reason",
                "source_type": "openai",
                "novelty_score": 0.8,
                "duplicate_marker": "",
                "ranking_hint": 0.7,
                "strategy": StrategyConfig(name="c1", min_ev=0.06),
            },
            {
                "title": "c2 title",
                "hypothesis": "c2 theory",
                "why_it_may_work": "c2 reason",
                "source_type": "openai",
                "novelty_score": 0.7,
                "duplicate_marker": "",
                "ranking_hint": 0.6,
                "strategy": StrategyConfig(name="c2", min_ev=0.07),
            },
            {
                "title": "c3 title",
                "hypothesis": "c3 theory",
                "why_it_may_work": "c3 reason",
                "source_type": "openai",
                "novelty_score": 0.6,
                "duplicate_marker": "",
                "ranking_hint": 0.5,
                "strategy": StrategyConfig(name="c3", min_ev=0.08),
            },
        ],
    )
    def fake_evaluate(**kwargs):
        seen["years"] = kwargs.get("years")
        return {
            "summary_metrics": {
                "events_evaluated": 4,
                "total_bets": 120,
                "weighted_roi_pct": 3.5,
                "unweighted_roi_pct": 2.8,
                "weighted_clv_avg": 0.015,
                "weighted_calibration_error": 0.05,
                "max_drawdown_pct": 7.0,
            },
            "baseline_summary_metrics": {
                "weighted_roi_pct": 2.0,
                "unweighted_roi_pct": 1.9,
                "weighted_clv_avg": 0.01,
                "weighted_calibration_error": 0.06,
                "max_drawdown_pct": 7.5,
            },
            "segmented_metrics": {"major": {"events_evaluated": 1}},
            "guardrail_results": {"passed": True, "reasons": [], "verdict": "promising"},
            "splits": [],
        }

    monkeypatch.setattr("backtester.research_cycle.evaluate_weighted_walkforward", fake_evaluate)
    monkeypatch.setattr(
        "backtester.research_cycle.write_research_dossier",
        lambda **kwargs: {
            "markdown_path": str(tmp_path / f"{kwargs['proposal']['id']}.md"),
            "manifest_path": str(tmp_path / f"{kwargs['proposal']['id']}.json"),
        },
    )

    result = run_research_cycle(max_candidates=2, years=[2024, 2025], output_dir=str(tmp_path))

    assert result["proposals_created"] == 2
    assert result["proposals_evaluated"] == 2
    assert len(result["top_candidates"]) == 2
    assert result["winner"]["proposal_id"] == result["top_candidates"][0]["proposal_id"]
    assert result["research_champion_updated"] is True
    assert all(proposal["status"] == "evaluated" for proposal in result["proposals"])
    assert seen["years"] == [2024, 2025]
    assert "c1 theory" in result["proposals"][0]["hypothesis"]
    assert "openai" in result["proposals"][0]["theory_metadata_json"]


def test_run_research_cycle_does_not_touch_active_strategy(monkeypatch, tmp_path):
    """Manual proposal runs must not auto-promote anything into active strategy."""
    from backtester.research_cycle import run_research_cycle
    from backtester.strategy import StrategyConfig

    monkeypatch.setattr(
        "backtester.research_cycle.get_active_strategy",
        lambda scope="global": StrategyConfig(name="baseline"),
    )
    monkeypatch.setattr(
        "backtester.research_cycle.generate_candidate_theories",
        lambda base, max_candidates=5, **kwargs: [
            {
                "title": "solo title",
                "hypothesis": "solo theory",
                "why_it_may_work": "solo reason",
                "source_type": "fallback_neighbor",
                "novelty_score": 0.4,
                "duplicate_marker": "",
                "ranking_hint": 0.3,
                "strategy": StrategyConfig(name="solo", min_ev=0.06),
            }
        ],
    )
    monkeypatch.setattr(
        "backtester.research_cycle.evaluate_weighted_walkforward",
        lambda **kwargs: {
            "summary_metrics": {
                "events_evaluated": 2,
                "total_bets": 80,
                "weighted_roi_pct": 1.5,
                "unweighted_roi_pct": 1.2,
                "weighted_clv_avg": 0.01,
                "weighted_calibration_error": 0.06,
                "max_drawdown_pct": 6.0,
            },
            "baseline_summary_metrics": {
                "weighted_roi_pct": 1.0,
                "unweighted_roi_pct": 1.0,
                "weighted_clv_avg": 0.009,
                "weighted_calibration_error": 0.06,
                "max_drawdown_pct": 6.0,
            },
            "segmented_metrics": {"regular": {"events_evaluated": 2}},
            "guardrail_results": {"passed": True, "reasons": [], "verdict": "promising"},
            "splits": [],
        },
    )
    monkeypatch.setattr(
        "backtester.research_cycle.write_research_dossier",
        lambda **kwargs: {
            "markdown_path": str(tmp_path / "solo.md"),
            "manifest_path": str(tmp_path / "solo.json"),
        },
    )

    run_research_cycle(max_candidates=1, years=[2025], output_dir=str(tmp_path))

    conn = db.get_conn()
    active_count = conn.execute("SELECT COUNT(*) AS cnt FROM active_strategy").fetchone()["cnt"]
    live_count = conn.execute("SELECT COUNT(*) AS cnt FROM live_model_registry").fetchone()["cnt"]
    conn.close()

    assert active_count == 0
    assert live_count == 0


def test_run_research_cycle_does_not_promote_bad_research_winner(monkeypatch, tmp_path):
    """A weak winner should not auto-replace the current research champion."""
    from backtester.research_cycle import run_research_cycle
    from backtester.strategy import StrategyConfig

    promoted = {"called": False}

    monkeypatch.setattr(
        "backtester.research_cycle.get_active_strategy",
        lambda scope="global": StrategyConfig(name="baseline"),
    )
    monkeypatch.setattr(
        "backtester.research_cycle.generate_candidate_theories",
        lambda base, max_candidates=5, **kwargs: [
            {
                "title": "bad title",
                "hypothesis": "bad theory",
                "why_it_may_work": "weak reason",
                "source_type": "fallback_neighbor",
                "novelty_score": 0.1,
                "duplicate_marker": "",
                "ranking_hint": 0.1,
                "strategy": StrategyConfig(name="bad_candidate", min_ev=0.06),
            }
        ],
    )
    monkeypatch.setattr(
        "backtester.research_cycle.evaluate_weighted_walkforward",
        lambda **kwargs: {
            "summary_metrics": {
                "events_evaluated": 10,
                "total_bets": 400,
                "weighted_roi_pct": -4.0,
                "unweighted_roi_pct": -2.0,
                "weighted_clv_avg": 0.01,
                "weighted_calibration_error": 0.08,
                "max_drawdown_pct": 40.0,
            },
            "baseline_summary_metrics": {
                "weighted_roi_pct": -3.0,
                "unweighted_roi_pct": -1.0,
                "weighted_clv_avg": 0.01,
                "weighted_calibration_error": 0.08,
                "max_drawdown_pct": 35.0,
            },
            "segmented_metrics": {"regular": {"events_evaluated": 10}},
            "guardrail_results": {"passed": True, "reasons": [], "verdict": "promising"},
            "splits": [],
        },
    )
    monkeypatch.setattr(
        "backtester.research_cycle.write_research_dossier",
        lambda **kwargs: {
            "markdown_path": str(tmp_path / "bad.md"),
            "manifest_path": str(tmp_path / "bad.json"),
        },
    )
    monkeypatch.setattr(
        "backtester.research_cycle.set_research_champion",
        lambda *args, **kwargs: promoted.__setitem__("called", True),
    )
    monkeypatch.setattr(
        "backtester.research_cycle._get_global_best_proposal_for_iteration",
        lambda *args, **kwargs: None,
    )

    result = run_research_cycle(max_candidates=1, years=[2025], output_dir=str(tmp_path))

    assert result["research_champion_updated"] is False
    assert result["promotion_decision"] == "kept_current_research_champion"
    assert promoted["called"] is False
