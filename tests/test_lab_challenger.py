"""Tests for the lab challenger shadow model (engine-scale H-6)."""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_lab_challenger_predicts_valid_probability():
    from src.models.lab_challenger import LabChallengerModel

    model = LabChallengerModel()
    p1 = {"player_key": "a", "composite": 80, "form": 60, "course_fit": 55, "momentum": 1}
    p2 = {"player_key": "b", "composite": 70, "form": 50, "course_fit": 50, "momentum": 0}
    p = model.predict_matchup(p1, p2, {"composite_gap": 10.0})
    assert 0.0 <= p <= 1.0
    # p1 is favored (positive gap) so should be > 0.5
    assert p > 0.5
    # Symmetry: flipping the gap sign flips the favorite
    p_flip = model.predict_matchup(p1, p2, {"composite_gap": -10.0})
    assert p_flip < 0.5


def test_challengers_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LAB_CHALLENGER_SHADOW_ENABLED", raising=False)
    import src.config as config

    importlib.reload(config)
    assert config.CHALLENGERS == []


def test_challenger_activates_with_env(monkeypatch):
    monkeypatch.setenv("LAB_CHALLENGER_SHADOW_ENABLED", "1")
    import src.config as config

    importlib.reload(config)
    assert "lab_trial327" in config.CHALLENGERS

    # iter_active_challengers should lazily register and return the lab model.
    import src.models.base as base

    base.MODELS.pop("lab_trial327", None)
    challengers = base.iter_active_challengers()
    names = [c.name for c in challengers]
    assert "lab_trial327" in names

    # Restore default config for other tests.
    monkeypatch.delenv("LAB_CHALLENGER_SHADOW_ENABLED", raising=False)
    importlib.reload(config)
