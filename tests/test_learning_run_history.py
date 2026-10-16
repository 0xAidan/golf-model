"""Run comparisons retain cohort boundaries and never publish private source fields."""
import json
import os
from pathlib import Path

import pytest

from src.learning_run_history import build_run_history, publish_run_history


def report(event="event-1", source="a" * 64):
    return {"schema_version": 2, "state": "evaluated", "generated_at": "2026-10-16T03:00:00Z", "as_of": "2026-10-16",
            "candidate": {"hash": "b" * 64, "ranking_unit": "expected_sg_per_round"},
            "baseline": {"hash": "c" * 64}, "data": {"source_sha256": source, "private_source": "/Users/private/.env"},
            "protocol_hash": "d" * 64, "protocol": {"test_status": "exposed_retrospective_2026_audit"},
            "splits": {"test": {"event_ids": [event]}},
            "comparisons": {"test": {"candidate": {"events": 1, "pair_log_loss": 0.6, "brier": 0.2, "sg_rmse": 1.5},
                                       "naive": {"pair_log_loss": 0.65}}},
            "promotion": {"eligible": False}}


def test_run_history_does_not_compare_other_cohorts_or_claim_multiple_weeks(tmp_path):
    for i, payload in enumerate([report(), report(), report("other-event"), report(source="e" * 64)], 1):
        path = tmp_path / ("20261016-" + str(i) * 16)
        path.mkdir()
        (path / "report.json").write_text(json.dumps(payload))
    invalid = tmp_path / ("20261016-" + "f" * 16)
    invalid.mkdir()
    (invalid / "report.json").write_text(json.dumps(report()))
    (invalid / "INVALIDATED.json").write_text("{}")
    before = {str(p): p.read_bytes() for p in tmp_path.glob("*/*")}
    result = build_run_history(tmp_path)
    assert result["summary"]["total_runs"] == 4
    assert result["summary"]["comparable_groups"] == 3
    assert result["summary"]["weeks_observed"] == 1
    assert result["summary"]["excluded"] == {"invalidated_artifact": 1}
    assert len({row["comparison_group"] for row in result["runs"] if row["run_id"].endswith(("1" * 16, "2" * 16))}) == 1
    assert all(row["promotion_status"] == "research_only" for row in result["runs"])
    assert all(row["test_status"] == "exposed_retrospective" for row in result["runs"])
    assert "/Users/" not in json.dumps(result)
    assert ".env" not in json.dumps(result)
    assert before == {str(p): p.read_bytes() for p in tmp_path.glob("*/*")}


def test_bad_artifact_is_unavailable_and_truncation_is_explicit(tmp_path):
    for i in (1, 2):
        p = tmp_path / ("20261016-" + str(i) * 16)
        p.mkdir()
        (p / "report.json").write_text(json.dumps(report()))
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "report.json").write_text("not json")
    result = build_run_history(tmp_path, maximum=1)
    assert len(result["runs"]) == 1
    assert result["summary"]["total_runs"] == 2
    assert result["summary"]["truncated"] is True
    assert result["summary"]["excluded"] == {"unavailable_or_unsupported_artifact": 1}


def test_public_history_is_readable_before_atomic_replace_with_private_umask(tmp_path, monkeypatch):
    destination = tmp_path / "public" / "learning-history.json"
    replacements = []
    original_replace = Path.replace

    def checked_replace(self, target):
        assert self.stat().st_mode & 0o777 == 0o644
        replacements.append(str(target))
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", checked_replace)
    previous = os.umask(0o077)
    try:
        publish_run_history(tmp_path / "private-runs", destination)
    finally:
        os.umask(previous)
    assert replacements == [str(destination)]
    assert destination.stat().st_mode & 0o777 == 0o644


def test_public_latest_stays_readable_when_later_publication_fails(tmp_path, monkeypatch):
    from scripts import train_learning_challenger as cli
    from src import learning_run_history

    output, destination = tmp_path / "private-runs", tmp_path / "public" / "learning-latest.json"
    artifact = output / "private-fixture"
    payload = {**report(), "learning": {}, "current_rankings": []}
    payload["data"].pop("private_source")
    monkeypatch.setattr(cli, "load_source", lambda *args, **kwargs: ({}, {}))
    monkeypatch.setattr(cli, "train_and_evaluate", lambda *args, **kwargs: (payload, None, [], {}))

    def save(*args, **kwargs):
        artifact.mkdir(parents=True)
        (artifact / "report.json").write_text(json.dumps(payload))
        return artifact

    def fail_after_latest(*args, **kwargs):
        raise RuntimeError("injected later history publication failure")

    monkeypatch.setattr(cli, "save_artifacts", save)
    monkeypatch.setattr(learning_run_history, "publish_run_history", fail_after_latest)
    original_replace = Path.replace
    observed = []

    def checked_replace(self, target):
        assert self.stat().st_mode & 0o777 == 0o644
        observed.append(str(target))
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", checked_replace)
    previous = os.umask(0o077)
    try:
        with pytest.raises(RuntimeError, match="injected later"):
            cli.main(["--source", "unused-read-only.sqlite", "--output", str(output), "--public-report", str(destination)])
    finally:
        os.umask(previous)
    assert observed == [str(destination)]
    assert destination.stat().st_mode & 0o777 == 0o644
    assert (artifact / "report.json").stat().st_mode & 0o777 == 0o600
