"""Provider identities, dated fields and immutable weekly inputs cannot borrow history."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import sqlite3

import pytest

from backtester import learning_challenger as v1
from backtester import learning_challenger_v2 as v2
from backtester.learning_corpus import add_snapshot_references, deduplicate, preserve_training_snapshot
from scripts.train_learning_challenger import current_field_input
from src.models.learning_challenger import FEATURE_NAMES, player_features_v2, provider_player_key, rank_players


def _round(dg_id=6986, alias="zach_johnson", event="prior", number=1, value=1, **updates):
    return {"tour": "pga", "dg_id": dg_id, "player_key": alias, "player_name": alias,
            "event_id": event, "year": 2025, "round_num": number, "course_num": 1,
            "event_completed": "2025-01-05", "sg_total": value, "score": 70,
            "sg_ott": 0.1, "sg_app": 0.5, "sg_arg": 0.1, "sg_putt": 0.3,
            "fin_text": "1", **updates}


def test_corpus_preserves_provider_identity_and_original_aliases_without_id_equivalence():
    original = _round()
    alias = {**original, "player_key": "zach_hunter_johnson", "_source_refs": [{"origin": "b"}]}
    other_player = _round(17619, value=-9)
    other_tour = {**original, "tour": "liv", "sg_total": 20}
    tables, source = deduplicate({"rounds": [original, alias, other_player, other_tour, {**original, "dg_id": None}]}, [])
    rows = tables["rounds"]
    assert {r["provider_player_key"] for r in rows} == {"pga:datagolf:6986", "pga:datagolf:17619", "liv:datagolf:6986"}
    retained = next(r for r in rows if r["provider_player_key"] == "pga:datagolf:6986")
    assert {a["player_key"] for a in retained["_source_aliases"]} == {"zach_johnson", "zach_hunter_johnson"}
    assert original["player_key"] == "zach_johnson" and "_source_aliases" not in original
    assert source["deduplication"]["missing_provider_identity_rounds_excluded"] == 1
    assert deduplicate(tables, [])[0] == tables


def test_temporal_targets_and_history_are_grouped_by_provider_not_name():
    rounds = []
    for player in range(20):
        dg_id = 6986 if player == 0 else player
        alias = "zach_johnson" if player == 0 else f"player_{player}"
        for number in range(1, 9):
            rounds.append(_round(dg_id, alias if number <= 4 else alias + "_old", number=number))
        rounds.append(_round(dg_id, alias, event="target", value=player, event_completed="2025-10-05", fin_text=str(player + 1)))
    rounds += [_round(17619, number=number, value=-9) for number in (1, 2)]
    rounds.append(_round(17619, event="target", value=-10, event_completed="2025-10-05", fin_text="CUT"))
    calendar = [{"tour": "pga", "event_id": "target", "year": 2025, "start_date": "2025-10-02", "event_name": "Identity Open"}]
    dataset, exclusions, _ = v1.build_dataset({"rounds": rounds, "historical_event_info": calendar}, "2025-10-10")
    assert len(dataset) == 20
    zach = next(row for row in dataset if row["dg_id"] == 6986)
    assert zach["player_key"] == zach["provider_player_key"] == "pga:datagolf:6986"
    assert zach["history_rounds"] == 8 and zach["naive_sg"] == 1 and zach["target_sg"] == 0
    assert set(zach["player_aliases"]) == {"zach_johnson", "zach_johnson_old"}
    assert not any(row["dg_id"] == 17619 for row in dataset)
    assert exclusions["insufficient_prior_rounds"] >= 1
    with pytest.raises(ValueError, match="single tour/DataGolf"):
        player_features_v2(rounds, as_of="2025-10-10")


def _model():
    return {"feature_names": list(FEATURE_NAMES), "feature_mean": [0.0] * len(FEATURE_NAMES),
            "feature_scale": [1.0] * len(FEATURE_NAMES), "coefficients": [1.0] + [0.0] * (len(FEATURE_NAMES) - 1),
            "intercept": 0.0, "minimum_history_rounds": 8}


def test_current_field_withholds_ambiguous_alias_and_does_not_borrow_covered_namesake_history():
    history = [_round(number=number) for number in range(1, 9)] + [_round(17619, number=number, value=-9) for number in (1, 2)]
    diagnostics = {}
    assert rank_players(_model(), history, [{"player_key": "zach_johnson"}], as_of="2025-10-10", diagnostics=diagnostics) == []
    assert diagnostics["withheld"][0]["reason"] == "ambiguous_alias_missing_provider_id"
    ranks = rank_players(_model(), history, [{"player_key": "zach_johnson", "dg_id": 6986}], as_of="2025-10-10")
    assert len(ranks) == 1 and ranks[0]["provider_player_key"] == "pga:datagolf:6986" and ranks[0]["history_rounds"] == 8
    assert rank_players(_model(), history, [{"player_key": "zach_johnson", "dg_id": 17619}], as_of="2025-10-10") == []
    assert rank_players(_model(), history, [{"player_key": "zach_johnson", "dg_id": 6986}, {"player_key": "zach_johnson", "dg_id": 17619}], as_of="2025-10-10") == []
    assert provider_player_key({"tour": "pga", "dg_id": 6986, "datagolf_id": 17619}) is None


def test_projection_uses_dated_tour_year_and_never_maximum_calendar_year():
    calendar = [{"tour": "pga", "event_id": "1", "year": year, "start_date": f"{year}-10-22", "course_id": course}
                for year, course in ((2025, 1), (2026, 2), (2027, 999))]
    snapshot = {"generated_at": "2026-10-16T01:00:00Z", "upcoming_tournament": {
        "source_event_id": "1", "rankings": [{"player_key": "p"}],
        "eligibility": {"verified": True, "observed_tour": "pga", "field_event_id": "1", "failed_invariants": []}}}
    current = current_field_input({"historical_event_info": calendar}, snapshot, "2026-10-16")
    assert current["state"] == "resolved" and current["year"] == 2026 and current["tour"] == "pga" and current["course_num"] == "2"
    ambiguous = calendar + [{**calendar[1], "start_date": "2026-10-29"}]
    assert current_field_input({"historical_event_info": ambiguous}, snapshot, "2026-10-16")["players"] == []
    old = deepcopy(snapshot)
    old["generated_at"] = "2025-10-16T01:00:00Z"
    assert current_field_input({"historical_event_info": calendar}, old, "2026-10-16")["players"] == []
    snapshot["upcoming_tournament"]["year"] = 2027
    assert current_field_input({"historical_event_info": calendar}, snapshot, "2026-10-16")["players"] == []


@pytest.mark.parametrize("section_update,eligibility_update,reason", [
    ({}, {"observed_tour": "liv"}, "unsupported_or_missing_tour_identity"),
    ({"tour": "pga"}, {"observed_tour": "liv"}, "contradictory_tour_identity"),
    ({"tour": "liv"}, {}, "contradictory_tour_identity"),
    ({}, {"observed_tour": None}, "unsupported_or_missing_tour_identity"),
    ({}, {"verified": False}, "unverified_event_field"),
    ({}, {"verified": "true"}, "unverified_event_field"),
    ({}, {"failed_invariants": ["field_event_mismatch"]}, "failed_field_invariants"),
    ({}, {"failed_invariants": "unknown"}, "failed_field_invariants"),
    ({}, {"field_event_id": "other"}, "unverified_field_event_identity"),
    ({}, {"field_event_id": None}, "unverified_field_event_identity"),
    ({"verification_error": "unverified"}, {}, "unverified_event_field"),
    ({"active": False}, {}, "unverified_event_field"),
])
def test_projection_requires_consistent_tour_and_verified_event_field(section_update, eligibility_update, reason):
    calendar = [{"tour": "pga", "event_id": "1", "year": 2026, "start_date": "2026-10-22", "course_id": 2}]
    eligibility = {"verified": True, "observed_tour": "pga", "field_event_id": "1", "failed_invariants": [], **eligibility_update}
    section = {"source_event_id": "1", "rankings": [{"player_key": "p"}], "eligibility": eligibility, **section_update}
    field = current_field_input({"historical_event_info": calendar}, {"generated_at": "2026-10-16", "upcoming_tournament": section}, "2026-10-16")
    assert field["players"] == [] and field["state"] == "withheld" and field["reason"] == reason


def test_projection_accepts_explicit_tour_without_observed_tour_but_never_without_verification():
    calendar = [{"tour": "pga", "event_id": "1", "year": 2026, "start_date": "2026-10-22", "course_id": 2}]
    section = {"source_event_id": "1", "tour": "pga", "rankings": [{"player_key": "p"}],
               "eligibility": {"verified": True, "field_event_id": "1"}}
    snapshot = {"generated_at": "2026-10-16", "upcoming_tournament": section}
    assert current_field_input({"historical_event_info": calendar}, snapshot, "2026-10-16")["state"] == "resolved"
    section.pop("eligibility")
    assert current_field_input({"historical_event_info": calendar}, snapshot, "2026-10-16")["players"] == []


def test_mutable_sqlite_training_input_is_replayable_after_correction(tmp_path):
    path = tmp_path / "weekly.sqlite"
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE rounds(tour TEXT,dg_id INTEGER,player_key TEXT,event_id TEXT,year INTEGER,round_num INTEGER,sg_total REAL,event_completed TEXT)")
    writer.execute("INSERT INTO rounds VALUES('pga',6986,'zach_johnson','1',2025,1,1.25,'2025-01-05')")
    writer.execute("CREATE TABLE historical_event_info(tour TEXT,event_id TEXT,year INTEGER,start_date TEXT)")
    writer.execute("INSERT INTO historical_event_info VALUES('pga','1',2025,'2025-01-02')")
    writer.commit()
    tables, source = v1.load_source(path, include_quotes=False)
    original_row = dict(tables["rounds"][0])
    add_snapshot_references(tables, source)
    reference = tables["rounds"][0]["_source_refs"][0]
    assert reference["row_sha256"] == hashlib.sha256(json.dumps(original_row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    tables, source = deduplicate(tables, [source])
    preserved = preserve_training_snapshot(tmp_path / "output", tables, source)
    writer.execute("UPDATE rounds SET sg_total=99")
    writer.commit()
    restored, _ = v1.load_source(preserved["path"], include_quotes=False)
    assert restored["rounds"] == tables["rounds"] and restored["rounds"][0]["sg_total"] == 1.25
    assert preserve_training_snapshot(tmp_path / "output", tables, source) == preserved
    assert preserved["readback_verified"] is True
    writer.close()


def test_repair_keeps_candidate_grid_and_fingerprints_admission_dependencies():
    original = json.loads((v2.ROOT / "config/learning-protocols/recovered-rounds-v2.json").read_text())
    repaired = v2.protocol()
    for field in ("candidates", "train_start", "validation_start", "test_start", "bootstrap"):
        assert repaired[field] == original[field]
    assert repaired["parent_protocol_hash"] == "239b49279de7a5a2074202150a4c522f33b8659fdf9b58e399b1ac1d58481194"
    fingerprints = v2.fingerprint()
    for path in ("backtester/sealed_holdout.py", "docs/research/sealed_holdout_events.json", "src/event_format.py"):
        assert fingerprints[path] == hashlib.sha256((v2.ROOT / path).read_bytes()).hexdigest()
