"""Tests for unified strategy resolution (CLI / web / service parity)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester.strategy import StrategyConfig
from src.strategy_resolution import (
    build_pipeline_strategy_config,
    map_strategy_to_runtime_settings,
    resolve_runtime_strategy,
)


def test_resolve_prefers_live_over_research(monkeypatch):
    import src.strategy_resolution as sr

    live_s = StrategyConfig(name="live_x", min_ev=0.06)
    research_s = StrategyConfig(name="research_y", min_ev=0.07)

    monkeypatch.setattr(
        sr,
        "get_live_weekly_model_record",
        lambda scope="global": {"id": 1, "strategy_config_json": live_s.to_json()},
    )
    monkeypatch.setattr(
        sr,
        "get_research_champion_record",
        lambda scope="global": {"id": 2, "strategy_config_json": research_s.to_json()},
    )
    monkeypatch.setattr(sr, "get_active_strategy", lambda scope="global": None)

    s, meta = resolve_runtime_strategy("global")
    assert s.name == "live_x"
    assert meta["strategy_source"] == "live"


def test_resolve_falls_through_to_research_when_no_live(monkeypatch):
    import src.strategy_resolution as sr

    research_s = StrategyConfig(name="research_only", min_ev=0.07)

    monkeypatch.setattr(sr, "get_live_weekly_model_record", lambda scope="global": None)
    monkeypatch.setattr(
        sr,
        "get_research_champion_record",
        lambda scope="global": {"id": 2, "strategy_config_json": research_s.to_json()},
    )
    monkeypatch.setattr(sr, "get_active_strategy", lambda scope="global": None)

    s, meta = resolve_runtime_strategy("global")
    assert s.name == "research_only"
    assert meta["strategy_source"] == "research_champion"


def test_build_pipeline_strategy_config_includes_sub_weights():
    s = StrategyConfig(
        name="t",
        w_sub_course_fit=0.35,
        w_sub_form=0.45,
        w_sub_momentum=0.20,
        min_ev=0.08,
    )
    cfg = build_pipeline_strategy_config(s)
    assert cfg["weights"]["course_fit"] == pytest.approx(0.35)
    assert cfg["w_sub_course_fit"] == pytest.approx(0.35)
    assert cfg["ev_threshold"] == pytest.approx(0.08)


def test_map_strategy_to_runtime_settings_blend_matches_weights():
    s = StrategyConfig(w_sub_course_fit=0.5, w_sub_form=0.3, w_sub_momentum=0.2, min_ev=0.05)
    rt = map_strategy_to_runtime_settings(s)
    assert rt["blend_weights"]["course_fit"] == pytest.approx(0.5)
    assert rt["ev_threshold"] == pytest.approx(0.05)


def test_map_strategy_to_runtime_settings_keeps_matchup_threshold():
    s = StrategyConfig(
        w_sub_course_fit=0.45,
        w_sub_form=0.45,
        w_sub_momentum=0.10,
        min_ev=0.08,
        matchup_ev_threshold=0.05,
    )

    rt = map_strategy_to_runtime_settings(s)

    assert rt["matchup_ev_threshold"] == pytest.approx(0.05)
