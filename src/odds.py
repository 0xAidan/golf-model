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

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "golf_pga"


def fetch_odds_api(market: str = "outrights") -> list[dict]:
    """
    Fetch odds from The Odds API.

    market: 'outrights', 'top_5', 'top_10', 'top_20'
    Returns: list of {player, bookmaker, price, implied_prob}
    """
    # Read API key at call time so .env is loaded before this runs
    ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
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
    """Convert American odds to implied probability. Returns 0 for invalid price."""
    if price > 0:
        return 100.0 / (price + 100.0)
    elif price < 0:
        return abs(price) / (abs(price) + 100.0)
    # price == 0 is invalid in American odds
    return 0.0


# ── Odds validation ──────────────────────────────────────────────
# Market-specific max odds from config (single source of truth with value.py)
from src import config as _config
_MAX_ODDS_ALIASES = {"outrights": "outright", "top_5": "top5", "top_10": "top10", "top_20": "top20"}
MAX_REASONABLE_ODDS = 50000  # global fallback for code that expects a number
MAX_REASONABLE_ODDS_BY_TYPE = _config.MAX_REASONABLE_ODDS

# Minimum reasonable implied probability. Any odds implying less than
# this are filtered as garbage (0.2% ≈ +50000).
MIN_REASONABLE_IMPLIED_PROB = 0.002


def is_valid_odds(price: int, bet_type: str = None) -> bool:
    """
    Check if American odds value is within reasonable bounds.

    Args:
        price: The American odds value to check
        bet_type: Optional bet type for market-specific limits

    Returns:
        True if odds are valid, False if likely corrupted
    """
    if price is None:
        return False
    try:
        price = int(price)
    except (ValueError, TypeError):
        return False
    if price == 0:
        return False
    if price < -10000:
        return False

    # Global maximum
    if price > MAX_REASONABLE_ODDS:
        return False

    # Market-specific maximum (unknown market falls back to outright max 30000)
    if bet_type:
        canonical = _MAX_ODDS_ALIASES.get(bet_type, bet_type)
        max_odds = MAX_REASONABLE_ODDS_BY_TYPE.get(canonical, MAX_REASONABLE_ODDS_BY_TYPE["outright"])
        if price > max_odds:
            return False

    return True


def is_reasonable_odds(price: int, bet_type: str = "outright") -> bool:
    """Check if odds are within reasonable range for the bet type."""
    return is_valid_odds(price, bet_type=bet_type)


def american_to_decimal(price: int) -> float:
    """Convert American odds to decimal odds. Returns 1.0 for invalid price == 0."""
    if price > 0:
        return 1.0 + price / 100.0
    elif price < 0:
        return 1.0 + 100.0 / abs(price)
    # price == 0 is invalid -- return 1.0 (even money) as safe fallback
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

# DG model references — not real bettable sportsbooks
_DG_MODEL_BOOKS = {"DG-CH", "DG-Base"}

def _get_preferred_book() -> str:
    """Get preferred book at call time so .env is loaded first."""
    return os.environ.get("PREFERRED_BOOK", "bet365")


def get_best_odds(odds_list: list[dict], preferred_book: str = None) -> dict:
    """
    For each player, find the best actionable odds.

    If preferred_book is set, uses that book's odds for the primary price
    (since that's where the user actually bets), and includes best-available
    across all books as a reference.

    DG model prices (DG-CH, DG-Base) are stored as reference but excluded
    from the "best odds" since you can't actually bet at those prices.

    Returns: {player_name_lower: {
        player, best_price, best_book, implied_prob,
        preferred_price, preferred_book,  # odds at the user's book
        all_books, dg_model_prices
    }}
    """
    if preferred_book is None:
        preferred_book = _get_preferred_book()

    by_player = {}
    filtered_count = 0
    for o in odds_list:
        name = o["player"].lower().strip()
        is_dg_model = o["bookmaker"] in _DG_MODEL_BOOKS

        # Skip garbage odds (e.g., +500000 from bad API data)
        if not is_dg_model and not is_valid_odds(o.get("price")):
            filtered_count += 1
            continue

        if name not in by_player:
            by_player[name] = {
                "player": o["player"],
                "best_price": None,
                "best_book": None,
                "implied_prob": None,
                "preferred_price": None,
                "preferred_book": preferred_book,
                "preferred_implied_prob": None,
                "market": o["market"],
                "all_books": [],
                "dg_model_prices": [],
            }

        if is_dg_model:
            by_player[name]["dg_model_prices"].append({
                "bookmaker": o["bookmaker"],
                "price": o["price"],
                "implied_prob": o["implied_prob"],
            })
        else:
            by_player[name]["all_books"].append({
                "bookmaker": o["bookmaker"],
                "price": o["price"],
            })
            # Track best across all books
            if (by_player[name]["best_price"] is None
                    or o["price"] > by_player[name]["best_price"]):
                by_player[name]["best_price"] = o["price"]
                by_player[name]["best_book"] = o["bookmaker"]
                by_player[name]["implied_prob"] = o["implied_prob"]

            # Track preferred book specifically
            if (preferred_book
                    and o["bookmaker"].lower() == preferred_book.lower()):
                by_player[name]["preferred_price"] = o["price"]
                by_player[name]["preferred_implied_prob"] = o["implied_prob"]

    # When preferred book has odds, use those as primary (actionable) price.
    # Fall back to best across all books if preferred book doesn't list that player.
    for name, entry in by_player.items():
        if entry["preferred_price"] is not None:
            # User can bet at their preferred book
            entry["best_price"] = entry["preferred_price"]
            entry["best_book"] = preferred_book
            entry["implied_prob"] = entry["preferred_implied_prob"]

    if filtered_count > 0:
        print(f"  ⚠ Filtered {filtered_count} odds entries with unreasonable values (>{MAX_REASONABLE_ODDS})")

    # Remove players that have no real sportsbook odds
    return {k: v for k, v in by_player.items() if v["best_price"] is not None}
