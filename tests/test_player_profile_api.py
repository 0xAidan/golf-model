"""Regression coverage for local-only player profile HTTP routes."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


def _explode(*_args, **_kwargs):
    raise AssertionError("HTTP player profiles must not fetch Data Golf")


def test_standalone_profile_uses_ingested_data_without_datagolf_requests(monkeypatch, tmp_path):
    """The HTTP profile is assembled from stored metrics, rounds, and snapshots."""
    from src import db

    db_path = tmp_path / "player_profile.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO tournaments (id, name, year) VALUES (?, ?, ?)",
        (7, "Stored Event", 2026),
    )
    conn.executemany(
        """INSERT INTO metrics
           (tournament_id, player_key, player_display, metric_category, metric_name, metric_value)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (7, "collin_morikawa", "Collin Morikawa", "dg_skill", "sg_total", 1.2),
            (7, "collin_morikawa", "Collin Morikawa", "dg_skill", "sg_app", 0.7),
            (7, "collin_morikawa", "Collin Morikawa", "dg_ranking", "dg_rank", 4),
            (7, "collin_morikawa", "Collin Morikawa", "dg_ranking", "owgr_rank", 6),
            (7, "collin_morikawa", "Collin Morikawa", "dg_approach", "sg_150_200_fw", 0.11),
        ],
    )
    conn.execute(
        """INSERT INTO rounds
           (dg_id, player_name, player_key, tour, season, year, event_id, event_name,
            event_completed, course_name, course_num, course_par, round_num, score, sg_total, sg_app)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (456, "Collin Morikawa", "collin_morikawa", "pga", 2026, 2026, "501",
         "Stored Event", "2026-04-12", "Augusta National", 10, 72, 4, 69, 1.7, 0.8),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("src.datagolf.fetch_skill_ratings", _explode)
    monkeypatch.setattr("src.datagolf.fetch_dg_rankings", _explode)
    monkeypatch.setattr("src.datagolf.fetch_approach_skill", _explode)

    import app

    response = TestClient(app.app).get("/api/players/collin_morikawa/standalone-profile")

    assert response.status_code == 200
    body = response.json()
    assert body["sg_skills"]["sg_total"] == 1.2
    assert body["ranking_card"]["dg_rank"] == 4
    assert body["approach_buckets"][0]["key"] == "sg_150_200_fw"
    assert body["availability"]["skill"] is True
    assert body["availability"]["rankings"] is True
    assert body["availability"]["approach"] is True
    assert body["availability"]["snapshot"] is False
    assert body["cache"]["key"].startswith("collin_morikawa:")


def test_standalone_profile_marks_missing_local_sections_unavailable(monkeypatch, tmp_path):
    """Missing stored inputs are explicit instead of triggering remote fallbacks."""
    from src import db

    db_path = tmp_path / "empty_profile.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    monkeypatch.setattr("src.datagolf.fetch_skill_ratings", _explode)
    monkeypatch.setattr("src.datagolf.fetch_dg_rankings", _explode)
    monkeypatch.setattr("src.datagolf.fetch_approach_skill", _explode)

    import app

    response = TestClient(app.app).get("/api/players/missing_player/standalone-profile")

    assert response.status_code == 200
    assert response.json()["availability"] == {
        "skill": False,
        "rankings": False,
        "approach": False,
        "rounds": False,
        "snapshot": False,
    }
