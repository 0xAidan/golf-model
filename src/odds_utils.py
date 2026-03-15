"""
Shared odds utility functions.

Canonical implementations of odds conversion and validation.
All other modules (odds.py, value.py, matchup_value.py, etc.) should
import from here or from odds.py (which re-exports these).
"""

from src import config as _config

_MAX_ODDS_ALIASES = {"outrights": "outright", "top_5": "top5", "top_10": "top10", "top_20": "top20"}
MAX_REASONABLE_ODDS = 50000


def american_to_decimal(price: int) -> float:
    """Convert American odds to decimal odds. Returns 1.0 for invalid price == 0."""
    if price > 0:
        return 1.0 + price / 100.0
    elif price < 0:
        return 1.0 + 100.0 / abs(price)
    return 1.0


def american_to_implied_prob(price: int) -> float:
    """Convert American odds to implied probability. Returns 0 for invalid price."""
    if price > 0:
        return 100.0 / (price + 100.0)
    elif price < 0:
        return abs(price) / (abs(price) + 100.0)
    return 0.0


def is_valid_odds(price: int, bet_type: str = None) -> bool:
    """Check if American odds value is within reasonable bounds."""
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
    if price > MAX_REASONABLE_ODDS:
        return False
    if bet_type:
        canonical = _MAX_ODDS_ALIASES.get(bet_type, bet_type)
        max_odds = _config.MAX_REASONABLE_ODDS.get(canonical, _config.MAX_REASONABLE_ODDS.get("outright", MAX_REASONABLE_ODDS))
        if price > max_odds:
            return False
    return True
