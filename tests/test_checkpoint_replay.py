from backtester.checkpoint_replay import summarize_checkpoint_results


def test_checkpoint_summary_aggregates_metrics():
    results = [
        {"metrics": {"roi_pct": 2.0, "clv_avg": 0.01, "calibration_error": 0.03, "total_bets": 10}},
        {"metrics": {"roi_pct": 4.0, "clv_avg": 0.03, "calibration_error": 0.05, "total_bets": 15}},
        {"metrics": {"roi_pct": 6.0, "clv_avg": 0.05, "calibration_error": 0.07, "total_bets": 20}},
    ]
    out = summarize_checkpoint_results(results)
    assert out["checkpoints_evaluated"] == 3
    assert out["total_bets"] == 45
    assert out["weighted_roi_pct"] == 4.0

