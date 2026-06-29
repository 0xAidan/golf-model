"""Analytics API contract tests."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app import app
from src.pick_ledger import compute_pick_key, persist_pick_ledger_rows


def _insert_graded_pick(
    conn: sqlite3.Connection,
    *,
    tournament_id: int,
    event_id: str,
    pick_id: int,
    source: str = "cockpit",
    bet_type: str = "matchup",
    book: str = "draftkings",
    ev: float = 0.08,
    hit: int = 1,
    profit: float = 0.91,
) -> None:
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
            opponent_key, opponent_display, market_odds, market_book, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pick_id,
            tournament_id,
            "baseline",
            source,
            bet_type,
            f"player_{pick_id}",
            f"Player {pick_id}",
            f"opp_{pick_id}",
            f"Opp {pick_id}",
            "-110",
            book,
            0.55,
            ev,
        ),
    )
    conn.execute(
        """INSERT INTO pick_outcomes (pick_id, hit, profit, odds_decimal, stake, entered_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (pick_id, hit, profit, 1.91, 1.0, "2026-06-01 10:00:00"),
    )
    conn.execute(
        "UPDATE tournaments SET event_id = ? WHERE id = ?",
        (event_id, tournament_id),
    )


def test_analytics_picks_excludes_pit_reconstructed_by_default(tmp_db, sample_tournament):
    """Ledger-only pit rows are not surfaced once analytics reads graded picks."""
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


def test_analytics_summary_uses_graded_picks_and_book_aliases(tmp_db, sample_tournament):
    db_mod, tid = sample_tournament
    conn = sqlite3.connect(db_mod.DB_PATH)
    _insert_graded_pick(conn, tournament_id=tid, event_id="34", pick_id=1, book="DraftKings", ev=0.06)
    _insert_graded_pick(conn, tournament_id=tid, event_id="34", pick_id=2, book="bet365", ev=0.12)
    conn.commit()
    conn.close()

    client = TestClient(app)
    resp = client.get(
        "/api/analytics/summary?event_id=34&lane=cockpit&bet_type=matchup&book=dk&ev_min=0.05",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pick_count"] == 1
    assert body["graded_count"] == 1
    assert body["wins"] == 1
    assert body["profit_units"] == 0.91


def test_analytics_rollup_groups_by_event(tmp_db, sample_tournament):
    db_mod, tid = sample_tournament
    conn = sqlite3.connect(db_mod.DB_PATH)
    _insert_graded_pick(conn, tournament_id=tid, event_id="34", pick_id=10, profit=1.5)
    _insert_graded_pick(conn, tournament_id=tid, event_id="34", pick_id=11, hit=0, profit=-1.0)
    conn.commit()
    conn.close()

    client = TestClient(app)
    resp = client.get("/api/analytics/picks/rollup?group_by=event&season=2026&lane=cockpit")
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["group_key"] == "34"
    assert float(rows[0]["profit"]) == 0.5
