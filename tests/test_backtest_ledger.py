"""Tests for the derived research backtest line/outcome ledger."""

from __future__ import annotations

import pytest

from backtester.backtest_ledger import (
    MARKET_FAMILY,
    PRE_EVENT_SECTIONS,
    american_to_implied,
    build_research_backtest_lines,
    coverage_summary,
)


@pytest.fixture()
def capture_db(tmp_db):
    """tmp_db with market_prediction_rows + grading spine fixtures."""
    conn = tmp_db.get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_prediction_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            generated_at TEXT,
            tour TEXT,
            section TEXT NOT NULL,
            event_id TEXT,
            event_name TEXT,
            market_family TEXT NOT NULL,
            market_type TEXT,
            player_key TEXT,
            player_display TEXT,
            opponent_key TEXT,
            opponent_display TEXT,
            book TEXT,
            odds TEXT,
            model_prob REAL,
            implied_prob REAL,
            ev REAL,
            is_value INTEGER DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            bet_type TEXT,
            player_key TEXT,
            opponent_key TEXT
        );
        CREATE TABLE IF NOT EXISTS pick_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_id INTEGER,
            hit INTEGER
        );
        """
    )
    # One tournament mapping event_id '34'.
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, '34')")
    # Two captured lines for event 34 (upcoming section), one live-section decoy.
    rows = [
        ("snap1", "2026-06-25T10:00:00", "upcoming", "34", "tournament_matchups",
         "player_a", "player_b", "bet365", "+110", '{"market_type": "tournament_matchups"}'),
        ("snap2", "2026-06-25T12:00:00", "upcoming", "34", "tournament_matchups",
         "player_a", "player_b", "bet365", "+120", '{"market_type": "tournament_matchups"}'),
        ("snap3", "2026-06-26T09:00:00", "live", "34", "tournament_matchups",
         "player_c", "player_d", "fanduel", "-130", "{}"),
    ]
    for snap_id, ts, section, ev, mtype, pk, ok, book, odds, payload in rows:
        conn.execute(
            """
            INSERT INTO market_prediction_rows (snapshot_id, generated_at, tour, section, event_id,
                event_name, market_family, market_type, player_key, player_display, opponent_key,
                opponent_display, book, odds, payload_json)
            VALUES (?, ?, 'pga', ?, ?, 'Test', 'matchup', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (snap_id, ts, section, ev, mtype, pk, pk.title(), ok, ok.title(), book, odds, payload),
        )
    # A graded pick: player_a beat player_b.
    conn.execute(
        "INSERT INTO picks (id, tournament_id, bet_type, player_key, opponent_key) VALUES (1, 1, '72-hole Match', 'player_a', 'player_b')"
    )
    conn.execute("INSERT INTO pick_outcomes (pick_id, hit) VALUES (1, 1)")
    conn.commit()
    yield conn


def test_american_to_implied_golden():
    assert american_to_implied("+100") == pytest.approx(0.5)
    assert american_to_implied("+110") == pytest.approx(0.476190, abs=1e-5)
    assert american_to_implied("-150") == pytest.approx(0.6)
    assert american_to_implied("bogus") is None


def test_build_is_idempotent_and_excludes_live(capture_db):
    first = build_research_backtest_lines(event_id="34", year=2026)
    assert first.events_seen >= 1
    rows = capture_db.execute(
        "SELECT player_key, opponent_key, book, odds_american FROM research_backtest_lines"
    ).fetchall()
    # Only the upcoming-section pair qualifies; live decoy excluded.
    assert len(rows) == 1
    key = rows[0]
    assert key[0] == "player_a" and key[1] == "player_b" and key[2] == "bet365"

    second = build_research_backtest_lines(event_id="34", year=2026)
    count_after = capture_db.execute("SELECT COUNT(*) FROM research_backtest_lines").fetchone()[0]
    assert count_after == 1  # still one row: idempotent


def test_outcome_join_from_graded_picks(capture_db):
    build_research_backtest_lines(event_id="34", year=2026)
    row = capture_db.execute(
        "SELECT outcome, outcome_source FROM research_backtest_lines WHERE player_key='player_a'"
    ).fetchone()
    assert row["outcome"] == "win"
    assert row["outcome_source"] == "graded_picks"


def test_coverage_summary_shape(capture_db):
    build_research_backtest_lines(event_id="34", year=2026)
    summary = coverage_summary()
    assert summary["total_lines"] == 1
    assert summary["distinct_events"] == 1
    assert summary["lines_with_outcome"] == 1
    assert summary["per_event"][0]["event_id"] == "34"


def test_pre_event_sections_constant():
    assert "live" not in PRE_EVENT_SECTIONS
    assert MARKET_FAMILY == "matchup"
