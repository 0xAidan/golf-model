"""Tests for champion-challenger rails (defect 3.3.1).

Covers:
  * Evaluation metric functions (Brier, matchup ROI, CLV) on seeded rows.
  * Shadow-prediction hook: empty CHALLENGERS => no writes, rows persist
    when a stub challenger is registered.
  * Byte-identical invariant on the matchup value path with/without a
    challenger (champion card output unchanged in both cases).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest

from src import config
from src.evaluation.champion_challenger import (
    brier_scores,
    clv_summary,
    matchup_roi,
    summarize_all,
)
from src.evaluation.shadow import record_matchup_shadow
from src.models.base import (
    MODELS,
    BaseModel,
    ChampionModel,
    ModelProtocol,
    get_champion,
    iter_active_challengers,
    register_model,
)


class StubChallenger(BaseModel):
    name = "stub_v0"
    version = "0.1"

    def predict_matchup(self, p1, p2, features):
        return 0.42  # deterministic

    def predict_outright(self, player, features):
        return 0.05


class FailingChallenger(BaseModel):
    name = "failing_v0"
    version = "0.0"

    def predict_matchup(self, p1, p2, features):
        raise RuntimeError("boom")

    def predict_outright(self, player, features):
        raise RuntimeError("boom")


@pytest.fixture
def _reset_challengers():
    original = list(config.CHALLENGERS)
    snapshot = dict(MODELS)
    yield
    config.CHALLENGERS = original
    MODELS.clear()
    MODELS.update(snapshot)


def _seed_row(
    db_mod,
    *,
    model_name: str,
    model_version: str = "0.1",
    predicted_p: float,
    champion_p: float | None = 0.5,
    book_price_p1: float | None = 0.5,
    book_price_p2: float | None = 0.5,
    outcome: int | None = 1,
    ts: str | None = None,
):
    conn = db_mod.get_conn()
    conn.execute(
        """
        INSERT INTO challenger_predictions (
            model_name, model_version, market_type, matchup_id,
            tournament_id, p1_key, p2_key, predicted_p, champion_p,
            book_price_p1, book_price_p2, outcome, ts
        ) VALUES (?, ?, 'matchup', 'm1', NULL, 'p1', 'p2', ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))
        """,
        (
            model_name,
            model_version,
            predicted_p,
            champion_p,
            book_price_p1,
            book_price_p2,
            outcome,
            ts,
        ),
    )
    conn.commit()
    conn.close()


# ─── Protocol / registry ────────────────────────────────────────────────────

def test_champion_satisfies_protocol(_reset_challengers):
    champ = get_champion()
    assert isinstance(champ, ChampionModel)
    assert isinstance(champ, ModelProtocol)
    assert champ.name == config.CHAMPION
    assert champ.version == "4.2"


def test_register_and_iterate_active_challengers(_reset_challengers):
    register_model(StubChallenger())
    assert "stub_v0" in MODELS
    config.CHALLENGERS = []
    assert iter_active_challengers() == []
    config.CHALLENGERS = ["stub_v0"]
    active = iter_active_challengers()
    assert len(active) == 1 and active[0].name == "stub_v0"
    # Unknown names are skipped silently.
    config.CHALLENGERS = ["stub_v0", "not_registered"]
    assert [m.name for m in iter_active_challengers()] == ["stub_v0"]


# ─── Evaluation metrics ─────────────────────────────────────────────────────

def test_brier_scores_simple(tmp_db):
    # perfect predictions: brier = 0
    _seed_row(tmp_db, model_name="stub_v0", predicted_p=1.0, outcome=1)
    _seed_row(tmp_db, model_name="stub_v0", predicted_p=0.0, outcome=0)
    # a wrong pred
    _seed_row(tmp_db, model_name="stub_v0", predicted_p=0.5, outcome=1)
    since = datetime.utcnow() - timedelta(days=7)
    result = brier_scores("stub_v0", since)
    assert result["n"] == 3
    assert result["brier"] == pytest.approx((0.0 + 0.0 + 0.25) / 3)


def test_brier_scores_ignores_ungraded(tmp_db):
    _seed_row(tmp_db, model_name="stub_v0", predicted_p=0.6, outcome=None)
    since = datetime.utcnow() - timedelta(days=7)
    result = brier_scores("stub_v0", since)
    assert result["n"] == 0 and result["brier"] is None


def test_matchup_roi_wins_and_losses(tmp_db):
    # Model predicts 0.7 on p1, book p1 = 0.5 (decimal 2.0) → wins bet for +1.0
    _seed_row(
        tmp_db,
        model_name="stub_v0",
        predicted_p=0.7,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=1,
    )
    # Model predicts 0.7 on p1, book p1 = 0.5 → loses (outcome = 0 => -1.0)
    _seed_row(
        tmp_db,
        model_name="stub_v0",
        predicted_p=0.7,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=0,
    )
    since = datetime.utcnow() - timedelta(days=7)
    result = matchup_roi("stub_v0", since)
    assert result["bets"] == 2
    assert result["staked"] == 2.0
    assert result["pnl"] == pytest.approx(0.0)
    assert result["roi_pct"] == pytest.approx(0.0)


def test_matchup_roi_no_edge_no_bet(tmp_db):
    # model_p 0.3 on p1 → bets p2 side with model_side_p 0.7, book p2 = 0.5, wins
    _seed_row(
        tmp_db,
        model_name="stub_v0",
        predicted_p=0.3,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=0,  # p2 wins
    )
    # model_p equals book (no edge) → no bet
    _seed_row(
        tmp_db,
        model_name="stub_v0",
        predicted_p=0.5,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=1,
    )
    since = datetime.utcnow() - timedelta(days=7)
    result = matchup_roi("stub_v0", since)
    assert result["bets"] == 1
    assert result["pnl"] == pytest.approx(1.0)


def test_clv_summary_bps(tmp_db):
    # model 0.6 vs book_p1 0.5 → diff 0.10 → 1000 bps
    _seed_row(
        tmp_db,
        model_name="stub_v0",
        predicted_p=0.6,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=1,
    )
    since = datetime.utcnow() - timedelta(days=7)
    result = clv_summary("stub_v0", since)
    assert result["n"] == 1
    assert result["clv_bps"] == pytest.approx(1000.0)


def test_summarize_all_covers_champion_and_challengers(tmp_db, _reset_challengers):
    register_model(StubChallenger())
    config.CHALLENGERS = ["stub_v0"]
    _seed_row(
        tmp_db,
        model_name=config.CHAMPION,
        predicted_p=0.7,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=1,
    )
    _seed_row(
        tmp_db,
        model_name="stub_v0",
        predicted_p=0.4,
        book_price_p1=0.5,
        book_price_p2=0.5,
        outcome=1,
    )
    result = summarize_all(windows_days=(14, 30))
    names = [m["model_name"] for m in result["models"]]
    assert config.CHAMPION in names
    assert "stub_v0" in names
    assert result["champion"] == config.CHAMPION
    assert result["challengers"] == ["stub_v0"]


# ─── Shadow hook: empty vs populated CHALLENGERS ────────────────────────────

def test_shadow_hook_self_records_champion_when_empty(tmp_db, _reset_challengers):
    """With no challengers configured the champion still self-records so the
    offline evaluator has data. The recorded `predicted_p` equals the
    champion's own probability and `champion_p` matches — i.e. Brier vs the
    champion is zero on each row, which is the correct identity behavior.
    """
    config.CHALLENGERS = []
    record_matchup_shadow(
        p1={"player_key": "a"},
        p2={"player_key": "b"},
        features={"champion_p": 0.6},
        champion_p=0.6,
        tournament_id=None,
        book="dk",
    )
    conn = tmp_db.get_conn()
    rows = conn.execute(
        "SELECT model_name, predicted_p, champion_p FROM challenger_predictions"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["model_name"] == config.CHAMPION
    assert rows[0]["predicted_p"] == pytest.approx(0.6)
    assert rows[0]["champion_p"] == pytest.approx(0.6)


def test_shadow_hook_writes_row_for_each_challenger(tmp_db, _reset_challengers):
    register_model(StubChallenger())
    config.CHALLENGERS = ["stub_v0"]
    record_matchup_shadow(
        p1={"player_key": "a"},
        p2={"player_key": "b"},
        features={"champion_p": 0.55},
        champion_p=0.55,
        tournament_id=None,
        book="dk",
        book_price_p1=0.5,
        book_price_p2=0.5,
    )
    conn = tmp_db.get_conn()
    rows = conn.execute(
        "SELECT model_name, predicted_p, champion_p FROM challenger_predictions "
        "ORDER BY model_name"
    ).fetchall()
    conn.close()
    # Champion self-record + challenger row.
    assert len(rows) == 2
    by_name = {r["model_name"]: r for r in rows}
    assert config.CHAMPION in by_name
    assert "stub_v0" in by_name
    assert by_name["stub_v0"]["predicted_p"] == pytest.approx(0.42)
    assert by_name["stub_v0"]["champion_p"] == pytest.approx(0.55)
    assert by_name[config.CHAMPION]["predicted_p"] == pytest.approx(0.55)
    assert by_name[config.CHAMPION]["champion_p"] == pytest.approx(0.55)


def test_shadow_hook_swallows_challenger_failure(tmp_db, _reset_challengers):
    register_model(StubChallenger())
    register_model(FailingChallenger())
    config.CHALLENGERS = ["stub_v0", "failing_v0"]
    # Must not raise even though one challenger explodes.
    record_matchup_shadow(
        p1={"player_key": "a"},
        p2={"player_key": "b"},
        features={"champion_p": 0.6},
        champion_p=0.6,
        tournament_id=None,
        book="dk",
        book_price_p1=0.5,
        book_price_p2=0.5,
    )
    conn = tmp_db.get_conn()
    rows = conn.execute(
        "SELECT model_name FROM challenger_predictions ORDER BY id"
    ).fetchall()
    conn.close()
    # Champion self-record + stub_v0; failing_v0 is swallowed.
    names = sorted(r["model_name"] for r in rows)
    assert names == sorted([config.CHAMPION, "stub_v0"])


# ─── Byte-identical invariant on matchup value path ─────────────────────────

def _minimal_matchup_fixture():
    """Matchup inputs covering both players with simple composite gaps."""
    composite_results = [
        {
            "player_key": "alice",
            "player_display": "Alice",
            "composite": 70.0,
            "form": 65.0,
            "course_fit": 60.0,
            "momentum": 55.0,
            "momentum_direction": "up",
        },
        {
            "player_key": "bob",
            "player_display": "Bob",
            "composite": 55.0,
            "form": 50.0,
            "course_fit": 55.0,
            "momentum": 45.0,
            "momentum_direction": "flat",
        },
    ]
    matchup_odds = [
        {
            "p1_player_name": "Alice",
            "p2_player_name": "Bob",
            "odds": {
                "draftkings": {"p1": -110, "p2": -110},
            },
        }
    ]
    return composite_results, matchup_odds


def _golden_hash(bets: list[dict], diagnostics: dict) -> str:
    payload = json.dumps(
        {"bets": bets, "diagnostics": diagnostics}, sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_matchup_value_byte_identical_with_empty_challengers(tmp_db, _reset_challengers, monkeypatch):
    from src import matchup_value

    # Block DG calls in tests — force Platt-only path.
    monkeypatch.setattr(
        "src.datagolf.fetch_dg_matchup_all_pairings",
        lambda *a, **k: {},
        raising=False,
    )

    config.CHALLENGERS = []
    composite_results, matchup_odds = _minimal_matchup_fixture()
    bets_a, all_a, diag_a = matchup_value._find_matchup_value_bets_core(
        composite_results,
        matchup_odds,
        ev_threshold=0.01,
        tournament_id=None,
        required_book="draftkings",
    )
    hash_a = _golden_hash(bets_a, diag_a)

    # Running again with a challenger registered but CHALLENGERS still empty
    # must still be byte-identical.
    register_model(StubChallenger())
    bets_b, all_b, diag_b = matchup_value._find_matchup_value_bets_core(
        composite_results,
        matchup_odds,
        ev_threshold=0.01,
        tournament_id=None,
        required_book="draftkings",
    )
    hash_b = _golden_hash(bets_b, diag_b)
    assert hash_a == hash_b


def test_matchup_value_byte_identical_with_active_challenger(tmp_db, _reset_challengers, monkeypatch):
    from src import matchup_value

    monkeypatch.setattr(
        "src.datagolf.fetch_dg_matchup_all_pairings",
        lambda *a, **k: {},
        raising=False,
    )

    config.CHALLENGERS = []
    composite_results, matchup_odds = _minimal_matchup_fixture()
    bets_baseline, _, diag_baseline = matchup_value._find_matchup_value_bets_core(
        composite_results,
        matchup_odds,
        ev_threshold=0.01,
        tournament_id=None,
        required_book="draftkings",
    )
    baseline_hash = _golden_hash(bets_baseline, diag_baseline)

    # Activate the challenger. Champion output must remain byte-identical.
    register_model(StubChallenger())
    config.CHALLENGERS = ["stub_v0"]
    bets_shadow, _, diag_shadow = matchup_value._find_matchup_value_bets_core(
        composite_results,
        matchup_odds,
        ev_threshold=0.01,
        tournament_id=None,
        required_book="draftkings",
    )
    shadow_hash = _golden_hash(bets_shadow, diag_shadow)
    assert shadow_hash == baseline_hash, "Challenger must not alter champion output"

    # AND a row must have been written to challenger_predictions for the
    # registered challenger. The champion also self-records (defect 3.3.1
    # follow-up) so we look up the stub row by name rather than by index.
    conn = tmp_db.get_conn()
    rows = conn.execute(
        "SELECT model_name, predicted_p FROM challenger_predictions"
    ).fetchall()
    conn.close()
    by_name = {r["model_name"]: r for r in rows}
    assert "stub_v0" in by_name
    assert by_name["stub_v0"]["predicted_p"] == pytest.approx(0.42)
