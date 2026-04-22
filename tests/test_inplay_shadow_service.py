"""T6 — tests for the in-play shadow ingest/evaluation glue."""

from __future__ import annotations

import pytest

from src import config


def _sample_prices():
    return [
        {
            "event_id": "E1",
            "round_num": 1,
            "player1": "scottie_scheffler",
            "player2": "rory_mcilroy",
            "book": "draftkings",
            "price1": 1.85,
            "price2": 2.05,
            "hole_num": 9,
            "current_scores": {"scottie_scheffler": -2.0, "rory_mcilroy": 0.0},
        },
        {
            "event_id": "E1",
            "round_num": 1,
            "player1": "xander_schauffele",
            "player2": "viktor_hovland",
            "book": "fanduel",
            "price1": 1.95,
            "price2": 1.95,
            "hole_num": 4,
            "current_scores": {"xander_schauffele": 0.0, "viktor_hovland": 0.0},
        },
    ]


def test_ingest_noop_when_flag_off(tmp_db, monkeypatch):
    monkeypatch.setattr(config, "INPLAY_ROUND_MATCHUPS_SHADOW", False)
    from src.services.inplay_shadow import ingest_inplay_prices

    written = ingest_inplay_prices(_sample_prices())
    assert written == 0

    conn = tmp_db.get_conn()
    try:
        n_prices = conn.execute(
            "SELECT COUNT(*) FROM inplay_round_matchup_prices"
        ).fetchone()[0]
        n_preds = conn.execute(
            "SELECT COUNT(*) FROM inplay_round_matchup_predictions"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n_prices == 0
    assert n_preds == 0


def test_ingest_writes_rows_when_flag_on(tmp_db, monkeypatch):
    monkeypatch.setattr(config, "INPLAY_ROUND_MATCHUPS_SHADOW", True)
    from src.services.inplay_shadow import ingest_inplay_prices

    written = ingest_inplay_prices(_sample_prices())
    assert written == 2

    conn = tmp_db.get_conn()
    try:
        preds = conn.execute(
            "SELECT predicted_p1, kelly_fraction_if_hypothetically FROM inplay_round_matchup_predictions"
        ).fetchall()
    finally:
        conn.close()
    assert len(preds) == 2
    for p1_prob, kf in preds:
        assert 0.0 < p1_prob < 1.0
        assert kf >= 0.0  # shadow-only; never used to place a bet


def test_evaluation_brier_and_roi(monkeypatch):
    from src.evaluation.inplay import brier_score, hypothetical_roi

    preds = [
        {"predicted_p1": 0.9, "outcome_p1": 1.0, "kelly_fraction_if_hypothetically": 0.1,
         "price1": 1.85, "price2": 2.05},
        {"predicted_p1": 0.6, "outcome_p1": 0.0, "kelly_fraction_if_hypothetically": 0.05,
         "price1": 1.70, "price2": 2.20},
        {"predicted_p1": 0.5, "outcome_p1": 0.5, "kelly_fraction_if_hypothetically": 0.0,
         "price1": 1.95, "price2": 1.95},
    ]
    b = brier_score(preds)
    # (0.01 + 0.36 + 0.0) / 3
    assert 0.12 < b < 0.13

    roi = hypothetical_roi(preds)
    assert roi["bets"] == 2  # third row has zero hypothetical kelly
    assert roi["staked"] > 0
