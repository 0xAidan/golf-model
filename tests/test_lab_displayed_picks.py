"""Tests for lab sandbox displayed-picks persistence."""

from src.lab_displayed_picks import persist_lab_logged_picks


def test_persist_lab_logged_picks_writes_lab_sandbox_source(tmp_db):
    tid = tmp_db.get_or_create_tournament("Lab log event", year=2026)
    n = persist_lab_logged_picks(
        {
            "tournament_id": tid,
            "profile_name": "lab_sandbox",
            "composite_results": [
                {"player_key": "player_a", "composite": 1.0, "course_fit": 0.0, "form": 0.0, "momentum": 0.0},
            ],
            "matchups": [
                {
                    "pick_key": "player_a",
                    "opponent_key": "player_b",
                    "pick": "Player A",
                    "opponent": "Player B",
                    "odds": -110,
                    "book": "draftkings",
                    "ev": 0.05,
                    "model_win_prob": 0.55,
                    "implied_prob": 0.52,
                    "tier": "STANDARD",
                    "why": "edge",
                },
            ],
        },
    )
    assert n == 1
    conn = tmp_db.get_conn()
    row = conn.execute(
        "SELECT source, model_variant FROM picks WHERE tournament_id = ?",
        (tid,),
    ).fetchone()
    conn.close()
    assert row["source"] == "lab_sandbox"
    assert row["model_variant"] == "baseline"


def test_store_picks_defaults_source_to_cockpit(tmp_db):
    tid = tmp_db.get_or_create_tournament("Cockpit default", year=2026)
    tmp_db.store_picks(
        [
            {
                "tournament_id": tid,
                "model_variant": "v5",
                "bet_type": "matchup",
                "player_key": "x",
                "player_display": "X",
                "opponent_key": "y",
                "opponent_display": "Y",
                "market_odds": "-110",
                "market_book": "dk",
            },
        ],
    )
    conn = tmp_db.get_conn()
    row = conn.execute("SELECT source FROM picks WHERE tournament_id = ?", (tid,)).fetchone()
    conn.close()
    assert row["source"] == "cockpit"
