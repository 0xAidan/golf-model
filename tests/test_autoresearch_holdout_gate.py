from scripts.run_autoresearch_holdout import run_holdout


def test_holdout_returns_verdict(monkeypatch):
    monkeypatch.setattr("scripts.run_autoresearch_holdout.ensure_initialized", lambda: None)
    monkeypatch.setattr("scripts.run_autoresearch_holdout.load_pilot_contract", lambda: {"pilot_contract_version": 1})
    monkeypatch.setattr("scripts.run_autoresearch_holdout.load_strategy_overrides", lambda _path=None: {"name": "candidate"})
    monkeypatch.setattr("scripts.run_autoresearch_holdout.get_research_champion", lambda *_args, **_kwargs: type("S", (), {"__dict__": {"name": "baseline"}})())
    monkeypatch.setattr("scripts.run_autoresearch_holdout.get_live_weekly_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "scripts.run_autoresearch_holdout._select_holdout_events",
        lambda count: [
            {"event_id": "a", "year": 2024, "event_name": "A", "as_of_date": "2024-01-01"},
            {"event_id": "b", "year": 2024, "event_name": "B", "as_of_date": "2024-01-02"},
            {"event_id": "c", "year": 2024, "event_name": "C", "as_of_date": "2024-01-03"},
        ][:count],
    )
    monkeypatch.setattr(
        "scripts.run_autoresearch_holdout._event_metrics",
        lambda event, strategy: {"roi_pct": 1.0, "clv_avg": 0.01, "calibration_error": 0.02, "total_bets": 20, "max_drawdown_pct": 0.0},
    )
    monkeypatch.setattr("scripts.run_autoresearch_holdout.evaluate_guardrails", lambda *_args, **_kwargs: {"passed": True})
    monkeypatch.setattr("scripts.run_autoresearch_holdout.compute_blended_score", lambda summary, _guards: summary["weighted_roi_pct"])
    monkeypatch.setattr("scripts.run_autoresearch_holdout.strategy_hash", lambda _payload: "hash")

    out = run_holdout(holdout_count=3)
    assert out["holdout_verdict"] in {"pass", "fail"}
    assert "holdout_metric_delta" in out

