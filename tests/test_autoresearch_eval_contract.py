from scripts.run_autoresearch_eval import _evaluate


def test_eval_contract_output_shape(monkeypatch):
    monkeypatch.setattr("scripts.run_autoresearch_eval.ensure_initialized", lambda: None)
    monkeypatch.setattr("scripts.run_autoresearch_eval.validate_contract_documents", lambda: None)
    monkeypatch.setattr(
        "scripts.run_autoresearch_eval.load_pilot_contract",
        lambda: {
            "pilot_contract_version": 1,
            "evaluation_contract_version": 1,
            "checkpoint_set_id": "v1",
        },
    )
    monkeypatch.setattr(
        "scripts.run_autoresearch_eval.load_strategy_overrides",
        lambda _path=None: {"name": "x"},
    )
    monkeypatch.setattr(
        "scripts.run_autoresearch_eval.get_pilot_checkpoints",
        lambda: {
            "pilot_event": {"event_id": "evt", "year": 2025, "event_name": "The Players", "start_date": "2025-03-10"},
            "checkpoints": [
                {"id": "pre_tournament", "as_of_date": "2025-03-10"},
                {"id": "before_day_2", "as_of_date": "2025-03-11"},
                {"id": "before_day_3", "as_of_date": "2025-03-12"},
            ],
        },
    )
    monkeypatch.setattr("scripts.run_autoresearch_eval.assert_checkpoint_temporal_integrity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.run_autoresearch_eval.get_research_champion", lambda *_args, **_kwargs: type("S", (), {"__dict__": {}, "name": "base"})())
    monkeypatch.setattr("scripts.run_autoresearch_eval.get_live_weekly_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("scripts.run_autoresearch_eval.build_strategy_from_overrides", lambda _ov, baseline: baseline)
    monkeypatch.setattr(
        "scripts.run_autoresearch_eval.replay_checkpoint",
        lambda *_args, **_kwargs: {"checkpoint_id": "x", "as_of_date": "2025-03-10", "metrics": {"roi_pct": 1.0, "clv_avg": 0.01, "calibration_error": 0.02, "total_bets": 10, "max_drawdown_pct": 0.0}},
    )
    monkeypatch.setattr(
        "scripts.run_autoresearch_eval.summarize_checkpoint_results",
        lambda _results: {"weighted_roi_pct": 1.0, "weighted_clv_avg": 0.01, "weighted_calibration_error": 0.02, "total_bets": 30, "max_drawdown_pct": 0.0},
    )
    monkeypatch.setattr("scripts.run_autoresearch_eval.evaluate_guardrails", lambda *_args, **_kwargs: {"passed": True})
    monkeypatch.setattr("scripts.run_autoresearch_eval.compute_blended_score", lambda *_args, **_kwargs: 2.5)
    monkeypatch.setattr("scripts.run_autoresearch_eval.strategy_hash", lambda *_args, **_kwargs: "hash")

    result = _evaluate()
    assert result["metric"] == 2.5
    assert "checkpoint_summary" in result

