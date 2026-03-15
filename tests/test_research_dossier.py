"""Tests for research dossier artifact generation."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_write_dossier_outputs_markdown_and_manifest(tmp_path):
    """Dossier generation should create both a markdown report and a JSON manifest."""
    from backtester.research_dossier import write_research_dossier

    proposal = {
        "id": 7,
        "name": "proposal_api_focus",
        "hypothesis": "Lean more on form in strong fields",
        "strategy_config_json": json.dumps({"w_sub_form": 0.5, "min_ev": 0.06}, sort_keys=True),
        "created_at": "2026-03-08T12:00:00",
    }
    evaluation = {
        "summary_metrics": {
            "events_evaluated": 8,
            "total_bets": 164,
            "weighted_roi_pct": 4.25,
            "unweighted_roi_pct": 3.1,
            "weighted_clv_avg": 0.018,
            "weighted_calibration_error": 0.044,
            "max_drawdown_pct": 8.0,
        },
        "baseline_summary_metrics": {
            "weighted_roi_pct": 2.0,
            "unweighted_roi_pct": 1.8,
            "weighted_clv_avg": 0.012,
            "weighted_calibration_error": 0.051,
            "max_drawdown_pct": 7.5,
        },
        "segmented_metrics": {
            "major": {"weighted_roi_pct": 5.0, "events_evaluated": 2},
            "regular": {"weighted_roi_pct": 2.6, "events_evaluated": 6},
        },
        "guardrail_results": {
            "passed": True,
            "reasons": [],
            "verdict": "promising",
        },
        "splits": [
            {"train_events": [{"event_id": "api_2024"}], "test_events": [{"event_id": "masters_2024"}]}
        ],
    }
    repro_metadata = {
        "seed": 42,
        "program_version": "v1",
        "code_commit": "abc123",
    }

    artifact_paths = write_research_dossier(
        proposal=proposal,
        evaluation=evaluation,
        repro_metadata=repro_metadata,
        output_dir=str(tmp_path),
    )

    assert os.path.exists(artifact_paths["markdown_path"])
    assert os.path.exists(artifact_paths["manifest_path"])

    with open(artifact_paths["markdown_path"], "r", encoding="utf-8") as handle:
        markdown = handle.read()
    with open(artifact_paths["manifest_path"], "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    assert "Synthetic Odds Warning" in markdown
    assert "Weighted ROI" in markdown
    assert "Unweighted ROI" in markdown
    assert "proposal_api_focus" in markdown
    assert manifest["proposal_id"] == 7
    assert manifest["seed"] == 42
    assert manifest["code_commit"] == "abc123"
    assert manifest["artifact_markdown_path"] == artifact_paths["markdown_path"]
