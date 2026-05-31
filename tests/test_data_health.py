"""Tests for data health audit and analytics views."""

from __future__ import annotations

import json
import os

import pytest

from src.data_health import build_data_health_report
from src.data_views import ensure_analytics_views


def test_build_data_health_report_empty_db(tmp_db):
    report = build_data_health_report(db_path=tmp_db.DB_PATH, year=2026)
    assert report["status"] in ("green", "yellow", "red")
    assert "monthly_coverage" in report
    assert report["row_counts"]["picks"] == 0


def test_data_health_with_picks(sample_tournament, tmp_db):
    db_mod, tid = sample_tournament
    db_mod.store_picks([
        {
            "tournament_id": tid,
            "model_variant": "baseline",
            "source": "cockpit",
            "bet_type": "top10",
            "player_key": "scottie_scheffler",
            "player_display": "Scottie Scheffler",
            "opponent_key": "",
            "opponent_display": "",
            "composite_score": 1.0,
            "course_fit_score": 0.5,
            "form_score": 0.5,
            "momentum_score": 0.0,
            "model_prob": 0.12,
            "market_odds": "+1200",
            "market_book": "draftkings",
            "market_implied_prob": 0.08,
            "ev": 0.04,
            "confidence": "low",
            "reasoning": "test",
        }
    ])
    report = build_data_health_report(db_path=tmp_db.DB_PATH, year=2026)
    assert report["row_counts"]["picks"] >= 1
    assert report["live_picks_coverage"]["tournaments_with_picks"] >= 1


def test_analytics_views_queryable(tmp_db, sample_tournament):
    db_mod, tid = sample_tournament
    ensure_analytics_views()
    conn = db_mod.get_conn()
    row = conn.execute(
        "SELECT pick_count FROM v_tournament_data_health WHERE tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert row is not None


def test_prune_then_vacuum(tmp_db):
    import src.db as db

    conn = db.get_conn()
    conn.execute(
        """
        INSERT INTO market_prediction_rows
        (snapshot_id, generated_at, tour, section, event_id, event_name,
         market_family, market_type, player_key, payload_json)
        VALUES ('old', '2020-01-01T00:00:00', 'pga', 'live', 'e1', 'E1',
                'matchup', 'matchup', 'a', '{}')
        """
    )
    conn.commit()
    conn.close()
    deleted = db.prune_market_prediction_rows(30)
    assert deleted >= 1
    result = db.vacuum_database()
    assert result["ok"] is True


def test_regression_fixture_db_exists():
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "fixtures",
        "golf_2026_one_event.db",
    )
    if not os.path.isfile(path):
        pytest.skip("Run scripts/build_regression_fixture_db.py to create fixture")
    report = build_data_health_report(db_path=path, year=2026)
    assert report["row_counts"]["picks"] >= 1
