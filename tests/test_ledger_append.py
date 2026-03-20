"""Ledger JSONL append (unified schema)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_append_ledger_cli_loop_roundtrip(tmp_path, monkeypatch):
    from backtester.research_lab import ledger

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(ledger, "LEGACY_LOOP_LEDGER", tmp_path / "legacy.jsonl")

    row = {
        "source": "cli_loop",
        "trial_id": "test-1",
        "duration_ms": 10,
        "scalar_metric": 1.23,
    }
    ledger.append_ledger_row(row)

    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["source"] == "cli_loop"
    assert data["scalar_metric"] == 1.23

    legacy_lines = (tmp_path / "legacy.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(legacy_lines) == 1


def test_benchmark_spec_hash_stable():
    from backtester.research_lab.benchmark_fingerprint import benchmark_spec_hash
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec

    a = WalkForwardBenchmarkSpec(years=[2024, 2025])
    b = WalkForwardBenchmarkSpec(years=[2024, 2025])
    assert benchmark_spec_hash(a) == benchmark_spec_hash(b)
