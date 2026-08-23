"""Versioned mutable strategy-config artifact (the loop's ONLY writable surface).

Schema v2 of autoresearch/strategy_config.json:

    {
      "schema_version": 2,
      "name": "autoresearch_candidate",
      "overrides": { ...flat StrategyConfig override fields... },
      "ranges":   { "<field>": {"min": x, "max": y, "step": s} },   # declared mutation space
      "segments": { "<segment_key>": { ...subset of overrides... } }
    }

The v1 flat layout ({name, w_sub_form, min_ev, ...}) is auto-migrated on load.
Validation is strict: unknown keys, out-of-range values, and undeclared segment
keys are rejected with ConfigArtifactError (a ValueError subclass).
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backtester.strategy import StrategyConfig
from backtester.theory_engine import ALLOWED_OVERRIDE_FIELDS

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_CONFIG_ARTIFACT_PATH = ROOT / "autoresearch" / "strategy_config.json"

SCHEMA_VERSION = 2

# Numeric bounds mirror the Optuna search space in research_lab/param_space.py
# plus the safety ranges enforced by autoresearch_config._validate_strategy_overrides.
DEFAULT_RANGES: dict[str, dict[str, float]] = {
    "w_sub_course_fit": {"min": 0.0, "max": 1.0},
    "w_sub_form": {"min": 0.0, "max": 1.0},
    "w_sub_momentum": {"min": 0.0, "max": 1.0},
    "min_ev": {"min": 0.02, "max": 0.18},
    "max_implied_prob": {"min": 0.20, "max": 0.65},
    "min_model_prob": {"min": 0.001, "max": 0.05},
    "kelly_fraction": {"min": 0.05, "max": 0.45},
    "softmax_temp": {"min": 0.4, "max": 2.5},
    "matchup_ev_threshold": {"min": 0.05, "max": 0.12},
    "platt_a": {"min": -0.12, "max": -0.02},
    "platt_b": {"min": -0.20, "max": 0.20},
    "min_composite_gap": {"min": 0.0, "max": 10.0},
    "max_win_prob_cap": {"min": 0.65, "max": 0.90},
    "dg_matchup_blend_weight": {"min": 0.50, "max": 0.95},
}

# Declared segment axes. Segment keys must be "<axis>=<value>".
SEGMENT_AXES = ("course_type", "golfer_type", "momentum_regime")
_SEGMENT_FIELDS_ALLOWED = set(DEFAULT_RANGES) | {"matchup_include_all_books"}


class ConfigArtifactError(ValueError):
    """Raised when the strategy-config artifact is missing, malformed, or invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigArtifactError(f"Missing strategy-config artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigArtifactError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigArtifactError("strategy config artifact must be a JSON object")
    return payload


def migrate_flat_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a v1 flat artifact into the v2 envelope."""
    overrides: dict[str, Any] = {}
    migrated = {
        "schema_version": SCHEMA_VERSION,
        "name": payload.get("name", "autoresearch_candidate"),
        "overrides": overrides,
        "ranges": {},
        "segments": {},
    }
    for key, value in payload.items():
        if key in ("name", "schema_version", "overrides", "ranges", "segments"):
            continue
        overrides[key] = value
    return migrated


def load_strategy_artifact(path: Path | None = None) -> dict[str, Any]:
    """Load + validate the strategy-config artifact; migrates v1 transparently."""
    target = path or STRATEGY_CONFIG_ARTIFACT_PATH
    payload = _read_json(target)
    if payload.get("schema_version") != SCHEMA_VERSION:
        payload = migrate_flat_to_v2(payload)
        payload["schema_version"] = SCHEMA_VERSION
    validate_artifact_payload(payload)
    return payload


def save_strategy_artifact(payload: dict[str, Any], path: Path | None = None) -> None:
    """Validate then atomically write the artifact."""
    validate_artifact_payload(payload)
    target = path or STRATEGY_CONFIG_ARTIFACT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)


def validate_artifact_payload(payload: dict[str, Any]) -> None:
    """Strict validation of a v2 artifact payload (raises ConfigArtifactError)."""
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ConfigArtifactError(f"schema_version must be {SCHEMA_VERSION}")

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigArtifactError("name must be a non-empty string")

    overrides = payload.get("overrides")
    if not isinstance(overrides, dict):
        raise ConfigArtifactError("overrides must be an object")

    unknown = sorted(k for k in overrides if k not in ALLOWED_OVERRIDE_FIELDS)
    if unknown:
        raise ConfigArtifactError(f"Unknown override keys: {unknown}")
    _validate_override_values(overrides)

    ranges = payload.get("ranges") or {}
    if not isinstance(ranges, dict):
        raise ConfigArtifactError("ranges must be an object when present")
    for field_name, bounds in ranges.items():
        if field_name not in DEFAULT_RANGES:
            raise ConfigArtifactError(f"Undeclared range field: {field_name}")
        if not isinstance(bounds, dict) or "min" not in bounds or "max" not in bounds:
            raise ConfigArtifactError(f"Range for {field_name} needs min and max")
        lo, hi = float(bounds["min"]), float(bounds["max"])
        declared = DEFAULT_RANGES[field_name]
        if lo < declared["min"] or hi > declared["max"] or lo >= hi:
            raise ConfigArtifactError(
                f"Range for {field_name} must satisfy "
                f"{declared['min']} <= min < max <= {declared['max']}"
            )
        value = overrides.get(field_name)
        if value is not None and not (lo <= float(value) <= hi):
            raise ConfigArtifactError(
                f"{field_name}={value} outside declared range [{lo}, {hi}]"
            )

    segments = payload.get("segments") or {}
    if not isinstance(segments, dict):
        raise ConfigArtifactError("segments must be an object when present")
    for seg_key, seg_overrides in segments.items():
        axis = str(seg_key).split("=", 1)[0]
        if axis not in SEGMENT_AXES:
            raise ConfigArtifactError(
                f"Segment key '{seg_key}' must use one of axes {SEGMENT_AXES}"
            )
        if not isinstance(seg_overrides, dict):
            raise ConfigArtifactError(f"Segment '{seg_key}' must map to an object")
        bad = sorted(k for k in seg_overrides if k not in _SEGMENT_FIELDS_ALLOWED)
        if bad:
            raise ConfigArtifactError(f"Segment '{seg_key}' has non-tunable keys: {bad}")
        _validate_override_values(seg_overrides, context=f"segment '{seg_key}'")


def _validate_override_values(values: dict[str, Any], *, context: str = "overrides") -> None:
    for key, value in values.items():
        if not isinstance(value, (int, float, bool)):
            raise ConfigArtifactError(f"{context}.{key} must be numeric/bool")
        if key.startswith("w_") and not (0.0 <= float(value) <= 1.0):
            raise ConfigArtifactError(f"{context}.{key} must be in [0, 1]")
        numeric_bounds = DEFAULT_RANGES.get(key)
        if numeric_bounds and not (
            numeric_bounds["min"] <= float(value) <= numeric_bounds["max"]
        ):
            raise ConfigArtifactError(
                f"{context}.{key}={value} outside allowed bounds "
                f"[{numeric_bounds['min']}, {numeric_bounds['max']}]"
            )


# ---------------------------------------------------------------------------
# Hashing / diffing
# ---------------------------------------------------------------------------


def artifact_hash(payload: dict[str, Any]) -> str:
    """Stable hash over name+overrides+ranges+segments (excludes schema_version)."""
    import hashlib

    material = {
        "name": payload.get("name"),
        "overrides": payload.get("overrides") or {},
        "ranges": payload.get("ranges") or {},
        "segments": payload.get("segments") or {},
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def diff_artifacts(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """Human-readable change list between two artifacts (for promote modals)."""
    changes: list[dict[str, Any]] = []
    old_ov = old.get("overrides") or {}
    new_ov = new.get("overrides") or {}

    def _record(scope: str, key: str, before: Any, after: Any) -> None:
        changes.append({"scope": scope, "field": key, "from": before, "to": after})

    for key in sorted(set(old_ov) | set(new_ov)):
        before, after = old_ov.get(key), new_ov.get(key)
        if before != after:
            _record("global", key, before, after)

    segments_old = old.get("segments") or {}
    segments_new = new.get("segments") or {}
    for seg in sorted(set(segments_old) | set(segments_new)):
        seg_a = segments_old.get(seg) or {}
        seg_b = segments_new.get(seg) or {}
        for key in sorted(set(seg_a) | set(seg_b)):
            before, after = seg_a.get(key), seg_b.get(key)
            if before != after:
                _record(f"segment:{seg}", key, before, after)

    return changes


def build_strategy_from_artifact(
    payload: dict[str, Any],
    baseline: StrategyConfig,
    *,
    segment: str | None = None,
) -> StrategyConfig:
    """Materialize a StrategyConfig from the artifact (optionally with one segment's overrides)."""
    values = asdict(baseline)
    values.update(payload.get("overrides") or {})
    if segment:
        seg_overrides = (payload.get("segments") or {}).get(segment)
        if seg_overrides:
            values.update(seg_overrides)
    return StrategyConfig(**values)


def default_ranges() -> dict[str, dict[str, float]]:
    """Fresh deep copy of DEFAULT_RANGES (safe to embed into artifacts)."""
    return copy.deepcopy(DEFAULT_RANGES)
