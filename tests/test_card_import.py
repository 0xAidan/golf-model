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


def test_parse_provenance_json_matchups(tmp_path):
    from src.card_import import parse_provenance_json, provenance_is_live, select_canonical_card, CardCandidate
    from datetime import date

    payload = tmp_path / "masters_tournament_provenance_20260408.json"
    payload.write_text(
        """{
          "phase": "live",
          "market_rows": [
            {
              "market_family": "matchup",
              "market_type": "tournament_matchups",
              "player_display": "Tiger Woods",
              "opponent_display": "Rory McIlroy",
              "odds": "+120",
              "book": "draftkings",
              "ev": 0.04
            }
          ]
        }""",
        encoding="utf-8",
    )
    picks = parse_provenance_json(payload)
    assert len(picks) == 1
    assert provenance_is_live(payload)
    md = CardCandidate(path=tmp_path / "masters_tournament_20260408.md", event_slug="masters", file_date=date(2026, 4, 8), lane="dashboard", kind="betting_card")
    prov = CardCandidate(path=payload, event_slug="masters", file_date=date(2026, 4, 8), lane="dashboard", kind="provenance")
    chosen, rejected = select_canonical_card([md, prov], event_name="Masters", round1_thursday=date(2026, 4, 9))
    assert chosen is not None
    assert chosen.kind == "betting_card"
    assert prov in rejected
