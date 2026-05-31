"""Regression test against committed fixture DB."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_FIXTURE_DB = _REPO / "tests" / "fixtures" / "golf_2026_one_event.db"
_FIXTURE_META = _FIXTURE_DB.with_suffix(".db.json")

pytestmark = pytest.mark.integration


@pytest.fixture
def fixture_db(monkeypatch):
    if not _FIXTURE_DB.is_file():
        pytest.skip("Missing tests/fixtures/golf_2026_one_event.db — run build_regression_fixture_db.py")
    import src.db as db

    original_path = db.DB_PATH
    original_init = db._DB_INITIALIZED
    db.DB_PATH = str(_FIXTURE_DB)
    db._DB_INITIALIZED = False
    db.ensure_initialized()
    with open(_FIXTURE_META, encoding="utf-8") as f:
        meta = json.load(f)
    yield db, meta
    db.DB_PATH = original_path
    db._DB_INITIALIZED = original_init


def test_fixture_picks_stable(fixture_db):
    db_mod, meta = fixture_db
    tid = meta["tournament_id"]
    conn = db_mod.get_conn()
    rows = conn.execute(
        "SELECT player_key, model_prob, ev FROM picks WHERE tournament_id = ?",
        (tid,),
    ).fetchall()
    conn.close()
    assert len(rows) >= 1
    assert rows[0]["player_key"] == "player_alpha"
    assert float(rows[0]["model_prob"]) == pytest.approx(0.58, abs=0.01)


def test_fixture_composite_runs(fixture_db, monkeypatch):
    """Recompute composite on fixture field — pipeline seam stays importable."""
    db_mod, meta = fixture_db
    tid = meta["tournament_id"]
    conn = db_mod.get_conn()
    keys = [
        r["player_key"]
        for r in conn.execute(
            "SELECT DISTINCT player_key FROM metrics WHERE tournament_id = ?",
            (tid,),
        ).fetchall()
    ]
    conn.close()
    assert len(keys) >= 2

    from src.models.composite import compute_composite

    composite = compute_composite(tid)
    assert len(composite) >= 2
    scores = {row["player_key"]: row["composite"] for row in composite}
    assert scores["player_alpha"] > scores["player_gamma"]
