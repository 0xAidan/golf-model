"""Verified origins, frozen chronology, nonlinear inference and audit/refit separation."""
from copy import deepcopy
from datetime import date, timedelta
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from backtester import learning_challenger as v1
from backtester import learning_challenger_v2 as trainer
from backtester.learning_corpus import deduplicate, load_verified_corpus
from src.models.learning_challenger import FEATURE_NAMES_V2, player_features_v2, predict_expected_sg


def test_verified_stream_hash_and_snapshot_state_are_required(tmp_path):
    rows = [{"type": "row", "table": table, "row": {"id": 1, "tour": "pga", "dg_id": 1}, "ordinal": 1,
             "row_sha256": v1.canonical_hash({"id": 1, "tour": "pga", "dg_id": 1})}
            for table in ("rounds", "historical_event_info")]
    payload = gzip.compress(("\n".join(json.dumps(r) for r in rows) + "\n").encode())
    vault = tmp_path / "vault.gz"
    vault.write_bytes(payload)
    manifest = {"state": "complete", "quick_check": ["ok"], "source_id": "snapshot",
                "preservation": {"readback_verified": True},
                "logical": {"path": str(vault), "sha256": hashlib.sha256(payload).hexdigest(),
                            "tables": {t: {"state": "complete", "rows": 1} for t in ("rounds", "historical_event_info")}}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    tables, source = load_verified_corpus([path])
    assert source["forensic_sql_admitted"] is False and len(tables["rounds"]) == 1
    assert tables["rounds"][0]["_source_refs"][0]["snapshot_sha256"] == "snapshot"
    manifest["logical"]["sha256"] = "wrong"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_verified_corpus([path])
    manifest["state"] = "salvaged_unverified"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unverified"):
        load_verified_corpus([path])


def test_dedup_preserves_source_refs_and_rejects_conflicting_rounds_without_cross_tour_join():
    row = {"tour": "pga", "event_id": "60", "year": 2026, "round_num": 1, "dg_id": 1,
           "player_key": "original", "sg_total": 1, "event_completed": "2026-08-30", "_source_refs": [{"origin": "a"}]}
    duplicate = {**row, "_source_refs": [{"origin": "b"}]}
    tables, source = deduplicate({"rounds": [row, duplicate, {**row, "tour": "liv"}]}, [])
    assert len(tables["rounds"]) == 2
    assert len(tables["rounds"][0]["_source_refs"]) == 2
    assert source["deduplication"]["duplicate_round_observations"] == 1
    bad, source = deduplicate({"rounds": [row, {**row, "sg_total": 9}]}, [])
    assert bad["rounds"] == []
    assert source["deduplication"]["conflicting_round_identities_excluded"] == 1


def test_calendar_completion_and_sealed_guards_apply_to_feature_history():
    rows = [{"tour": "pga", "event_id": "bad", "year": 2026, "event_completed": "2026-01-01"},
            {"tour": "pga", "event_id": "26", "year": 2026, "event_completed": "2026-06-21"},
            {"tour": "pga", "event_id": "good", "year": 2025, "event_completed": "2025-03-09"}]
    calendar = [{"tour": "pga", "event_id": "bad", "year": 2026, "start_date": "2026-08-01"},
                {"tour": "pga", "event_id": "26", "year": 2026, "start_date": "2026-06-18"},
                {"tour": "pga", "event_id": "good", "year": 2025, "start_date": "2025-03-06"}]
    safe, exclusions = trainer.clean_history({"rounds": rows, "historical_event_info": calendar}, "2026-10-16")
    assert [r["event_id"] for r in safe["rounds"]] == ["good"]
    assert exclusions["sealed_event_never_admitted"] == exclusions["completion_calendar_mismatch"] == 1


def test_extended_features_never_use_current_or_future_events():
    prior = [{"tour": "pga", "event_id": str(i), "year": 2025, "round_num": 1,
              "player_key": "p", "dg_id": 1, "course_num": 7, "event_completed": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
              "sg_total": 1, "sg_ott": 0.3, "sg_app": 0.5, "sg_arg": 0.1, "sg_putt": 0.1} for i in range(20)]
    future = {**prior[0], "event_id": "future", "event_completed": "2025-03-01", "sg_total": 999}
    a = player_features_v2(prior, as_of="2025-03-01", course_num=None)
    b = player_features_v2(prior + [future], as_of="2025-03-01", course_num=None)
    assert a == b and len(a["values"]) == len(FEATURE_NAMES_V2)
    assert a["values"][FEATURE_NAMES_V2.index("course_time_residual")] == 0


def _rows():
    rng = np.random.default_rng(5)
    result = []
    for year, events in ((2020, 12), (2025, 4), (2026, 4)):
        for event in range(events):
            start = date(year, 1, 2) + timedelta(days=event * 7)
            for player in range(20):
                features = rng.normal(0, 0.1, len(FEATURE_NAMES_V2))
                skill = (player - 10) / 10
                features[0] = skill
                features[FEATURE_NAMES_V2.index("sg_raw_50")] = skill
                features[FEATURE_NAMES_V2.index("history_coverage")] = 1
                result.append({"event_id": str(event), "year": year, "event_key": f"{year}:{event}", "event_name": "Synthetic",
                               "start": start.isoformat(), "end": (start + timedelta(days=3)).isoformat(),
                               "features": features.tolist(), "target_sg": skill + rng.normal(0, 0.1), "finish": 20 - player,
                               "player_key": str(player), "history_rounds": 50, "last_observed": "2019-12-01",
                               "baseline_score": 50 + skill * 10, "naive_sg": skill})
    return result


def test_stumps_and_spline_are_reproducible_json_inference():
    rows = _rows()[:240]
    config = trainer.protocol()
    for specification in ({"kind": "boosted_stumps", "iterations": 30, "learning_rate": 0.1},
                          {"kind": "spline_ridge", "ridge": 0.1}):
        model = trainer.fit(rows, specification, config)
        restored = json.loads(json.dumps(model))
        assert v1.predict_rows(restored, rows) == pytest.approx(v1.predict_rows(model, rows))
        assert np.mean((v1.predict_rows(model, rows) - [r["target_sg"] for r in rows]) ** 2) < 0.2
        assert np.isfinite(predict_expected_sg(model, rows[0]["features"]))


def test_exposed_test_can_change_forward_refit_but_never_selection_or_evaluation_model(monkeypatch):
    rows = _rows()
    config = trainer.protocol()
    config["candidates"] = config["candidates"][:2]
    monkeypatch.setattr(trainer, "protocol", lambda: config)
    monkeypatch.setattr(trainer, "clean_history", lambda *args: ({"rounds": []}, {}))
    monkeypatch.setattr(v1, "build_dataset", lambda *args, **kwargs: (rows, {}, [[], []]))
    monkeypatch.setattr(v1, "attach_baseline", lambda *args: None)
    first = trainer.train({}, {"source_sha256": "same-source"}, as_of="2026-10-16", progress=lambda *args, **kwargs: None)
    altered = deepcopy(rows)
    for row in altered:
        if row["year"] == 2026:
            row["target_sg"] += 3
            row["finish"] = 21 - row["finish"]
    monkeypatch.setattr(v1, "build_dataset", lambda *args, **kwargs: (altered, {}, [[], []]))
    second = trainer.train({}, {"source_sha256": "same-source"}, as_of="2026-10-16", progress=lambda *args, **kwargs: None)
    assert first[1]["hash"] == second[1]["hash"]
    assert first[0]["selection"] == second[0]["selection"]
    assert first[4]["hash"] != second[4]["hash"]
    assert first[0]["protocol"]["test_status"] == "exposed_retrospective_2026_identity_integrity_repair"
    assert first[0]["market_evidence"]["roi_pct"] is None and not first[0]["promotion"]["eligible"]
    assert all(f["fit_through"] < f["forecast_start"] for f in first[0]["diagnostics"]["calibration_folds"])


def test_weekly_seed_is_required_and_report_path_override_is_forwarded(tmp_path, monkeypatch, capsys):
    from scripts import weekly_learning_refresh as weekly

    calls = []
    monkeypatch.setattr(weekly, "train_main", lambda args: calls.append(args) or 0)
    assert weekly.main([], root=tmp_path, db_path="/tmp/live-golf.sqlite") == 2
    assert json.loads(capsys.readouterr().out)["state"] == "missing_verified_history_seed"
    assert calls == []
    seed = tmp_path / "data/research/verified-learning-corpus-v2-identity-repair.jsonl.gz"
    seed.parent.mkdir(parents=True)
    seed.write_bytes(b"test only; training call is replaced")
    assert weekly.main(["--public-report", "/tmp/dist/reports/learning-latest.json"], root=tmp_path, db_path="/tmp/live-golf.sqlite") == 0
    assert calls[0][-2:] == ["--public-report", "/tmp/dist/reports/learning-latest.json"]
    assert calls[0][calls[0].index("--protocol") + 1] == "recovered-v2"
    artifact_root = Path(calls[0][calls[0].index("--output") + 1])
    assert artifact_root.is_relative_to(tmp_path / "data" / "research")
    assert not artifact_root.is_relative_to(tmp_path / "output")


def test_freshness_does_not_claim_learning_when_no_completed_events_arrived(tmp_path):
    from scripts.train_learning_challenger import source_freshness

    prior = tmp_path / "previous"
    prior.mkdir()
    (prior / "forward-model.json").write_text(json.dumps({"training_event_ids": ["2025:1"]}))
    (tmp_path / "latest.json").write_text(json.dumps({"run_id": "previous"}))
    same = source_freshness(tmp_path, {"training_event_ids": ["2025:1"], "trained_through": "2025-01-05"})
    assert same["state"] == "no_new_completed_events" and same["new_completed_events"] == 0
    newer = source_freshness(tmp_path, {"training_event_ids": ["2025:1", "2025:2"], "trained_through": "2025-01-12"})
    assert newer["state"] == "new_completed_events" and newer["event_ids"] == ["2025:2"]
