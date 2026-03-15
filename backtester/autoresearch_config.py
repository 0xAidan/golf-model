"""Autoresearch configuration and contract validation helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from backtester.strategy import StrategyConfig
from backtester.theory_engine import ALLOWED_OVERRIDE_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PILOT_CONTRACT_PATH = ROOT / "docs" / "autoresearch" / "pilot_contract.json"
EVALUATION_CONTRACT_PATH = ROOT / "docs" / "autoresearch" / "evaluation_contract.md"
PROGRAM_PATH = ROOT / "program.md"
STRATEGY_CONFIG_PATH = ROOT / "autoresearch" / "strategy_config.json"

REQUIRED_DOC_MARKERS = {
    "evaluation_contract.md": [
        "Editable Surface",
        "Primary Objective",
        "Output Contract",
        "Promotion Gate Dependency",
    ],
    "program.md": [
        "Scope",
        "Immutable Evaluator Rule",
        "Objective",
        "Loop Protocol",
        "Promotion Rule",
    ],
}


class ContractValidationError(ValueError):
    """Raised when an autoresearch contract or config is invalid."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractValidationError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"Invalid JSON in {path}: {exc}") from exc


def validate_contract_documents() -> None:
    for name, path in {
        "evaluation_contract.md": EVALUATION_CONTRACT_PATH,
        "program.md": PROGRAM_PATH,
    }.items():
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in REQUIRED_DOC_MARKERS[name] if marker not in text]
        if missing:
            raise ContractValidationError(f"{name} missing required sections: {missing}")


def load_pilot_contract() -> dict[str, Any]:
    contract = _read_json(PILOT_CONTRACT_PATH)
    _validate_pilot_contract(contract)
    return contract


def _validate_pilot_contract(contract: dict[str, Any]) -> None:
    required_top_level = [
        "pilot_contract_version",
        "evaluation_contract_version",
        "score_formula_version",
        "guardrail_version",
        "anchor_policy",
        "checkpoint_set_id",
        "checkpoints",
        "benchmark",
        "resolved_event",
    ]
    missing = [key for key in required_top_level if key not in contract]
    if missing:
        raise ContractValidationError(f"pilot_contract missing required keys: {missing}")

    if contract["anchor_policy"] != "recent_signature_event":
        raise ContractValidationError("anchor_policy must be 'recent_signature_event'")

    allowed_versions = {1}
    for key in ("pilot_contract_version", "evaluation_contract_version", "score_formula_version", "guardrail_version"):
        if contract.get(key) not in allowed_versions:
            raise ContractValidationError(f"{key} must be one of {sorted(allowed_versions)}")

    checkpoints = contract.get("checkpoints")
    if not isinstance(checkpoints, list) or len(checkpoints) != 3:
        raise ContractValidationError("checkpoints must contain exactly 3 entries")

    ids = [c.get("id") for c in checkpoints]
    if ids != ["pre_tournament", "before_day_2", "before_day_3"]:
        raise ContractValidationError("checkpoint ids must be [pre_tournament, before_day_2, before_day_3]")

    offsets = [c.get("offset_days_from_start") for c in checkpoints]
    if offsets != sorted(offsets):
        raise ContractValidationError("checkpoint offsets must be sorted ascending")

    benchmark = contract.get("benchmark") or {}
    years = benchmark.get("years")
    if not isinstance(years, list) or not years:
        raise ContractValidationError("benchmark.years must be a non-empty list")


def resolve_checkpoint_dates(start_date_iso: str, contract: dict[str, Any]) -> list[dict[str, str]]:
    start = date.fromisoformat(start_date_iso)
    checkpoints: list[dict[str, str]] = []
    for checkpoint in contract["checkpoints"]:
        offset = int(checkpoint["offset_days_from_start"])
        as_of = start + timedelta(days=offset)
        checkpoints.append(
            {
                "id": checkpoint["id"],
                "label": checkpoint.get("label", checkpoint["id"]),
                "as_of_date": as_of.isoformat(),
            }
        )
    return checkpoints


def load_strategy_overrides(path: Path | None = None) -> dict[str, Any]:
    target = path or STRATEGY_CONFIG_PATH
    payload = _read_json(target)
    if not isinstance(payload, dict):
        raise ContractValidationError("strategy config must be a JSON object")
    _validate_strategy_overrides(payload)
    return payload


def _validate_strategy_overrides(payload: dict[str, Any]) -> None:
    unknown = sorted([key for key in payload if key not in ALLOWED_OVERRIDE_FIELDS and key != "name"])
    if unknown:
        raise ContractValidationError(f"Unknown strategy keys: {unknown}")

    for key, value in payload.items():
        if key == "name":
            if not isinstance(value, str) or not value.strip():
                raise ContractValidationError("name must be a non-empty string")
            continue

        if not isinstance(value, (int, float, bool)):
            raise ContractValidationError(f"{key} must be numeric/bool")

        if key.startswith("w_") and not (0.0 <= float(value) <= 1.0):
            raise ContractValidationError(f"{key} must be in [0, 1]")
        if key == "min_ev" and not (0.0 <= float(value) <= 1.0):
            raise ContractValidationError("min_ev must be in [0, 1]")
        if key == "max_implied_prob" and not (0.0 < float(value) <= 1.0):
            raise ContractValidationError("max_implied_prob must be in (0, 1]")
        if key == "min_model_prob" and not (0.0 <= float(value) <= 1.0):
            raise ContractValidationError("min_model_prob must be in [0, 1]")
        if key == "kelly_fraction" and not (0.0 < float(value) <= 1.0):
            raise ContractValidationError("kelly_fraction must be in (0, 1]")
        if key == "softmax_temp" and not (0.1 <= float(value) <= 50.0):
            raise ContractValidationError("softmax_temp must be in [0.1, 50.0]")
        if key == "stat_window" and int(value) <= 0:
            raise ContractValidationError("stat_window must be positive")


def build_strategy_from_overrides(overrides: dict[str, Any], baseline: StrategyConfig) -> StrategyConfig:
    values = asdict(baseline)
    values.update(overrides)
    return StrategyConfig(**values)


def strategy_hash(overrides: dict[str, Any]) -> str:
    return _sha256_text(json.dumps(overrides, sort_keys=True))

