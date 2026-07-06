"""Tests for event results acquisition in the grading pipeline."""

from __future__ import annotations

from unittest.mock import patch

from src import db
from src.event_pick_freeze import freeze_completed_event_picks
from src.event_results import acquire_event_results


def test_acquire_event_results_uses_dg_api(tmp_db):
    tournament_id = db.get_or_create_tournament("John Deere Classic", year=2026, event_id="30")
    fake_results = [
        {
            "player_key": "scottie_scheffler",
            "player_display": "Scottie Scheffler",
            "finish_position": 1,
            "finish_text": "1",
            "made_cut": 1,
        }
    ]

    with patch("src.event_results.fetch_event_results", return_value=fake_results):
        summary = acquire_event_results("30", 2026, tournament_id=tournament_id)

    assert summary["status"] == "ok"
    assert summary["source"] == "dg_api"
    conn = db.get_conn()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM results WHERE tournament_id = ?",
            (tournament_id,),
        ).fetchone()["c"]
    finally:
        conn.close()
    assert int(count) == 1


def test_acquire_event_results_falls_back_to_rounds(tmp_db):
    tournament_id = db.get_or_create_tournament("John Deere Classic", year=2026, event_id="30")

    with patch("src.event_results.fetch_event_results", return_value=[]):
        with patch(
            "src.event_results.auto_ingest_results",
            return_value={"status": "ok", "results_stored": 3, "players": 3},
        ):
            summary = acquire_event_results("30", 2026, tournament_id=tournament_id)

    assert summary["status"] == "ok"
    assert summary["source"] == "rounds"


def test_acquire_event_results_returns_no_data_when_both_missing(tmp_db):
    tournament_id = db.get_or_create_tournament("Future Open", year=2026, event_id="99")

    with patch("src.event_results.fetch_event_results", return_value=[]):
        with patch(
            "src.event_results.auto_ingest_results",
            return_value={"status": "no_data", "results_stored": 0},
        ):
            summary = acquire_event_results("99", 2026, tournament_id=tournament_id)

    assert summary["status"] == "no_data"


def test_freeze_completed_event_picks_acquires_results_before_awaiting(tmp_db, monkeypatch):
    event_id = "30"
    year = 2026
    tournament_id = db.get_or_create_tournament("John Deere Classic", year=year, event_id=event_id)
    db.store_picks(
        [
            {
                "tournament_id": tournament_id,
                "model_variant": "v5",
                "source": "cockpit",
                "bet_type": "top20",
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "opponent_key": "",
                "opponent_display": "",
                "model_prob": 0.2,
                "market_odds": "+400",
                "market_book": "draftkings",
                "market_implied_prob": 0.15,
                "ev": 0.05,
            }
        ]
    )

    monkeypatch.setattr("src.event_pick_freeze._inventory_exists", lambda _event_id: (1, 1))
    monkeypatch.setattr(
        "src.event_pick_freeze.backfill_completed_market_rows_into_picks",
        lambda *_args, **_kwargs: 0,
    )

    def _fake_acquire(_event_id, _year, *, tournament_id):
        db.store_results(
            tournament_id,
            [
                {
                    "player_key": "scottie_scheffler",
                    "player_display": "Scottie Scheffler",
                    "finish_position": 1,
                    "finish_text": "1",
                    "made_cut": 1,
                }
            ],
        )
        return {"status": "ok", "source": "dg_api", "results_stored": 1}

    monkeypatch.setattr("src.event_results.acquire_event_results", _fake_acquire)
    monkeypatch.setattr(
        "scripts.grade_tournament.grade_tournament",
        lambda *_args, **_kwargs: {"status": "complete"},
    )

    report = freeze_completed_event_picks(event_id, year=year, event_name="John Deere Classic")

    assert report["status"] == "complete"
