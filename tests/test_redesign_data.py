"""Tests for redesign read-only data endpoints (terminal overhaul R1)."""

from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture()
def redesign_router():
    module = importlib.import_module("src.routes.redesign_data")
    return module.router


def _run(coro):
    return asyncio.run(coro)


def test_router_mounted(redesign_router):
    paths = {route.path for route in redesign_router.routes}
    assert "/api/redesign/player/{player_key}/betting-record" in paths
    assert "/api/redesign/player/{player_key}/market-history" in paths
    assert "/api/redesign/player/{player_key}/course-dna" in paths
    assert "/api/redesign/player/{player_key}/hole-heat" in paths
    assert "/api/redesign/compare" in paths


def test_betting_record_empty_player(tmp_db, monkeypatch):
    """Unknown player returns a well-formed zero payload, never raises."""
    from src.routes import redesign_data as module

    payload = _run(module.player_betting_record("nobody-here"))

    assert payload["player_key"] == "nobody-here"
    assert payload["total_picks"] == 0
    assert payload["graded_picks"] == 0
    assert payload["hit_rate"] is None
    assert payload["units_profit"] == 0
    assert payload["recent"] == []


def test_safe_query_swallows_schema_errors(monkeypatch):
    """A broken table reference degrades to [] (migration-safety contract)."""
    from src.routes import redesign_data as module

    class BoomConn:
        def execute(self, *_args, **_kwargs):
            raise module.sqlite3.OperationalError("no such column: missing_col")

        def close(self):
            return None

    monkeypatch.setattr(module.db, "get_conn", lambda: BoomConn())
    assert module._safe_query("SELECT missing_col FROM picks") == []


def test_market_history_shape(tmp_db, monkeypatch):
    from src.routes import redesign_data as module

    payload = _run(module.player_market_history("ghost", days=30))
    assert payload["window_days"] == 30
    assert isinstance(payload["daily"], list)
    assert set(payload["totals"]) == {"rows_seen", "value_flags", "best_ev"}


def test_hole_heat_honest_empty(tmp_db, monkeypatch):
    """No hole data -> available=False with an explanation note."""
    from src.routes import redesign_data as module

    payload = _run(module.player_hole_heat("ghost"))
    assert payload["available"] is False
    assert payload["holes"] == []
    assert payload["note"] is not None


def test_compare_payload_structure(tmp_db, monkeypatch):
    from src.routes import redesign_data as module

    payload = _run(module.pairwise_compare(a="x", b="y"))
    assert payload["a"]["player_key"] == "x"
    assert payload["b"]["player_key"] == "y"
    assert {"graded", "a_wins", "b_wins"} <= set(payload["head_to_head"])
