"""
Portfolio Diversification Rules

Enforces constraints on bet selection to prevent catastrophic concentration.
These rules are applied as a post-processing step after value bets are identified.

Based on lessons learned:
- Genesis: 11/12 placement bets on 3 players, -6.83u when 2 busted
- Pebble Beach: AI concentrated 87% of units on one player
"""

import logging

logger = logging.getLogger("portfolio")

MAX_BETS_PER_PLAYER = 2
MIN_UNIQUE_PLAYERS = 3
MAX_PLACEMENT_BETS = 6
SPECULATIVE_MARKETS = {"outright", "top5", "frl"}
CORE_MARKETS = {"top10", "top20", "make_cut"}


def enforce_diversification(value_bets_by_market: dict) -> dict:
    """
    Apply diversification rules to value bets across all markets.

    Takes the raw value_bets dict (keyed by market type, values are lists of bet dicts)
    and returns a filtered version respecting concentration limits.

    Each bet dict must have at minimum: player_key, ev, is_value.
    """
    all_value_bets = []
    for market, bets in value_bets_by_market.items():
        for bet in bets:
            if bet.get("is_value") and not bet.get("suspicious") and not bet.get("ev_capped"):
                all_value_bets.append({**bet, "_market": market})

    if not all_value_bets:
        return value_bets_by_market

    all_value_bets.sort(key=lambda x: x.get("ev", 0), reverse=True)

    player_bet_count = {}
    selected = []
    placement_count = 0

    for bet in all_value_bets:
        pk = bet["player_key"]
        market = bet["_market"]

        current_count = player_bet_count.get(pk, 0)
        if current_count >= MAX_BETS_PER_PLAYER:
            logger.info(
                "Diversification: dropped %s %s bet (player already has %d bets)",
                bet.get("player_display", pk), market, current_count,
            )
            continue

        if market in CORE_MARKETS and placement_count >= MAX_PLACEMENT_BETS:
            logger.info(
                "Diversification: dropped %s %s bet (placement cap %d reached)",
                bet.get("player_display", pk), market, MAX_PLACEMENT_BETS,
            )
            continue

        selected.append(bet)
        player_bet_count[pk] = current_count + 1
        if market in CORE_MARKETS:
            placement_count += 1

    unique_players = len(player_bet_count)
    if 0 < unique_players < MIN_UNIQUE_PLAYERS:
        logger.warning(
            "Portfolio has only %d unique player(s) — below recommended minimum of %d",
            unique_players, MIN_UNIQUE_PLAYERS,
        )

    dropped = len(all_value_bets) - len(selected)
    if dropped > 0:
        logger.info(
            "Diversification: kept %d of %d value bets (%d dropped, %d unique players)",
            len(selected), len(all_value_bets), dropped, unique_players,
        )

    filtered = {market: [] for market in value_bets_by_market}
    for bet in selected:
        market = bet.pop("_market")
        filtered[market].append(bet)

    for market, bets in value_bets_by_market.items():
        for bet in bets:
            if not bet.get("is_value"):
                filtered[market].append(bet)
        filtered[market].sort(key=lambda x: x.get("ev", 0), reverse=True)

    return filtered


def get_portfolio_summary(value_bets_by_market: dict) -> dict:
    """
    Generate a summary of the portfolio for display on the card.
    Returns stats about concentration, bet distribution, etc.
    """
    all_value = []
    for market, bets in value_bets_by_market.items():
        for bet in bets:
            if bet.get("is_value"):
                all_value.append({**bet, "_market": market})

    if not all_value:
        return {
            "total_value_bets": 0,
            "unique_players": 0,
            "by_market": {},
            "by_player": {},
            "concentration_warning": None,
        }

    by_player = {}
    by_market = {}
    for bet in all_value:
        pk = bet["player_key"]
        market = bet["_market"]
        by_player[pk] = by_player.get(pk, 0) + 1
        by_market[market] = by_market.get(market, 0) + 1

    max_player_bets = max(by_player.values()) if by_player else 0
    max_player = max(by_player, key=by_player.get) if by_player else None

    concentration_warning = None
    if max_player_bets > MAX_BETS_PER_PLAYER:
        concentration_warning = (
            f"High concentration: {max_player} has {max_player_bets} bets "
            f"(max recommended: {MAX_BETS_PER_PLAYER})"
        )

    return {
        "total_value_bets": len(all_value),
        "unique_players": len(by_player),
        "by_market": by_market,
        "by_player": by_player,
        "concentration_warning": concentration_warning,
    }
