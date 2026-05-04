"""Tests for v5 vs legacy AB comparison reports."""

import json
from pathlib import Path

from src.research.ab_compare import build_ab_report


def test_build_ab_report_pairs_v5_and_legacy(tmp_db, tmp_path):
    base_row = {
        "snapshot_id": "snap_ab",
        "generated_at": "2026-05-04T12:00:00",
        "tour": "pga",
        "event_id": "evt_ab",
        "event_name": "Test Open",
        "market_family": "matchup",
        "market_type": "tournament_matchups",
        "player_key": "p1",
        "player_display": "P1",
        "opponent_key": "p2",
        "opponent_display": "P2",
        "book": "draftkings",
        "odds": "+100",
        "implied_prob": 0.50,
        "is_value": 1,
    }
    rows = [
        {
            **base_row,
            "section": "live",
            "model_prob": 0.55,
            "ev": 0.05,
            "payload_json": json.dumps({"model_variant": "v5"}),
        },
        {
            **base_row,
            "section": "legacy",
            "model_prob": 0.50,
            "ev": 0.02,
            "payload_json": json.dumps({"model_variant": "baseline"}),
        },
    ]
    tmp_db.store_market_prediction_rows(rows)

    report = build_ab_report("evt_ab", output_dir=tmp_path, write_files=True)
    assert report["ok"] is True
    assert report["counts"]["paired_keys"] == 1
    assert report["paired_metrics"]["mean_model_prob_delta_v5_minus_legacy"] == 0.05
    assert report["paired_metrics"]["mean_ev_delta_v5_minus_legacy"] == 0.03
    assert "artifact_paths" in report
    json_name = Path(report["artifact_paths"]["json"]).name
    assert (tmp_path / json_name).exists()


def test_build_ab_report_requires_event_id():
    out = build_ab_report("", write_files=False)
    assert out["ok"] is False
