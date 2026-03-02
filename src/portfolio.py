"""
Portfolio Diversification Rules

Enforces constraints on bet selection to prevent catastrophic concentration.
These rules are applied as a post-processing step after value bets are identified.

Based on lessons learned:
- Genesis: 11/12 placement bets on 3 players, -6.83u when 2 busted
- Pebble Beach: AI concentrated 87% of units on one player
- Cognizant Classic v4.0: 23 bets, 1-22 record (-16u). No total cap enforced.
"""

import logging

from src import config

logger = logging.getLogger("portfolio")

MAX_BETS_PER_PLAYER = 2
MIN_UNIQUE_PLAYERS = 3
MAX_PLACEMENT_BETS = 6
SPECULATIVE_MARKETS = {"outright", "top5", "frl"}
CORE_MARKETS = {"top10", "top20", "make_cut"}


MARKET_RISK_ORDER = ["top20", "top10", "make_cut", "top5", "outright", "frl"]
SAFER_MARKET_EV_RATIO = 2.0


def _prefer_safer_markets(value_bets_by_market: dict) -> dict:
    """
    When a player has value in multiple markets, keep the safer one
    unless the riskier market's EV is at least 2x higher.

    Prevents the "right player, wrong market" problem (e.g., Keith Mitchell
    T6 finish bet as outright instead of top 10).
    """
    player_bets = {}
    for market, bets in value_bets_by_market.items():
        for bet in bets:
            if not bet.get("is_value") or bet.get("suspicious") or bet.get("ev_capped"):
                continue
            pk = bet["player_key"]
            if pk not in player_bets:
                player_bets[pk] = []
            player_bets[pk].append((market, bet))

    drop_keys = set()
    for pk, entries in player_bets.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda x: MARKET_RISK_ORDER.index(x[0]) if x[0] in MARKET_RISK_ORDER else 99)
        safest_market, safest_bet = entries[0]
        safest_ev = safest_bet.get("ev", 0)
        for market, bet in entries[1:]:
            riskier_ev = bet.get("ev", 0)
            if safest_ev > 0 and riskier_ev < safest_ev * SAFER_MARKET_EV_RATIO:
                drop_keys.add((pk, market))
                logger.info(
                    "Market selection: dropped %s %s (EV %.1f%%) — safer %s bet kept (EV %.1f%%)",
                    bet.get("player_display", pk), market, riskier_ev * 100,
                    safest_market, safest_ev * 100,
                )

    if not drop_keys:
        return value_bets_by_market

    result = {}
    for market, bets in value_bets_by_market.items():
        result[market] = []
        for bet in bets:
            pk = bet.get("player_key")
            if (pk, market) in drop_keys:
                bet_copy = {**bet, "is_value": False}
                result[market].append(bet_copy)
            else:
                result[market].append(bet)
    return result


def enforce_diversification(
    value_bets_by_market: dict,
    field_strength: str = "average",
) -> dict:
    """
    Apply diversification rules to value bets across all markets.

    Takes the raw value_bets dict (keyed by market type, values are lists of bet dicts)
    and returns a filtered version respecting concentration limits.

    Each bet dict must have at minimum: player_key, ev, is_value.
    """
    value_bets_by_market = _prefer_safer_markets(value_bets_by_market)

    max_total = config.MAX_TOTAL_VALUE_BETS
    if field_strength == "weak":
        max_total = config.MAX_TOTAL_VALUE_BETS_WEAK_FIELD

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
        if len(selected) >= max_total:
            logger.info(
                "Diversification: dropped %s %s bet (total cap %d reached)",
                bet.get("player_display", bet["player_key"]), bet["_market"], max_total,
            )
            continue

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
            "Diversification: kept %d of %d value bets (%d dropped, %d unique players, cap %d)",
            len(selected), len(all_value_bets), dropped, unique_players, max_total,
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
