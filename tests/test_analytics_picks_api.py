"""Analytics API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import app
from src import db
from src.pick_ledger import compute_pick_key, persist_pick_ledger_rows


def test_analytics_picks_excludes_pit_reconstructed_by_default(tmp_db, sample_tournament):
    _, tid = sample_tournament
    pk = compute_pick_key(
        event_id="99",
        lane="cockpit",
        section="upcoming",
        phase="pre_tournament",
        bet_type="matchup",
        player_key="a",
        opponent_key="b",
        book="dk",
        odds="+100",
        snapshot_id="pit1",
    )
    persist_pick_ledger_rows([
        {
            "pick_key": pk,
            "event_id": "99",
            "event_name": "Test",
            "tournament_id": tid,
            "year": 2026,
            "phase": "pre_tournament",
            "section": "upcoming",
            "lane": "cockpit",
            "lifecycle": "pit_reconstructed",
            "bet_type": "matchup",
            "market_family": "matchup",
            "market_type": "matchup",
            "player_key": "a",
            "player_display": "A",
            "opponent_key": "b",
            "opponent_display": "B",
            "book": "dk",
            "odds": "+100",
            "ev": 0.1,
            "is_value": 1,
            "model_variant": "baseline",
            "snapshot_id": "pit1",
            "generated_at": "2026-06-01T00:00:00+00:00",
            "source_origin": "pit_reconstructed",
            "payload_json": "{}",
        }
    ])

    client = TestClient(app)
    resp = client.get("/api/analytics/picks?event_id=99")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
