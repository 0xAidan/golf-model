"""Tests for shadow Monte Carlo v2 and rounds SG fit."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.prob_engine_v1.contextual import build_shadow_contextual_meta
from src.models.prob_engine_v1.rounds_sg import fit_player_round_sg
from src.models.prob_engine_v1.shadow_dispatch import run_shadow_field_simulation
from src.models.prob_engine_v1.shadow_mc_v2 import (
    ENGINE_VERSION_V2,
    run_field_simulation_v2,
)


def test_v2_outright_probabilities_sum_to_one():
    field = [(f"p{i}", 75.0 - i * 0.05) for i in range(50)]
    out = run_field_simulation_v2(
        field,
        n_sims=600,
        base_score_noise=2.0,
        field_correlation=0.1,
        cut_keep_frac=0.6,
        rankings_for_context=[{"composite": 80.0, "weather_adjustment": 0.1, "course_fit": 1.0, "form": 0.5}],
        seed=99,
    )
    assert out["engine_version"] == ENGINE_VERSION_V2
    total = sum(v["p_outright"] for v in out["player_summary"].values())
    assert abs(total - 1.0) < 1e-5


def test_v2_make_cut_fraction_reasonable():
    field = [(f"p{i}", 70.0 + i * 0.01) for i in range(40)]
    out = run_field_simulation_v2(
        field,
        n_sims=400,
        base_score_noise=1.5,
        cut_keep_frac=0.55,
        seed=3,
    )
    p_mc = [v["p_make_cut"] for v in out["player_summary"].values()]
    assert max(p_mc) <= 1.0 + 1e-9
    assert min(p_mc) >= 0.0


def test_fit_player_round_sg_default_without_rows(tmp_db):
    out = fit_player_round_sg(["unknown_player_xyz"])
    assert out["unknown_player_xyz"]["source"] == "default"
    assert out["unknown_player_xyz"]["sd_sg"] == pytest.approx(2.5)


def test_fit_player_round_sg_with_data(tmp_db):
    rows = []
    for r in range(1, 8):
        rows.append(
            {
                "dg_id": 9000 + r,
                "player_name": "Test Golfer",
                "player_key": "test_golfer_fit",
                "tour": "pga",
                "season": 2026,
                "year": 2026,
                "event_id": f"evt{r}",
                "event_name": "T",
                "event_completed": f"2026-01-{r:02d}",
                "course_name": "C",
                "course_num": 1,
                "course_par": 72,
                "round_num": 1,
                "score": 70,
                "sg_total": 0.5 + (r % 3) * 0.2,
                "sg_ott": 0.1,
                "sg_app": 0.1,
                "sg_arg": 0.0,
                "sg_putt": 0.0,
                "sg_t2g": 0.2,
                "driving_dist": None,
                "driving_acc": None,
                "gir": None,
                "scrambling": None,
                "prox_fw": None,
                "prox_rgh": None,
                "great_shots": None,
                "poor_shots": None,
                "birdies": None,
                "pars": None,
                "bogies": None,
                "doubles_or_worse": None,
                "eagles_or_better": None,
                "fin_text": None,
                "teetime": None,
                "start_hole": None,
            }
        )
    tmp_db.store_rounds(rows)
    out = fit_player_round_sg(["test_golfer_fit"], lookback_rounds=10)
    assert out["test_golfer_fit"]["source"] == "rounds"
    assert out["test_golfer_fit"]["n"] >= 2


def test_contextual_meta_handles_empty():
    assert build_shadow_contextual_meta([]) == {}


def test_dispatch_uses_v2_when_flag(monkeypatch):
    monkeypatch.setattr(
        "src.models.prob_engine_v1.shadow_mc_v2.is_shadow_monte_carlo_v2_enabled",
        lambda: True,
    )
    field = [("a", 80.0), ("b", 79.0)]
    out = run_shadow_field_simulation(field, [], seed=1)
    assert "p_make_cut" in next(iter(out["player_summary"].values()))
