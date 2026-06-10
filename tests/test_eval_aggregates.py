"""Tests for per-track eval aggregates (engine-scale Wave 3)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db
from src.eval_aggregates import track_comparison


def _seed_graded_pick(conn, tid, *, source, player, opp, model_prob, hit, odds_decimal, ev=0.08, bet_type="matchup"):
    cur = conn.execute(
        """INSERT INTO picks (tournament_id, model_variant, source, bet_type, player_key,
                              player_display, opponent_key, ev, model_prob, market_odds, market_book, created_at)
           VALUES (?, 'baseline', ?, ?, ?, ?, ?, ?, ?, '-110', 'bet365', datetime('now'))""",
        (tid, source, bet_type, player, player, opp, ev, model_prob),
    )
    pid = cur.lastrowid
    conn.execute(
        "INSERT INTO pick_outcomes (pick_id, hit, profit, odds_decimal) VALUES (?, ?, ?, ?)",
        (pid, hit, (odds_decimal - 1) if hit else -1, odds_decimal),
    )
    return pid


def test_track_comparison_metrics_and_overlap(tmp_db):
    conn = db.get_conn()
    tid = db.get_or_create_tournament("Eval Agg Event", year=2026)
    # Cockpit: 2 picks, 1 win.
    _seed_graded_pick(conn, tid, source="cockpit", player="a", opp="b", model_prob=0.55, hit=1, odds_decimal=2.0)
    _seed_graded_pick(conn, tid, source="cockpit", player="c", opp="d", model_prob=0.40, hit=0, odds_decimal=1.9)
    # Lab: 2 picks, both win; one overlaps cockpit on (a,b,matchup).
    _seed_graded_pick(conn, tid, source="lab_sandbox", player="a", opp="b", model_prob=0.60, hit=1, odds_decimal=2.0)
    _seed_graded_pick(conn, tid, source="lab_sandbox", player="e", opp="f", model_prob=0.58, hit=1, odds_decimal=2.1)
    conn.commit()
    conn.close()

    result = track_comparison(window_days=365)
    cockpit = result["tracks"]["cockpit"]
    lab = result["tracks"]["lab"]
    assert cockpit["n"] == 2
    assert cockpit["wins"] == 1
    assert cockpit["hit_rate_pct"] == 50.0
    assert lab["n"] == 2
    assert lab["hit_rate_pct"] == 100.0
    # 1u ROI: cockpit = (+1.0 -1.0)/2 = 0%, lab = (+1.0 + +1.1)/2 = +105%
    assert cockpit["roi_pct"] == 0.0
    assert lab["roi_pct"] == 105.0
    assert cockpit["brier"] is not None
    assert result["overlap"]["both"] == 1
    assert result["overlap"]["cockpit_only"] == 1
    assert result["overlap"]["lab_only"] == 1
    assert result["data_kind"] == "live_graded"


def test_track_comparison_endpoint(tmp_db):
    import app as app_module
    from fastapi.testclient import TestClient

    client = TestClient(app_module.app)
    resp = client.get("/api/eval/track-comparison?window=30d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "30d"
    assert "tracks" in body and "overlap" in body
