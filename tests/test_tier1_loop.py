"""Tests for the Tier 1 loop: mutation ranges, keep/discard, confirmation, staging."""

from __future__ import annotations

import json
import random

import pytest

from backtester import tier1_loop as t1
from backtester.strategy_config_artifact import (
    ConfigArtifactError,
    SCHEMA_VERSION,
    artifact_hash,
)


def _artifact(**overrides) -> dict:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "name": "champion_candidate",
        "overrides": {"min_ev": 0.06, "kelly_fraction": 0.25},
        "ranges": {
            "min_ev": {"min": 0.02, "max": 0.18},
            "kelly_fraction": {"min": 0.05, "max": 0.45},
        },
        "segments": {},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Mutation proposal
# ---------------------------------------------------------------------------


def test_propose_mutation_stays_in_range():
    rng = random.Random(7)
    artifact = _artifact()
    for _ in range(50):
        mutated, description = t1.propose_mutation(artifact, rng=rng)
        field, _, value_text = description.partition(": ")
        lo = artifact["ranges"][field]["min"]
        hi = artifact["ranges"][field]["max"]
        assert lo <= float(value_text.split("->")[1]) <= hi


def test_propose_mutation_requires_ranges():
    rng = random.Random(1)
    with pytest.raises(ConfigArtifactError):
        t1.propose_mutation({"schema_version": 2, "name": "x", "ranges": {}}, rng=rng)


def test_mutation_changes_hash():
    rng = random.Random(3)
    artifact = _artifact()
    mutated, description = t1.propose_mutation(artifact, rng=rng)
    assert description
    assert artifact_hash(mutated) != artifact_hash(artifact)


# ---------------------------------------------------------------------------
# Cycle behavior with monkeypatched evaluation (deterministic verdicts)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, roi: float, bets: int):
        from backtester.research_lab.canonical import EvaluationResult

        self.summary_metrics = {
            "weighted_roi_pct": roi,
            "total_bets": bets,
            "weighted_clv_avg": 0.02 if roi > 0 else -0.01,
            "weighted_calibration_error": 0.03,
            "max_drawdown_pct": 5.0,
            "unweighted_roi_pct": roi,
        }
        self.baseline_summary_metrics = self.summary_metrics
        self.guardrail_results = {}
        self.blended_score = 0.0
        self.feasible = True
        self.metadata = {"fast_tier": True}


@pytest.fixture()
def offline_cycle(monkeypatch, tmp_path):
    """Patch evaluation + windows + dossier dir so run_tier1_cycle runs fully offline."""
    windows = {
        "search": [{"event_id": str(i), "year": 2026, "event_name": "E", "event_date": f"2026-06-{i:02d}"} for i in range(10, 23)],
        "confirmation": [
            {"event_id": "30", "year": 2026, "event_name": "C", "event_date": "2026-07-01"},
            {"event_id": "31", "year": 2026, "event_name": "D", "event_date": "2026-07-08"},
            {"event_id": "32", "year": 2026, "event_name": "F", "event_date": "2026-07-15"},
        ],
        "excluded_sealed": True,
    }
    monkeypatch.setattr(t1, "select_research_windows", lambda **kw: windows)

    ledger_rows: list[dict] = []
    monkeypatch.setattr(t1, "append_ledger_row", lambda row: ledger_rows.append(row) or row)
    monkeypatch.setattr(t1, "_git_head", lambda: "testhead")
    monkeypatch.setattr(t1, "DOSSIER_DIR", tmp_path / "dossiers")

    return {"ledger_rows": ledger_rows, "windows": windows}


def test_cycle_keeps_and_confirms_profitable_candidate(offline_cycle, monkeypatch):
    calls = {"search": 0}

    def fake_eval(strategy, baseline, events):
        # Search window: strong positive; confirmation window: still positive.
        roi = 25.0
        result = _FakeResult(roi=roi, bets=400 if len(events) > 5 else 40)
        # Guardrails pass when candidate beats baseline on CLV and sample is big.
        from backtester.weighted_walkforward import evaluate_guardrails

        baseline_like = dict(result.summary_metrics)
        baseline_like["weighted_clv_avg"] = -0.05
        result.guardrail_results = evaluate_guardrails(result.summary_metrics, baseline_like)
        result.baseline_summary_metrics = baseline_like
        calls["search"] += 1
        return result

    monkeypatch.setattr(t1, "evaluate_on_events", fake_eval)

    summary = t1.run_tier1_cycle(seed=11, max_trials=3)
    assert summary["keeps"] >= 1
    assert summary["verdict"] == "staged_for_review"
    kinds = [r["kind"] for r in offline_cycle["ledger_rows"]]
    assert "trial" in kinds and "confirmation" in kinds and "promotion_ready" in kinds
    dossiers = list(t1.DOSSIER_DIR.glob("promotion_ready_*.json"))
    assert len(dossiers) >= 1
    payload = json.loads(dossiers[0].read_text())
    assert payload["status"].startswith("PROMOTION_READY")
    assert "trials_run_this_lineage" in payload["multiplicity_context"]


def test_cycle_discards_when_guardrails_fail(offline_cycle, monkeypatch):
    def fake_eval(strategy, baseline, events):
        from backtester.weighted_walkforward import evaluate_guardrails

        result = _FakeResult(roi=-30.0, bets=500)
        bad_baseline = dict(result.summary_metrics)
        bad_baseline["weighted_clv_avg"] = 0.05  # candidate CLV regresses badly
        result.guardrail_results = evaluate_guardrails(result.summary_metrics, bad_baseline)
        result.baseline_summary_metrics = bad_baseline
        return result

    monkeypatch.setattr(t1, "evaluate_on_events", fake_eval)
    summary = t1.run_tier1_cycle(seed=5, max_trials=4)
    assert summary["discards"] >= 1
    assert summary["staged_promotions"] == 0
    assert summary["verdict"] == "no_promotable_candidate"
    decisions = [r.get("decision") for r in offline_cycle["ledger_rows"] if r["kind"] == "trial"]
    assert all(d in ("discard", "report_only") for d in decisions)


def test_cycle_report_only_below_sample_floor(offline_cycle, monkeypatch):
    def fake_eval(strategy, baseline, events):
        from backtester.weighted_walkforward import evaluate_guardrails

        result = _FakeResult(roi=99.0, bets=42)  # tiny sample: below 300 floor
        like = dict(result.summary_metrics)
        result.guardrail_results = evaluate_guardrails(result.summary_metrics, like)
        result.baseline_summary_metrics = like
        return result

    monkeypatch.setattr(t1, "evaluate_on_events", fake_eval)
    summary = t1.run_tier1_cycle(seed=2, max_trials=2)
    assert summary["staged_promotions"] == 0
    decisions = [r.get("decision") for r in offline_cycle["ledger_rows"] if r["kind"] == "trial"]
    assert decisions and all(d == "report_only" for d in decisions)


def test_no_data_verdict_without_search_events(monkeypatch):
    monkeypatch.setattr(
        t1,
        "select_research_windows",
        lambda **kw: {"search": [], "confirmation": [], "excluded_sealed": True},
    )
    monkeypatch.setattr(t1, "append_ledger_row", lambda row: row)
    summary = t1.run_tier1_cycle(seed=1, max_trials=1)
    assert summary["verdict"] == "no_data"


def test_alert_fired_on_promotion_ready(offline_cycle, monkeypatch):
    alerts: list[str] = []

    def fake_eval(strategy, baseline, events):
        from backtester.weighted_walkforward import evaluate_guardrails

        result = _FakeResult(roi=20.0, bets=400 if len(events) > 5 else 40)
        like = dict(result.summary_metrics)
        like["weighted_clv_avg"] = -0.05
        result.guardrail_results = evaluate_guardrails(result.summary_metrics, like)
        result.baseline_summary_metrics = like
        return result

    monkeypatch.setattr(t1, "evaluate_on_events", fake_eval)
    t1.run_tier1_cycle(seed=9, max_trials=2, alert_fn=alerts.append)
    assert any("PROMOTION-READY" in a for a in alerts)
