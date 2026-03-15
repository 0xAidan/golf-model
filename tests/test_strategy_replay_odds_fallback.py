import sqlite3

from backtester.strategy import StrategyConfig, replay_event


def _seed_replay_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE historical_odds (
            event_id TEXT,
            year INTEGER,
            player_dg_id INTEGER,
            player_name TEXT,
            market TEXT,
            book TEXT,
            open_line REAL,
            close_line REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE rounds (
            event_id TEXT,
            year INTEGER,
            player_key TEXT,
            fin_text TEXT
        )
        """
    )
    return conn


def test_replay_event_falls_back_to_close_when_open_line_missing(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        INSERT INTO historical_odds
        (event_id, year, player_dg_id, player_name, market, book, open_line, close_line)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, 1, "Scottie Scheffler", "win", "dg", None, 500.0),
    )
    conn.execute(
        "INSERT INTO rounds (event_id, year, player_key, fin_text) VALUES (?, ?, ?, ?)",
        ("evt", 2026, "scottie_scheffler", "1"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {
            "scottie_scheffler": {
                "composite": 1.0,
                "course_fit": 1.0,
                "form": 1.0,
                "momentum": 1.0,
            }
        },
    )

    strategy = StrategyConfig(
        name="odds_fallback_test",
        markets=["win"],
        min_ev=-1.0,
        min_model_prob=0.0,
        max_implied_prob=1.0,
    )
    bets = replay_event("evt", 2026, strategy, odds_source="open")
    assert len(bets) == 1
