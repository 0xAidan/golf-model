"""Tests for weighted walk-forward evaluation helpers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_event_classification_and_weights():
    """Majors and signature events should get stronger weighting than regular stops."""
    from backtester.weighted_walkforward import classify_event, event_weight

    masters = classify_event("Masters Tournament")
    api = classify_event("Arnold Palmer Invitational presented by Mastercard")
    regular = classify_event("John Deere Classic")

    assert masters == "major"
    assert api == "signature"
    assert regular == "regular"
    assert event_weight(masters) > event_weight(api) > event_weight(regular)


def test_build_expanding_splits_preserves_temporal_order():
    """Train windows should only contain earlier events than the test window."""
    from backtester.weighted_walkforward import build_expanding_splits

    events = [
        {"event_id": "A", "year": 2022, "event_date": "2022-01-01"},
        {"event_id": "B", "year": 2022, "event_date": "2022-02-01"},
        {"event_id": "C", "year": 2022, "event_date": "2022-03-01"},
        {"event_id": "D", "year": 2022, "event_date": "2022-04-01"},
    ]

    splits = build_expanding_splits(events, min_train_events=2, test_window_size=1)

    assert len(splits) == 2
    assert [event["event_id"] for event in splits[0]["train_events"]] == ["A", "B"]
    assert [event["event_id"] for event in splits[0]["test_events"]] == ["C"]
    assert [event["event_id"] for event in splits[1]["train_events"]] == ["A", "B", "C"]
    assert [event["event_id"] for event in splits[1]["test_events"]] == ["D"]


def test_compute_weighted_metrics_emits_weighted_and_unweighted_views():
    """Summary metrics should surface both weighted and raw values."""
    from backtester.weighted_walkforward import compute_weighted_metrics

    event_results = [
        {
            "event_id": "major-1",
            "event_class": "major",
            "weight": 3.0,
            "roi_pct": 10.0,
            "clv_avg": 0.05,
            "calibration_error": 0.04,
            "total_bets": 30,
            "max_drawdown_pct": 4.0,
        },
        {
            "event_id": "regular-1",
            "event_class": "regular",
            "weight": 1.0,
            "roi_pct": 2.0,
            "clv_avg": 0.01,
            "calibration_error": 0.08,
            "total_bets": 40,
            "max_drawdown_pct": 6.0,
        },
    ]

    metrics = compute_weighted_metrics(event_results)

    assert metrics["weighted_roi_pct"] == 8.0
    assert metrics["unweighted_roi_pct"] == 6.0
    assert metrics["total_bets"] == 70
    assert metrics["events_evaluated"] == 2


def test_guardrails_block_large_regressions_and_low_sample(monkeypatch):
    """Guardrails should reject unstable or under-sampled candidates."""
    from backtester.weighted_walkforward import evaluate_guardrails

    monkeypatch.setattr(
        "src.config.get_autoresearch_guardrail_params",
        lambda: {
            "min_bets": 30,
            "max_clv_regression": 0.02,
            "max_calibration_regression": 0.03,
            "max_drawdown_regression": 10.0,
        },
    )

    candidate = {
        "total_bets": 40,
        "weighted_clv_avg": -0.02,
        "weighted_calibration_error": 0.14,
        "max_drawdown_pct": 19.0,
    }
    baseline = {
        "total_bets": 160,
        "weighted_clv_avg": 0.03,
        "weighted_calibration_error": 0.05,
        "max_drawdown_pct": 8.0,
    }

    guardrails = evaluate_guardrails(candidate, baseline, min_bets=100)

    assert guardrails["passed"] is False
    assert "insufficient_sample" in guardrails["reasons"]
    assert "clv_regression" in guardrails["reasons"]
    assert "calibration_regression" in guardrails["reasons"]
    assert "drawdown_regression" in guardrails["reasons"]


def test_evaluate_weighted_walkforward_segments_results(monkeypatch):
    """Full evaluation should aggregate per-event results and segment them by event class."""
    from backtester.weighted_walkforward import evaluate_weighted_walkforward
    from backtester.strategy import StrategyConfig

    events = [
        {
            "event_id": "masters",
            "year": 2024,
            "event_date": "2024-04-14",
            "event_name": "Masters Tournament",
        },
        {
            "event_id": "api",
            "year": 2024,
            "event_date": "2024-03-10",
            "event_name": "Arnold Palmer Invitational presented by Mastercard",
        },
        {
            "event_id": "jdc",
            "year": 2024,
            "event_date": "2024-07-14",
            "event_name": "John Deere Classic",
        },
    ]

    fake_results = {
        ("api", "candidate"): {"roi_pct": 2.0, "clv_avg": 0.01, "calibration_error": 0.05, "total_bets": 20},
        ("masters", "candidate"): {"roi_pct": 6.0, "clv_avg": 0.02, "calibration_error": 0.04, "total_bets": 18},
        ("jdc", "candidate"): {"roi_pct": -1.0, "clv_avg": 0.005, "calibration_error": 0.06, "total_bets": 25},
        ("api", "baseline"): {"roi_pct": 1.0, "clv_avg": 0.01, "calibration_error": 0.05, "total_bets": 20},
        ("masters", "baseline"): {"roi_pct": 2.0, "clv_avg": 0.015, "calibration_error": 0.05, "total_bets": 18},
        ("jdc", "baseline"): {"roi_pct": 0.0, "clv_avg": 0.008, "calibration_error": 0.05, "total_bets": 25},
    }

    def fake_runner(event, strategy):
        key = "candidate" if strategy.name == "candidate" else "baseline"
        return fake_results[(event["event_id"], key)]

    result = evaluate_weighted_walkforward(
        strategy=StrategyConfig(name="candidate"),
        baseline_strategy=StrategyConfig(name="baseline"),
        events=events,
        replay_runner=fake_runner,
        min_train_events=1,
        test_window_size=1,
    )

    assert result["summary_metrics"]["events_evaluated"] == 2
    assert "major" in result["segmented_metrics"]
    assert "regular" in result["segmented_metrics"]
    assert result["guardrail_results"]["passed"] is True
