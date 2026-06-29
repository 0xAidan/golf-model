"""Tests for season grading API."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


def test_grading_season_returns_lane_split(monkeypatch, tmp_path):
    import app as app_module
    from src import db as db_module
    from src.pick_ledger import compute_pick_key, persist_pick_ledger_rows

    db_path = tmp_path / "grading_season.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (1, "Season Test Open", "Test Course", 2026, "9001"),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
            opponent_key, opponent_display, market_odds, market_book, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "baseline", "cockpit", "matchup", "dash_player", "Dash Player", "dash_opp", "Dash Opp", "-110", "fanduel", 0.55, 0.05),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
            opponent_key, opponent_display, market_odds, market_book, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (2, 1, "v5", "lab_sandbox", "matchup", "lab_player", "Lab Player", "lab_opp", "Lab Opp", "+120", "draftkings", 0.52, 0.04),
    )
    conn.execute(
        """INSERT INTO pick_outcomes (pick_id, hit, profit, odds_decimal, stake, entered_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, 1, 0.91, 1.91, 1.0, "2026-06-01 10:00:00"),
    )
    conn.execute(
        """INSERT INTO pick_outcomes (pick_id, hit, profit, odds_decimal, stake, entered_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (2, 0, -1.0, 2.2, 1.0, "2026-06-01 10:00:00"),
    )
    conn.commit()
    conn.close()

    persist_pick_ledger_rows([
        {
            "pick_key": compute_pick_key(
                event_id="9001",
                lane="cockpit",
                section="upcoming",
                phase="pre_tournament",
                bet_type="matchup",
                player_key="dash_player",
                opponent_key="dash_opp",
                book="fanduel",
                odds="-110",
            ),
            "event_id": "9001",
            "event_name": "Season Test Open",
            "tournament_id": 1,
            "year": 2026,
            "lane": "cockpit",
            "lifecycle": "graded",
            "bet_type": "matchup",
            "player_key": "dash_player",
            "player_display": "Dash Player",
            "opponent_key": "dash_opp",
            "opponent_display": "Dash Opp",
            "book": "fanduel",
            "odds": "-110",
            "model_variant": "baseline",
            "ev": 0.05,
            "is_value": 1,
            "source_origin": "test",
            "generated_at": "2026-06-01T10:00:00+00:00",
        },
        {
            "pick_key": compute_pick_key(
                event_id="9001",
                lane="lab",
                section="lab_upcoming",
                phase="pre_tournament",
                bet_type="matchup",
                player_key="lab_player",
                opponent_key="lab_opp",
                book="draftkings",
                odds="+120",
            ),
            "event_id": "9001",
            "event_name": "Season Test Open",
            "tournament_id": 1,
            "year": 2026,
            "lane": "lab",
            "lifecycle": "graded",
            "bet_type": "matchup",
            "player_key": "lab_player",
            "player_display": "Lab Player",
            "opponent_key": "lab_opp",
            "opponent_display": "Lab Opp",
            "book": "draftkings",
            "odds": "+120",
            "model_variant": "v5",
            "ev": 0.04,
            "is_value": 1,
            "source_origin": "test",
            "generated_at": "2026-06-01T10:00:00+00:00",
        },
    ])

    client = TestClient(app_module.app)
    response = client.get("/api/grading/season?year=2026")
    assert response.status_code == 200
    payload = response.json()
    event = next((row for row in payload["events"] if row["event_id"] == "9001"), None)
    assert event is not None
    assert event["lanes"]["dashboard"]["graded_pick_count"] == 1
    assert event["lanes"]["lab"]["graded_pick_count"] == 1
    assert event["comparison"]["overlap_matchups"] == 0
    assert payload["summary"]["dashboard"]["wins"] == 1
    assert payload["summary"]["lab"]["losses"] == 1


def test_grading_season_lane_filter_dashboard(monkeypatch, tmp_path):
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "grading_season_lane.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (1, "Season Test Open", "Test Course", 2026, "9001"),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
            opponent_key, opponent_display, market_odds, market_book, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "baseline", "cockpit", "matchup", "dash_player", "Dash Player", "dash_opp", "Dash Opp", "-110", "fanduel", 0.55, 0.05),
    )
    conn.execute(
        """INSERT INTO pick_outcomes (pick_id, hit, profit, odds_decimal, stake, entered_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, 1, 0.91, 1.91, 1.0, "2026-06-01 10:00:00"),
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/grading/season?year=2026&lane=cockpit")
    assert response.status_code == 200
    payload = response.json()
    event = next((row for row in payload["events"] if row["event_id"] == "9001"), None)
    assert event is not None
    assert event["graded_pick_count"] == 1
    assert len(event["picks"]) == 1
    assert event["picks"][0]["source"] == "cockpit"


def test_grading_season_events_chronological_pga(monkeypatch, tmp_path):
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "grading_season_chrono.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executemany(
        """
        INSERT INTO rounds (dg_id, event_id, event_name, year, tour, event_completed, round_num)
        VALUES (?, ?, ?, 2026, 'pga', ?, 4)
        """,
        [
            (1, "100", "Zebra Open", "2026-06-20"),
            (2, "200", "Alpha Open", "2026-03-01"),
            (3, "300", "Beta Open", "2026-04-15"),
        ],
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/grading/season?year=2026&tour=pga")
    assert response.status_code == 200
    events = response.json()["events"]
    event_ids = [row["event_id"] for row in events if row["event_id"] in {"100", "200", "300"}]
    assert event_ids == ["200", "300", "100"]
    assert events[0].get("event_date") == "2026-03-01"


def test_lane_ungraded_zero_before_results(monkeypatch, tmp_path):
    """Upcoming events with +EV inventory must not count as ungraded +EV gaps."""
    import app as app_module
    from src import db as db_module

    db_path = tmp_path / "grading_season_ungraded.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO tournaments (id, name, course, year, event_id) VALUES (?, ?, ?, ?, ?)",
        (1, "Upcoming Test", "Test Course", 2026, "8001"),
    )
    conn.execute(
        """INSERT INTO picks
           (id, tournament_id, model_variant, source, bet_type, player_key, player_display,
            market_odds, market_book, model_prob, ev)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "baseline", "cockpit", "top10", "player_a", "Player A", "+200", "fanduel", 0.4, 0.05),
    )
    conn.commit()
    conn.close()

    client = TestClient(app_module.app)
    response = client.get("/api/grading/season?year=2026&lane=cockpit")
    assert response.status_code == 200
    event = next((row for row in response.json()["events"] if row["event_id"] == "8001"), None)
    assert event is not None
    assert event["has_results"] is False
    assert event["lanes"]["dashboard"]["ungraded_positive_ev_count"] == 0

