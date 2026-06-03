"""Lab champion config and live matchup runtime wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtester.strategy import StrategyConfig
from src import lab_champion
from src.matchup_value import _find_matchup_value_bets_core, _tier_meets_floor


def test_lab_champion_bundle_loads_trial_327():
    strategy = lab_champion.load_lab_champion_strategy()
    assert strategy.name == "lab_matchup_champion_trial_327"
    assert strategy.model_variant == "v5"
    assert strategy.matchup_ev_threshold == 0.03
    assert strategy.platt_a == -0.1
    assert strategy.min_composite_gap == 1.5
    pipeline = lab_champion.build_lab_pipeline_config(strategy)
    assert pipeline["lab_champion_id"] == "optuna_trial_327"
    assert "sg_weights" in pipeline
    assert pipeline["matchup_filters"]["tier_floor"] == "STRONG"


def test_tier_floor_filter():
    assert _tier_meets_floor("STRONG", "STRONG")
    assert not _tier_meets_floor("GOOD", "STRONG")


def test_matchup_runtime_applies_min_composite_gap():
    composite = [
        {"player_key": "a", "player_display": "A", "composite": 50.1, "form": 50, "momentum": 50, "course_fit": 50},
        {"player_key": "b", "player_display": "B", "composite": 50.0, "form": 50, "momentum": 50, "course_fit": 50},
    ]
    odds = [
        {
            "p1_player_name": "A",
            "p2_player_name": "B",
            "p1_odds": -110,
            "p2_odds": -110,
            "book": "draftkings",
        }
    ]
    _, all_bets, diag = _find_matchup_value_bets_core(
        composite,
        odds,
        ev_threshold=0.0,
        model_variant="v5",
        matchup_runtime={"min_composite_gap": 5.0, "platt_a": -0.1, "platt_b": 0.0},
    )
    assert len(all_bets) == 0
    assert diag["reason_codes"].get("below_min_composite_gap", 0) >= 1


def test_champion_json_matches_repo_path():
    path = Path(__file__).resolve().parent.parent / "config" / "lab_matchup_champion_trial327.json"
    assert path.is_file()
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert bundle["id"] == "optuna_trial_327"
