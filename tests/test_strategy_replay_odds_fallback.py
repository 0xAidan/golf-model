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
    conn.execute(
        """
        CREATE TABLE historical_matchup_odds (
            event_id TEXT,
            year INTEGER,
            book TEXT,
            bet_type TEXT,
            p1_dg_id INTEGER,
            p1_name TEXT,
            p2_dg_id INTEGER,
            p2_name TEXT,
            p1_open REAL,
            p1_close REAL,
            p2_open REAL,
            p2_close REAL,
            p1_outcome TEXT,
            p2_outcome TEXT,
            p1_outcome_text TEXT,
            p2_outcome_text TEXT,
            tie_rule TEXT
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


def test_replay_matchups_use_shared_eval_and_flat_stake(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "bet365", "72-hole Match", 1, "Player A", 2, "Player B",
         110.0, 110.0, -130.0, -130.0, "win", "loss", "win", "loss", "push"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {
            "player_a": {"composite": 79.0, "course_fit": 74.0, "form": 76.0, "momentum": 61.0},
            "player_b": {"composite": 63.0, "course_fit": 60.0, "form": 62.0, "momentum": 49.0},
        },
    )

    strategy = StrategyConfig(
        name="matchup_parity_flat",
        markets=["matchup"],
        flat_stake=0.03,
        stake_mode="flat",
        min_composite_gap=5.0,
    )
    bets = replay_event("evt", 2026, strategy, odds_source="close")
    assert len(bets) == 1
    assert bets[0]["market"] == "matchup"
    assert bets[0]["wager"] == 0.03
    assert bets[0]["ev"] > 0


def test_replay_matchups_require_positive_ev_even_if_threshold_negative(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "bet365", "72-hole Match", 1, "Player A", 2, "Player B",
         -1000.0, -1000.0, -1000.0, -1000.0, "loss", "win", "loss", "win", "push"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {
            "player_a": {"composite": 70.0, "course_fit": 70.0, "form": 70.0, "momentum": 55.0},
            "player_b": {"composite": 69.9, "course_fit": 69.0, "form": 69.0, "momentum": 54.0},
        },
    )
    monkeypatch.setattr("backtester.strategy.config.MATCHUP_EV_THRESHOLD", -1.0)

    strategy = StrategyConfig(
        name="matchup_positive_ev_guard",
        markets=["matchup"],
        matchup_ev_threshold=-1.0,
        min_composite_gap=0.0,
    )
    bets = replay_event("evt", 2026, strategy, odds_source="close")
    assert bets == []


def test_replay_matchups_include_all_books_when_enabled(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "bet365", "72-hole Match", 1, "Player A", 2, "Player B",
         110.0, 110.0, -130.0, -130.0, "win", "loss", "win", "loss", "push"),
    )
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "fanduel", "72-hole Match", 1, "Player A", 2, "Player B",
         110.0, 110.0, -130.0, -130.0, "win", "loss", "win", "loss", "push"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {
            "player_a": {"composite": 79.0, "course_fit": 74.0, "form": 76.0, "momentum": 61.0},
            "player_b": {"composite": 63.0, "course_fit": 60.0, "form": 62.0, "momentum": 49.0},
        },
    )

    default_strategy = StrategyConfig(
        name="default_book_filter",
        markets=["matchup"],
        min_composite_gap=5.0,
    )
    default_bets = replay_event("evt", 2026, default_strategy, odds_source="close")
    assert len(default_bets) == 1
    assert default_bets[0]["book"] == "bet365"

    full_book_strategy = StrategyConfig(
        name="all_books",
        markets=["matchup"],
        min_composite_gap=5.0,
        matchup_include_all_books=True,
    )
    all_book_bets = replay_event("evt", 2026, full_book_strategy, odds_source="close")
    assert len(all_book_bets) == 2
    assert {b["book"] for b in all_book_bets} == {"bet365", "fanduel"}


def test_replay_matchups_accepts_three_ball_labels(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "bet365", "R1 3-Ball", 1, "Player A", 2, "Player B",
         110.0, 110.0, -130.0, -130.0, "win", "loss", "win", "loss", "push"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {
            "player_a": {"composite": 79.0, "course_fit": 74.0, "form": 76.0, "momentum": 61.0},
            "player_b": {"composite": 63.0, "course_fit": 60.0, "form": 62.0, "momentum": 49.0},
        },
    )

    strategy = StrategyConfig(
        name="three_ball_support",
        markets=["matchup"],
        min_composite_gap=5.0,
    )
    bets = replay_event("evt", 2026, strategy, odds_source="close")
    assert len(bets) == 1
    assert bets[0]["matchup_type"] == "R1 3-Ball"


def test_replay_matchups_uses_odds_based_fallback_when_pit_missing(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        CREATE TABLE pit_rolling_stats (
            event_id TEXT,
            year INTEGER,
            player_key TEXT,
            sg_total REAL,
            sg_ott REAL,
            sg_app REAL,
            sg_arg REAL,
            sg_putt REAL,
            sg_t2g REAL,
            rounds_used INTEGER,
            window INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "bet365", "R2 Match-Up", 1, "Player A", 2, "Player B",
         -130.0, -130.0, 110.0, 110.0, "win", "loss", "win", "loss", "push"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {},
    )

    strategy = StrategyConfig(
        name="pit_missing_fallback",
        markets=["matchup"],
        min_composite_gap=0.0,
        matchup_require_positive_ev=False,
        matchup_ev_threshold=-1.0,
        matchup_market_types=["R2 Match-Up"],
    )
    bets = replay_event("evt", 2026, strategy, odds_source="close")
    assert len(bets) == 1
    assert bets[0]["matchup_type"] == "R2 Match-Up"


def test_replay_matchups_parses_even_odds_strings(monkeypatch):
    conn = _seed_replay_db()
    conn.execute(
        """
        INSERT INTO historical_matchup_odds
        (event_id, year, book, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name,
         p1_open, p1_close, p2_open, p2_close, p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("evt", 2026, "bet365", "R1 Match-Up", 1, "Player A", 2, "Player B",
         "EVEN", "EVEN", -110.0, -110.0, "win", "loss", "win", "loss", "push"),
    )
    conn.commit()

    monkeypatch.setattr("backtester.strategy.db.get_conn", lambda: conn)
    monkeypatch.setattr(
        "backtester.strategy.compute_pit_composite",
        lambda *_args, **_kwargs: {
            "player_a": {"composite": 77.0, "course_fit": 74.0, "form": 76.0, "momentum": 61.0},
            "player_b": {"composite": 62.0, "course_fit": 60.0, "form": 62.0, "momentum": 49.0},
        },
    )

    strategy = StrategyConfig(
        name="even_odds_support",
        markets=["matchup"],
        min_composite_gap=5.0,
        matchup_market_types=["R1 Match-Up"],
    )
    bets = replay_event("evt", 2026, strategy, odds_source="close")
    assert len(bets) == 1
    assert bets[0]["odds"] == 100
