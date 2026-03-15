import json
from pathlib import Path

import pytest

from backtester.autoresearch_config import ContractValidationError, load_pilot_contract


def test_pilot_contract_loads_and_has_required_shape():
    contract = load_pilot_contract()
    assert contract["pilot_contract_version"] == 1
    assert contract["evaluation_contract_version"] == 1
    assert [c["id"] for c in contract["checkpoints"]] == [
        "pre_tournament",
        "before_day_2",
        "before_day_3",
    ]


def test_pilot_contract_invalid_checkpoint_order_raises(tmp_path, monkeypatch):
    bad = {
        "pilot_contract_version": 1,
        "evaluation_contract_version": 1,
        "score_formula_version": 1,
        "guardrail_version": 1,
        "anchor_policy": "recent_signature_event",
        "checkpoint_set_id": "x",
        "resolved_event": {"event_id": None, "year": None, "event_name": None},
        "benchmark": {"years": [2025]},
        "checkpoints": [
            {"id": "pre_tournament", "offset_days_from_start": 2},
            {"id": "before_day_2", "offset_days_from_start": 1},
            {"id": "before_day_3", "offset_days_from_start": 0},
        ],
    }
    p = tmp_path / "pilot_contract.json"
    p.write_text(json.dumps(bad), encoding="utf-8")

    from backtester import autoresearch_config as cfg

    monkeypatch.setattr(cfg, "PILOT_CONTRACT_PATH", Path(p))
    with pytest.raises(ContractValidationError):
        cfg.load_pilot_contract()

