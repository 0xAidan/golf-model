"""Tests for shadow Monte Carlo v1 (offline engine)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.prob_engine_v1 import (
    ENGINE_VERSION,
    is_shadow_monte_carlo_enabled,
    run_field_simulation_v1,
)


def test_engine_version_constant():
    assert "prob_engine" in ENGINE_VERSION


def test_run_field_simulation_outright_sums_to_one():
    field = [(f"p{i}", 75.0 - i * 0.05) for i in range(45)]
    out = run_field_simulation_v1(
        field,
        n_sims=800,
        score_noise=2.0,
        seed=42,
    )
    assert out["n_sims"] == 800
    assert out["field_size"] == 45
    total_win = sum(v["p_outright"] for v in out["player_summary"].values())
    assert abs(total_win - 1.0) < 1e-9


def test_is_any_shadow_respects_v2_flag(monkeypatch):
    monkeypatch.delenv("SHADOW_MC_V1", raising=False)
    monkeypatch.setattr("src.feature_flags.is_enabled", lambda _: False)
    from src.models.prob_engine_v1.shadow_mc import is_any_shadow_monte_carlo_enabled

    assert is_any_shadow_monte_carlo_enabled() is False
    monkeypatch.setattr(
        "src.models.prob_engine_v1.shadow_mc_v2.is_shadow_monte_carlo_v2_enabled",
        lambda: True,
    )
    assert is_any_shadow_monte_carlo_enabled() is True


def test_is_shadow_monte_carlo_env_overrides_flag(monkeypatch):
    monkeypatch.delenv("SHADOW_MC_V1", raising=False)
    monkeypatch.setattr("src.feature_flags.is_enabled", lambda _: False)
    assert is_shadow_monte_carlo_enabled() is False
    monkeypatch.setenv("SHADOW_MC_V1", "1")
    assert is_shadow_monte_carlo_enabled() is True


def test_append_shadow_event_simulation(tmp_db):
    n = tmp_db.append_shadow_event_simulation(
        snapshot_id="snap1",
        event_id="evt123",
        section="upcoming",
        tour="pga",
        n_sims=100,
        engine_version="test",
        payload_json={"k": 1},
    )
    assert n == 1
    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT event_id, section, n_sims FROM shadow_event_simulations WHERE snapshot_id = ?",
        ("snap1",),
    ).fetchone()
    conn.close()
    assert dict(row)["event_id"] == "evt123"
    assert dict(row)["section"] == "upcoming"
    assert dict(row)["n_sims"] == 100
