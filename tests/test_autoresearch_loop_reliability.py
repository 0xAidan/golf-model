from scripts.run_autoresearch_loop import run_loop


def test_loop_handles_eval_errors(monkeypatch):
    monkeypatch.setattr("scripts.run_autoresearch_loop.load_pilot_contract", lambda: {"pilot_contract_version": 1, "checkpoint_set_id": "v1"})
    monkeypatch.setattr("scripts.run_autoresearch_loop._load_strategy", lambda: {"name": "x"})
    monkeypatch.setattr("scripts.run_autoresearch_loop._save_strategy", lambda _payload: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop._git_add_commit", lambda _msg: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop._git_reset_previous", lambda: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop._git_commit", lambda: "abc")
    monkeypatch.setattr("scripts.run_autoresearch_loop._write_ledger_row", lambda _row: None)
    monkeypatch.setattr("scripts.run_autoresearch_loop.strategy_hash", lambda _payload: "hash")

    calls = {"n": 0}

    def _fake_eval(timeout_seconds=120):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "autoresearch_metric": "1.0",
                "autoresearch_guardrails": "pass",
                "autoresearch_sample": "10",
                "autoresearch_checkpoint_summary": "{}",
            }
        raise RuntimeError("boom")

    monkeypatch.setattr("scripts.run_autoresearch_loop._run_eval", _fake_eval)
    summary = run_loop(iterations=1, seed=42, timeout_seconds=5)
    assert summary["failed"] == 1

