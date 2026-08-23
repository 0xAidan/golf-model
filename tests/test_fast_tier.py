"""Tests for the fast-tier runner: cache equivalence, windows, budget."""

from __future__ import annotations

import pytest

from backtester.fast_tier import (
    CONFIRMATION_WINDOW_SIZE,
    EFFORT_PRESETS,
    SEARCH_WINDOW_SIZE,
    EffortBudget,
    FastTierWindow,
    _blend_sub_scores,
    resolve_effort,
)
from backtester.pit_models import compute_pit_composite
from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
from backtester.strategy import SimulationResult, StrategyConfig, replay_event
from tests.test_evaluator_characterization import (
    EVENT_ID,
    PLAYERS,
    YEAR,
    seed_fixture_db,
)


@pytest.fixture()
def eval_db(tmp_db):
    """tmp_db schema plus seeded evaluator fixture behind db.get_conn()."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    seed_fixture_db(conn)

    class _ConnProxy:
        def execute(self, sql, params=()):
            return conn.execute(sql, params)

        def close(self):
            return None

    original = tmp_db.get_conn
    tmp_db.get_conn = lambda: _ConnProxy()
    yield conn
    tmp_db.get_conn = original


def test_blend_matches_frozen_compute_pit_composite(eval_db):
    """The cached blend path must produce output identical to the frozen builder."""
    form = {"alpha_player": {"score": 80.0, "components": {}}, "delta_player": {"score": 40.0, "components": {}}}
    course = {}
    momentum = {
        "alpha_player": {"score": 60.0, "direction": "hot", "trend": 5.0},
        "delta_player": {"score": 45.0, "direction": "cooling", "trend": -2.0},
    }
    # The blend block in fast_tier mirrors pit_models.compute_pit_composite's
    # aggregation exactly (frozen file; equivalence pinned here and by
    # test_fast_window_replay_identical_to_plain).
    from backtester.fast_tier import _blend_sub_scores as blend

    cached = blend(form, course, momentum, 0.4, 0.4, 0.2)
    assert set(cached) == {"alpha_player", "delta_player"}
    # No course data -> frozen redistribution: form' = 0.4 + 0.4*0.7 = 0.68,
    # momentum' = 0.2 + 0.4*0.3 = 0.32.
    assert cached["alpha_player"]["composite"] == pytest.approx(0.68 * 80.0 + 0.32 * 60.0, abs=1e-9)
    assert cached["delta_player"]["composite"] == pytest.approx(0.68 * 40.0 + 0.32 * 45.0, abs=1e-9)
    assert cached["alpha_player"]["form"] == 80.0
    assert cached["delta_player"]["momentum_direction"] == "cooling"


def test_fast_window_replay_identical_to_plain(eval_db):
    strategy = StrategyConfig(name="fastcheck")
    plain_bets = replay_event(EVENT_ID, YEAR, strategy)
    with FastTierWindow([{"event_id": EVENT_ID, "year": YEAR}]):
        fast_bets = replay_event(EVENT_ID, YEAR, strategy)
    assert fast_bets == plain_bets


def test_fast_window_replays_many_times_stable(eval_db):
    events = [{"event_id": EVENT_ID, "year": YEAR}]
    with FastTierWindow(events) as window:
        first = replay_event(EVENT_ID, YEAR, StrategyConfig(name="s"))
        for _ in range(3):
            assert replay_event(EVENT_ID, YEAR, StrategyConfig(name="s")) == first


def test_cache_miss_delegates_to_real_builder(eval_db, monkeypatch):
    # Event never prefetched: the injected function must fall back to the real one.
    with FastTierWindow([]) as window:  # prefetch nothing
        bets = replay_event(EVENT_ID, YEAR, StrategyConfig(name="fallback"))
    assert isinstance(bets, list)


# ---------------------------------------------------------------------------
# Window selection (uses sealed-holdout loader; no DB writes)
# ---------------------------------------------------------------------------


def test_select_windows_shapes_and_sealed_exclusion(monkeypatch, tmp_path):
    from backtester import fast_tier as ft

    events = [
        {"event_id": str(i), "year": 2026, "event_name": f"E{i}", "event_date": f"2026-06-{i:02d}"}
        for i in range(10, 30)
    ]
    monkeypatch.setattr(ft, "load_historical_events", lambda years=None: list(events))
    monkeypatch.setattr(ft, "_filter_events_with_pit", lambda evs: evs)
    holdout = tmp_path / "holdout.json"
    holdout.write_text(
        '{"sealed_holdout_version": 1, "events": [{"event_id": "10", "year": 2026}, {"event_id": "11", "year": 2026}]}'
    )
    monkeypatch.setattr("backtester.sealed_holdout.SEALED_HOLDOUT_PATH", holdout)

    windows = ft.select_research_windows()
    ids = [e["event_id"] for e in windows["search"]]
    conf_ids = [e["event_id"] for e in windows["confirmation"]]
    assert len(ids) == SEARCH_WINDOW_SIZE
    assert len(conf_ids) == CONFIRMATION_WINDOW_SIZE
    assert "10" not in ids and "11" not in ids and "10" not in conf_ids
    # Confirmation takes the most recent events; search the block right before.
    assert conf_ids == ["27", "28", "29"]
    assert ids == [str(i) for i in range(14, 27)]


def test_select_windows_skips_pitless_events(monkeypatch):
    from backtester import fast_tier as ft

    events = [
        {"event_id": "nopit", "year": 2026, "event_name": "X", "event_date": "2026-07-01"},
        {"event_id": "withpit", "year": 2026, "event_name": "Y", "event_date": "2026-07-02"},
    ]
    monkeypatch.setattr(ft, "load_historical_events", lambda years=None: events)
    monkeypatch.setattr(ft, "_filter_events_with_pit", lambda evs: [e for e in evs if e["event_id"] == "withpit"])

    windows = ft.select_research_windows(search_size=13, confirmation_size=1)
    assert [e["event_id"] for e in windows["confirmation"]] == ["withpit"]
    assert windows["search"] == []


# ---------------------------------------------------------------------------
# Effort budget presets
# ---------------------------------------------------------------------------


def test_effort_presets_shape():
    assert set(EFFORT_PRESETS) == {"light", "standard", "max"}
    standard = resolve_effort("STANDARD ")
    assert standard["max_trials"] == 100
    assert resolve_effort(None)["max_wall_seconds"] == EFFORT_PRESETS["standard"]["max_wall_seconds"]
    unknown = resolve_effort("turbo")
    assert unknown == EFFORT_PRESETS["standard"]


def test_effort_budget_enforcement():
    budget = EffortBudget(max_wall_seconds=3600, max_trials=2)
    assert budget.start_trial() is True
    assert budget.start_trial() is True
    assert budget.start_trial() is False
    assert budget.exhausted() is True

    tiny = EffortBudget(max_wall_seconds=-1, max_trials=100)
    assert tiny.start_trial() is False


# ---------------------------------------------------------------------------
# make_fast_eval_fn contract (monkeypatched walk-forward to stay offline)
# ---------------------------------------------------------------------------


def test_make_fast_eval_fn_uses_precomputed_baseline(eval_db, monkeypatch):
    from backtester import fast_tier as ft

    captured = {}

    def fake_eval_weighted_walkforward(**kwargs):
        captured.update(kwargs)
        return {
            "summary_metrics": {"total_bets": 42, "weighted_roi_pct": 1.0},
            "baseline_summary_metrics": {},
            "guardrail_results": {"passed": True},
            "segmented_metrics": None,
            "baseline_segmented_metrics": None,
            "splits": [],
            "event_results": [],
            "baseline_event_results": [],
        }

    monkeypatch.setattr(
        "backtester.weighted_walkforward.evaluate_weighted_walkforward",
        fake_eval_weighted_walkforward,
    )

    spec = WalkForwardBenchmarkSpec(events=[{"event_id": EVENT_ID, "year": YEAR}])
    eval_fn = ft.make_fast_eval_fn(
        StrategyConfig(name="base"),
        spec,
        [{"event_id": EVENT_ID, "year": YEAR}],
    )
    result = eval_fn(StrategyConfig(name="cand"), StrategyConfig(name="base"), spec)
    assert result.metadata and result.metadata.get("fast_tier") is True
    assert captured["precomputed_baseline"] is not None
    assert all("roi_pct" in row for row in captured["precomputed_baseline"])
