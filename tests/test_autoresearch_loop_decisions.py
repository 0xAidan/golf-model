from scripts.run_autoresearch_loop import run_loop


def test_loop_keeps_only_improving_guardrail_pass(monkeypatch):
    monkeypatch.setattr("scripts.run_autoresearch_loop.load_pilot_contract", lambda: {"pilot_contract_version": 1, "checkpoint_set_id": "v1"})
    monkeypatch.setattr("scripts.run_autoresearch_loop._load_strategy", lambda: {"name": "x", "min_ev": 0.05})
    monkeypatch.setattr("scripts.run_autoresearch_loop._save_strategy", lambda _payload: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop._git_add_commit", lambda _msg: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop._git_reset_previous", lambda: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop._git_commit", lambda: "abc")
    monkeypatch.setattr("scripts.run_autoresearch_loop._write_ledger_row", lambda _row: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop.strategy_hash", lambda _payload: "hash")

    values = [
        {"autoresearch_metric": "1.0", "autoresearch_guardrails": "pass", "autoresearch_sample": "10", "autoresearch_checkpoint_summary": "{}"},
        {"autoresearch_metric": "1.2", "autoresearch_guardrails": "pass", "autoresearch_sample": "10", "autoresearch_checkpoint_summary": "{}"},
        {"autoresearch_metric": "0.9", "autoresearch_guardrails": "pass", "autoresearch_sample": "10", "autoresearch_checkpoint_summary": "{}"},
    ]
    monkeypatch.setattr("scripts.run_autoresearch_loop._run_eval", lambda timeout_seconds=120: values.pop(0))

    summary = run_loop(iterations=2, seed=42, timeout_seconds=5)
    assert summary["kept"] == 1

