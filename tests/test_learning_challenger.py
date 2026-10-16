"""Temporal and evidence invariants for the additive learned ranking model."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
import sqlite3

import numpy as np
import pytest

from backtester import learning_challenger as trainer
from src.models.learning_challenger import (
    FEATURE_NAMES, eligible_history, pair_probability, player_features, rank_players,
)


def _round(event: str, completed: str, value: float, *, number: int = 1) -> dict:
    return {"event_id": event, "year": 2025, "round_num": number, "course_num": 1, "tour": "pga", "dg_id": 1,
            "player_key": "player", "event_completed": completed, "sg_total": value,
            "sg_ott": value / 4, "sg_app": value / 4, "sg_arg": value / 4, "sg_putt": value / 4}


def test_features_exclude_same_day_future_and_conflicting_rounds():
    prior = [_round("a", "2025-01-01", 1.0), _round("b", "2025-01-03", 2.0)]
    contaminated = prior + [_round("c", "2025-01-05", 100.0), _round("d", "2025-01-06", 100.0)]
    assert player_features(contaminated, as_of="2025-01-05") == player_features(prior, as_of="2025-01-05")
    assert len(eligible_history(prior + [prior[0]], "2025-01-05")) == 2
    conflict = {**prior[0], "sg_total": 10.0}
    assert [r["event_id"] for r in eligible_history(prior + [conflict], "2025-01-05")] == ["b"]


def test_chronological_splits_group_dates_and_purge_crossing_events():
    rows = []
    for index in range(30):
        start = date(2025, 1, 1) + timedelta(days=index * 7)
        rows.append({"event_key": str(index), "start": start.isoformat(), "end": (start + timedelta(days=3)).isoformat()})
    rows.append({**rows[17], "event_key": "overlap", "end": rows[18]["start"]})
    rows.append({**rows[18], "event_key": "same-day"})
    splits = trainer.chronological_split(rows)
    assert "overlap" not in {r["event_key"] for split in splits.values() for r in split}
    assert {r["event_key"] for r in splits["validation"]} >= {"18", "same-day"}
    assert max(r["end"] for r in splits["train"]) < min(r["start"] for r in splits["validation"])
    assert max(r["end"] for r in splits["validation"]) < min(r["start"] for r in splits["test"])


def test_pair_metrics_use_events_as_equal_weight_not_correlated_pair_count():
    rows = [{"event_key": "small", "finish": 1, "target_sg": 0}, {"event_key": "small", "finish": 2, "target_sg": 0}]
    scores = [0.0, 1.0]  # Wrong order for this whole event.
    for index in range(10):
        rows.append({"event_key": "large", "finish": index + 1, "target_sg": 0})
        scores.append(float(10 - index))
    result = trainer.evaluate(rows, np.asarray(scores), 1.0)
    assert result["pairs"] == 46
    assert result["events"] == 2
    assert result["pair_accuracy"] == 0.5
    assert "not independent" in result["sample_unit"]


def test_crossfit_calibration_never_fits_its_forecast_event(monkeypatch):
    rows = []
    for index in range(24):
        start = date(2025, 1, 1) + timedelta(days=index * 7)
        rows.append({"event_key": str(index), "start": start.isoformat(), "end": (start + timedelta(days=3)).isoformat(), "features": [0.0] * len(FEATURE_NAMES), "target_sg": 0.0})
    fits = []
    original = trainer.fit_ridge

    def recording_fit(training, ridge):
        fits.append(max(r["end"] for r in training))
        return original(training, ridge)

    monkeypatch.setattr(trainer, "fit_ridge", recording_fit)
    held, forecasts = trainer.crossfit_scores(rows, 0.1)
    assert len(held) == len(forecasts) == 16
    assert len(fits) == 4
    for index, end in enumerate(fits):
        assert end < held[index * 4]["start"]


def _synthetic_rows():
    rows = []
    rng = np.random.default_rng(20261015)
    for event in range(30):
        start = date(2025, 1, 1) + timedelta(days=event * 7)
        for player in range(20):
            skill = (player - 10) / 10
            features = [skill] + rng.normal(0, 0.1, len(FEATURE_NAMES) - 1).tolist()
            rows.append({"event_id": str(event), "year": 2025, "event_key": str(event), "event_name": f"Event {event}",
                         "start": start.isoformat(), "end": (start + timedelta(days=3)).isoformat(),
                         "player_key": str(player), "player_display": str(player), "features": features,
                         "target_sg": skill + rng.normal(0, 0.5), "finish": 20 - player,
                         "baseline_score": 50 + skill * 10, "naive_sg": skill,
                         "history_rounds": 24, "last_observed": (start - timedelta(days=4)).isoformat()})
    return rows


def test_test_outcomes_cannot_change_selection_or_fitted_model(monkeypatch):
    rows = _synthetic_rows()
    monkeypatch.setattr(trainer, "attach_baseline", lambda *args: None)
    monkeypatch.setattr(trainer, "build_dataset", lambda *args: (rows, {}, [[], []]))
    source = {"source_sha256": "a" * 64}
    first_report, first_model, _, _ = trainer.train_and_evaluate({}, source, as_of="2026-01-01")
    altered = deepcopy(rows)
    test_keys = set(first_report["splits"]["test"]["event_ids"])
    for row in altered:
        if row["event_key"] in test_keys:
            row["target_sg"] += 10
            row["finish"] = 21 - row["finish"]
    monkeypatch.setattr(trainer, "build_dataset", lambda *args: (altered, {}, [[], []]))
    second_report, second_model, _, _ = trainer.train_and_evaluate({}, source, as_of="2026-01-01")
    assert first_model["hash"] == second_model["hash"]
    assert first_report["selection"] == second_report["selection"]
    assert first_report["comparisons"]["test"]["candidate"] != second_report["comparisons"]["test"]["candidate"]
    assert first_report["promotion"]["eligible"] is False
    assert first_report["market_evidence"]["roi_pct"] is None
    assert first_report["market_evidence"]["avg_clv_pct"] is None


def test_projection_requires_coverage_and_preserves_probability_symmetry():
    model = {"feature_names": list(FEATURE_NAMES), "feature_mean": [0.0] * len(FEATURE_NAMES),
             "feature_scale": [1.0] * len(FEATURE_NAMES), "coefficients": [1.0] + [0.0] * (len(FEATURE_NAMES) - 1),
             "intercept": 0.0, "pair_slope": 0.8, "minimum_history_rounds": 8}
    history = [_round(str(i), (date(2025, 1, 1) + timedelta(days=i)).isoformat(), 1.0) for i in range(8)]
    ranks = rank_players(model, history, [{"player_key": "player"}, {"player_key": "uncovered"}], as_of="2025-02-01")
    assert [r["player_key"] for r in ranks] == ["player"]
    assert ranks[0]["expected_sg_per_round"] == 0.5
    assert ranks[0]["rank"] == 1
    assert pair_probability(model, 1.0, -1.0) + pair_probability(model, -1.0, 1.0) == pytest.approx(1.0)


def test_empty_data_and_absent_closing_quotes_are_explicit():
    report, model, predictions, baseline = trainer.train_and_evaluate({}, {"source_sha256": "empty"}, as_of="2026-10-16")
    assert report["state"] == "insufficient_data"
    assert report["market_evidence"]["clv_count"] == 0
    assert report["market_evidence"]["avg_clv_pct"] is None
    assert model is None and predictions == [] and baseline["preserved"]


def test_artifacts_never_overwrite_prior_run(monkeypatch, tmp_path):
    monkeypatch.setattr(trainer, "ROOT", tmp_path)
    report = {"protocol_hash": "protocol", "candidate": {"hash": "candidate"}, "as_of": "2026-10-16", "state": "evaluated"}
    source = {"source_sha256": "source"}
    baseline = {"hash": "baseline"}
    first = trainer.save_artifacts(tmp_path / "runs", report, {"a": 1}, [], baseline, source)
    second = trainer.save_artifacts(tmp_path / "runs", {**report, "state": "changed"}, {"a": 2}, [], baseline, source)
    assert first == second
    assert '"a": 1' in (first / "model.json").read_text()
    assert '"state": "evaluated"' in (first / "report.json").read_text()
    third = trainer.save_artifacts(tmp_path / "runs", {**report, "candidate": {"hash": "new"}}, {"a": 3}, [], baseline, source)
    assert third != first
    assert first.exists() and third.exists()


def test_cross_tour_event_id_collision_cannot_mix_target_or_feature_history():
    rounds = []
    for player in range(20):
        for number in range(1, 9):
            rounds.append({**_round("warmup", "2026-01-01", 0.0, number=number), "tour": "pga", "dg_id": player + 1, "year": 2026, "player_key": str(player), "fin_text": str(player + 1)})
        rounds.append({**_round("60", "2026-08-30", 2.0), "tour": "pga", "dg_id": player + 1, "year": 2026, "player_key": str(player), "fin_text": str(player + 1)})
        rounds.append({**_round("60", "2026-05-10", 9.0), "tour": "liv", "dg_id": player + 1, "year": 2026, "player_key": str(player), "fin_text": str(player + 1)})
    calendar = [{"tour": "pga", "event_id": "60", "year": 2026, "start_date": "2026-08-27", "event_name": "TOUR Championship"},
                {"tour": "liv", "event_id": "60", "year": 2026, "start_date": "2026-05-07", "event_name": "LIV Virginia"}]
    dataset, exclusions, _ = trainer.build_dataset({"rounds": rounds, "historical_event_info": calendar}, "2026-09-01")
    assert len(dataset) == 20
    assert {r["target_sg"] for r in dataset} == {2.0}
    assert {r["history_rounds"] for r in dataset} == {8}
    assert {r["naive_sg"] for r in dataset} == {0.0}
    assert exclusions["round_outside_pga_scope"] == 20


def test_calendar_mismatch_is_excluded_without_inventing_start_date():
    rounds = [{**_round("60", "2026-05-10", 1), "tour": "pga", "year": 2026, "fin_text": "1"}]
    calendar = [{"tour": "pga", "event_id": "60", "year": 2026, "start_date": "2026-08-27", "event_name": "TOUR Championship"}]
    dataset, exclusions, _ = trainer.build_dataset({"rounds": rounds, "historical_event_info": calendar}, "2026-09-01")
    assert dataset == []
    assert exclusions["event_without_verified_calendar"] == 1


def test_wal_visible_data_change_updates_source_hash(tmp_path):
    path = tmp_path / "wal.sqlite"
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE rounds(id INTEGER PRIMARY KEY, sg_total REAL)")
    writer.execute("INSERT INTO rounds(sg_total) VALUES(1)")
    writer.commit()
    tables1, source1 = trainer.load_source(path)
    writer.execute("INSERT INTO rounds(sg_total) VALUES(2)")
    writer.commit()
    tables2, source2 = trainer.load_source(path)
    assert len(tables1["rounds"]) == 1 and len(tables2["rounds"]) == 2
    assert source1["source_sha256"] != source2["source_sha256"]
    writer.close()


def test_original_baseline_stays_pinned_when_live_config_changes():
    first = trainer.preserve_baseline({}, {})
    live_changed = {"track_configs": [{"track": "dashboard", "status": "active", "id": 999, "strategy_bundle_json": '{"new_model": true}'}]}
    assert trainer.preserve_baseline(live_changed, {"git_commit": "new-live-commit"}) == first


def test_original_comparator_rejects_changed_source(monkeypatch, tmp_path):
    monkeypatch.setattr(trainer, "ROOT", tmp_path)
    directory = tmp_path / "config" / "model-baselines"
    directory.mkdir(parents=True)
    baseline = {"source_hashes": {"changed.py": "expected"}}
    baseline["hash"] = trainer.canonical_hash(baseline)
    (directory / trainer.FROZEN_BASELINE_FILENAME).write_text(json.dumps(baseline))
    (tmp_path / "changed.py").write_text("different")
    with pytest.raises(trainer.ComparatorSourceChanged, match="comparator_source_changed"):
        trainer.preserve_baseline({}, {})


def test_events_without_decisive_pairs_do_not_divide_by_zero():
    rows = [{"event_key": "all-cut", "finish": 1000.0, "target_sg": -1.0} for _ in range(20)]
    result = trainer.evaluate(rows, np.zeros(20), 1.0)
    assert result["pairs"] == 0
    assert result["pair_log_loss"] is None
