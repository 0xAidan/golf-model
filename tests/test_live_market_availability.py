"""Live market availability gating (E14)."""

from __future__ import annotations

from backtester import dashboard_runtime as runtime


def test_tournament_matchups_not_live_bettable_when_gating_enabled(monkeypatch):
    monkeypatch.setattr(runtime.config, "LIVE_MARKET_AVAILABILITY_GATING", True)
    row = {
        "pick": "Player A",
        "pick_key": "player_a",
        "opponent": "Player B",
        "opponent_key": "player_b",
        "book": "bet365",
        "odds": "+110",
        "market_type": "tournament_matchups",
        "ev": 0.12,
    }
    runtime._annotate_live_market_row(
        row,
        generated_at="2026-06-14T12:00:00+00:00",
        last_seen_tick="tick-1",
        live_is_active=True,
    )
    assert row["market_provenance"] == "tournament_matchups"
    assert row["live_bettable"] is False
    assert "72-hole" in str(row["availability_reason"])


def test_round_matchups_live_bettable_with_book_line(monkeypatch):
    monkeypatch.setattr(runtime.config, "LIVE_MARKET_AVAILABILITY_GATING", True)
    row = {
        "pick": "Player A",
        "pick_key": "player_a",
        "opponent": "Player B",
        "opponent_key": "player_b",
        "book": "bet365",
        "odds": "-105",
        "market_type": "round_matchups",
        "ev": 0.09,
    }
    runtime._annotate_live_market_row(
        row,
        generated_at="2026-06-14T12:00:00+00:00",
        last_seen_tick="tick-1",
        live_is_active=True,
    )
    assert row["market_provenance"] == "round_matchups"
    assert row["live_bettable"] is True
    assert row["last_seen_tick"] == "tick-1"


def test_new_live_opportunity_requires_bettable_row():
    section = {
        "matchup_bets": [
            {
                "pick": "A",
                "pick_key": "a",
                "opponent": "B",
                "opponent_key": "b",
                "book": "bet365",
                "odds": "+120",
                "market_type": "tournament_matchups",
                "ev": 0.1,
                "live_bettable": False,
                "market_provenance": "tournament_matchups",
            }
        ],
        "matchup_bets_all_books": [],
        "value_bets": {},
    }
    runtime._annotate_live_market_availability(
        section,
        generated_at="2026-06-14T12:00:00+00:00",
        snapshot_id="snap-2",
        live_is_active=True,
    )
    alerts = runtime._apply_live_opportunity_flags(
        section,
        previous_section_payload={"matchup_bets": [], "matchup_bets_all_books": [], "value_bets": {}},
        generated_at="2026-06-14T12:00:00+00:00",
    )
    row = section["matchup_bets"][0]
    assert row["is_new_since_last_snapshot"] is True
    assert row["is_new_live_opportunity"] is False
    assert alerts == []
