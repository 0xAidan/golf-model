"""Tests for evaluator fingerprint stamping in the append-only ledger."""

from __future__ import annotations

import json

import pytest

from backtester.research_lab import ledger as ledger_mod
from backtester.research_lab.fingerprint import compute_evaluator_fingerprint


@pytest.fixture()
def ledger_paths(tmp_path):
    original_main = ledger_mod.LEDGER_PATH
    original_legacy = ledger_mod.LEGACY_LOOP_LEDGER
    ledger_mod.LEDGER_PATH = tmp_path / "ledger.jsonl"
    ledger_mod.LEGACY_LOOP_LEDGER = tmp_path / "autoresearch_runs.jsonl"
    yield tmp_path
    ledger_mod.LEDGER_PATH = original_main
    ledger_mod.LEGACY_LOOP_LEDGER = original_legacy


def test_append_stamps_fingerprint_and_version(ledger_paths):
    ledger_mod.append_ledger_row({"source": "agent", "kind": "unit", "duration_ms": 1})
    row = json.loads(ledger_paths.joinpath("ledger.jsonl").read_text().strip())
    assert row["evaluator_fingerprint"] == compute_evaluator_fingerprint()
    assert row["ts"]
    assert row["source"] == "agent"


def test_append_preserves_explicit_fingerprint(ledger_paths):
    ledger_mod.append_ledger_row(
        {"source": "optuna_mo", "evaluator_fingerprint": "custom0123456789abcdef0123456789abcd"}
    )
    row = json.loads(ledger_paths.joinpath("ledger.jsonl").read_text().strip())
    assert row["evaluator_fingerprint"] == "custom0123456789abcdef0123456789abcd"


def test_append_rejects_unknown_source(ledger_paths):
    from pytest import raises

    with raises(ValueError, match="ledger source"):
        ledger_mod.append_ledger_row({"source": "mystery_lane"})
