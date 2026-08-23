"""Tests for the versioned strategy-config artifact (schema v2)."""

from __future__ import annotations

import json

import pytest

from backtester.strategy import StrategyConfig
from backtester.strategy_config_artifact import (
    ConfigArtifactError,
    SCHEMA_VERSION,
    artifact_hash,
    build_strategy_from_artifact,
    default_ranges,
    diff_artifacts,
    load_strategy_artifact,
    migrate_flat_to_v2,
    save_strategy_artifact,
    validate_artifact_payload,
)


def _v2_payload(**overrides) -> dict:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "name": "candidate",
        "overrides": {"min_ev": 0.05, "kelly_fraction": 0.25},
        "ranges": {"min_ev": {"min": 0.02, "max": 0.18}},
        "segments": {},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_migrate_flat_v1_to_v2():
    flat = {
        "name": "autoresearch_candidate",
        "w_sub_course_fit": 0.4,
        "w_sub_form": 0.4,
        "w_sub_momentum": 0.2,
        "min_ev": 0.05,
        "use_weather": True,
    }
    migrated = migrate_flat_to_v2(flat)
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert migrated["overrides"]["w_sub_form"] == 0.4
    assert migrated["overrides"]["use_weather"] is True
    assert "min_ev" not in migrated["ranges"]
    assert migrated["name"] == "autoresearch_candidate"


def test_load_migrates_flat_file(tmp_path):
    target = tmp_path / "strategy_config.json"
    target.write_text(json.dumps({"name": "legacy", "min_ev": 0.05}))
    payload = load_strategy_artifact(target)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["overrides"]["min_ev"] == 0.05


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_accepts_committed_artifact():
    from backtester.strategy_config_artifact import STRATEGY_CONFIG_ARTIFACT_PATH

    payload = load_strategy_artifact(STRATEGY_CONFIG_ARTIFACT_PATH)
    assert payload["schema_version"] == SCHEMA_VERSION


def test_validate_rejects_unknown_override_key():
    payload = _v2_payload()
    payload["overrides"]["mystery_knob"] = 1.5
    with pytest.raises(ConfigArtifactError, match="Unknown override keys"):
        validate_artifact_payload(payload)


def test_validate_rejects_out_of_bounds_value():
    payload = _v2_payload()
    payload["overrides"]["kelly_fraction"] = 3.0
    with pytest.raises(ConfigArtifactError, match="outside allowed bounds"):
        validate_artifact_payload(payload)


def test_validate_rejects_undeclared_range_field():
    payload = _v2_payload()
    payload["ranges"]["not_a_field"] = {"min": 0.0, "max": 1.0}
    with pytest.raises(ConfigArtifactError, match="Undeclared range field"):
        validate_artifact_payload(payload)


def test_validate_rejects_range_wider_than_allowed():
    payload = _v2_payload()
    # min_ev hard bounds are [0.02, 0.18]; declaring [0.0, 0.9] must fail.
    payload["ranges"]["min_ev"] = {"min": 0.0, "max": 0.9}
    with pytest.raises(ConfigArtifactError, match="Range for min_ev"):
        validate_artifact_payload(payload)


def test_validate_rejects_value_outside_declared_range():
    payload = _v2_payload()
    payload["overrides"]["min_ev"] = 0.10
    payload["ranges"]["min_ev"] = {"min": 0.02, "max": 0.08}
    with pytest.raises(ConfigArtifactError, match="outside declared range"):
        validate_artifact_payload(payload)


def test_validate_rejects_bad_segment_axis():
    payload = _v2_payload()
    payload["segments"] = {"weather=windy": {"min_ev": 0.06}}
    with pytest.raises(ConfigArtifactError, match="must use one of axes"):
        validate_artifact_payload(payload)


def test_validate_rejects_non_tunable_segment_key():
    payload = _v2_payload()
    payload["segments"] = {"course_type=coastal": {"name": "nope"}}
    with pytest.raises(ConfigArtifactError, match="non-tunable keys"):
        validate_artifact_payload(payload)


def test_validate_accepts_valid_segment():
    payload = _v2_payload()
    payload["segments"] = {"momentum_regime=hot": {"matchup_ev_threshold": 0.08}}
    validate_artifact_payload(payload)


# ---------------------------------------------------------------------------
# Hashing / diffing / materialization
# ---------------------------------------------------------------------------


def test_artifact_hash_stable_and_sensitive():
    a = artifact_hash(_v2_payload())
    b = artifact_hash(_v2_payload())
    assert a == b
    changed = _v2_payload()
    changed["overrides"]["min_ev"] = 0.06
    assert artifact_hash(changed) != a


def test_diff_artifacts_reports_global_and_segment_changes():
    old = _v2_payload()
    new = _v2_payload()
    new["overrides"]["min_ev"] = 0.08
    new["overrides"]["new_field_dropped"] = 1  # will be stripped by diff? no: raw compare
    changes = diff_artifacts(old, new)
    fields = {(c["scope"], c["field"]) for c in changes}
    assert ("global", "min_ev") in fields

    seg_old = _v2_payload()
    seg_new = _v2_payload()
    seg_new["segments"] = {"golfer_type=elite": {"platt_b": 0.1}}
    changes = diff_artifacts(seg_old, seg_new)
    assert any(c["scope"] == "segment:golfer_type=elite" and c["field"] == "platt_b" for c in changes)


def test_build_strategy_applies_overrides_and_segment():
    baseline = StrategyConfig(name="base")
    payload = _v2_payload()
    payload["overrides"] = {"min_ev": 0.09}
    payload["segments"] = {"course_type=links": {"matchup_ev_threshold": 0.11}}

    plain = build_strategy_from_artifact(payload, baseline)
    assert plain.min_ev == 0.09
    assert plain.matchup_ev_threshold == baseline.matchup_ev_threshold

    links = build_strategy_from_artifact(payload, baseline, segment="course_type=links")
    assert links.matchup_ev_threshold == 0.11


def test_save_and_roundtrip(tmp_path):
    target = tmp_path / "artifact.json"
    payload = _v2_payload(name="roundtrip")
    save_strategy_artifact(payload, target)
    loaded = load_strategy_artifact(target)
    assert loaded["name"] == "roundtrip"
    assert artifact_hash(loaded) == artifact_hash(payload)
    assert default_ranges()["min_ev"]["max"] == 0.18
