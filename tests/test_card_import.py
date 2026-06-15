"""Tests for markdown card import."""

from pathlib import Path

from src.card_import import parse_best_bets_table, parse_card_file, parse_matchup_tables

PLAYERS_SNIPPET = """
| Pick | vs | Odds | Model Win% | EV | Tier | Book | Why |
|------|-----|------|------------|-----|------|------|-----|
| **Ludvig Aberg** | Michael Thorbjornsen | -130 | 85.0% | 50.3% | STRONG | bet365 | course fit |
"""


def test_parse_matchup_table():
    picks = parse_matchup_tables(PLAYERS_SNIPPET)
    assert len(picks) == 1
    assert picks[0].player_display == "Ludvig Aberg"
    assert picks[0].ev == 0.503


def test_parse_players_card_file():
    path = Path("data/local_recovery/md_cards/md cards/the_players_championship_20260315.md")
    if not path.is_file():
        return
    picks = parse_card_file(path)
    assert len(picks) >= 3
    assert any((pick.ev or 0) > 0 for pick in picks)


def test_parse_best_bets_matchup_rows():
    text = """
## 3 Best Bets
| Pick | Market | Odds | EV% | Tier |
|------|--------|------|-----|------|
| **Ludvig Aberg vs Michael Thorbjornsen** | matchup | -130 | 50.3% | STRONG |
"""
    picks = parse_best_bets_table(text)
    assert len(picks) == 1
    assert picks[0].opponent_display == "Michael Thorbjornsen"
