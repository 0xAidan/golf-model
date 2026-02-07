"""
Odds Integration

Fetch golf betting odds from The Odds API and/or parse saved HTML.
Supports: outrights, top 5, top 10, top 20, matchups.
"""

import json
import os
import re
import requests
from typing import Optional


# ── The Odds API ────────────────────────────────────────────────────

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "golf_pga"


def fetch_odds_api(market: str = "outrights") -> list[dict]:
    """
    Fetch odds from The Odds API.

    market: 'outrights', 'top_5', 'top_10', 'top_20'
    Returns: list of {player, bookmaker, price, implied_prob}
    """
    if not ODDS_API_KEY:
        print("  No ODDS_API_KEY set. Skipping API odds fetch.")
        print("  Set it with: export ODDS_API_KEY=your_key_here")
        return []

    # Map market names to API format
    market_map = {
        "outrights": "outrights",
        "top_5": "outrights_top_5",
        "top_10": "outrights_top_10",
        "top_20": "outrights_top_20",
    }
    api_market = market_map.get(market, market)

    try:
        url = f"{ODDS_API_BASE}/sports/{SPORT}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": api_market,
            "oddsFormat": "american",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for event in data:
            for bookmaker in event.get("bookmakers", []):
                bk_name = bookmaker.get("title", "")
                for market_data in bookmaker.get("markets", []):
                    for outcome in market_data.get("outcomes", []):
                        name = outcome.get("name", "")
                        price = outcome.get("price", 0)
                        impl_prob = american_to_implied_prob(price)
                        results.append({
                            "player": name,
                            "bookmaker": bk_name,
                            "price": price,
                            "implied_prob": round(impl_prob, 4),
                            "market": market,
                        })
        return results

    except Exception as e:
        print(f"  Odds API error: {e}")
        return []


def american_to_implied_prob(price: int) -> float:
    """Convert American odds to implied probability."""
    if price > 0:
        return 100.0 / (price + 100.0)
    elif price < 0:
        return abs(price) / (abs(price) + 100.0)
    return 0.0


def american_to_decimal(price: int) -> float:
    """Convert American odds to decimal odds."""
    if price > 0:
        return 1.0 + price / 100.0
    elif price < 0:
        return 1.0 + 100.0 / abs(price)
    return 1.0


# ── Manual odds entry ───────────────────────────────────────────────

def load_manual_odds(filepath: str) -> list[dict]:
    """
    Load manually entered odds from a JSON file.

    Expected format:
    {
        "market": "outrights",
        "bookmaker": "bet365",
        "odds": {
            "Scottie Scheffler": "+450",
            "Xander Schauffele": "+1000",
            ...
        }
    }
    """
    if not os.path.exists(filepath):
        return []

    with open(filepath) as f:
        data = json.load(f)

    market = data.get("market", "outrights")
    bookmaker = data.get("bookmaker", "manual")
    odds_map = data.get("odds", {})

    results = []
    for player, price_str in odds_map.items():
        price = int(price_str.replace("+", ""))
        impl_prob = american_to_implied_prob(price)
        results.append({
            "player": player,
            "bookmaker": bookmaker,
            "price": price,
            "implied_prob": round(impl_prob, 4),
            "market": market,
        })
    return results


# ── Aggregate odds across books ─────────────────────────────────────

def get_best_odds(odds_list: list[dict]) -> dict:
    """
    For each player, find the best (highest) price across all bookmakers.

    Returns: {player_name_lower: {player, best_price, best_book, implied_prob, all_books: [...]}}
    """
    by_player = {}
    for o in odds_list:
        name = o["player"].lower().strip()
        if name not in by_player:
            by_player[name] = {
                "player": o["player"],
                "best_price": o["price"],
                "best_book": o["bookmaker"],
                "implied_prob": o["implied_prob"],
                "market": o["market"],
                "all_books": [],
            }
        by_player[name]["all_books"].append({
            "bookmaker": o["bookmaker"],
            "price": o["price"],
        })
        if o["price"] > by_player[name]["best_price"]:
            by_player[name]["best_price"] = o["price"]
            by_player[name]["best_book"] = o["bookmaker"]
            by_player[name]["implied_prob"] = o["implied_prob"]

    return by_player
