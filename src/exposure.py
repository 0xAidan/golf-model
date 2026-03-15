"""
Portfolio exposure management.

Caps per-player (5%) and per-tournament (12%) effective exposure.
When feature flag exposure_caps is on, filters value bets that exceed caps.
"""

import logging
from copy import deepcopy
from typing import Optional

from src.feature_flags import is_enabled

logger = logging.getLogger(__name__)

PER_PLAYER_CAP_PCT = 0.05   # 5% of bankroll per player
PER_TOURNAMENT_CAP_PCT = 0.12  # 12% per tournament
MIN_BETS_AFTER_CAP = 3


def compute_exposure(
    value_bets_by_type: dict,
    stake_per_bet: float = 1.0,
    bankroll: Optional[float] = None,
) -> dict:
    """
    Compute per-player and per-tournament exposure from value_bets_by_type.

    Returns: {
        "per_player": {player_key: fraction of bankroll or units},
        "tournament_total": float,
        "over_exposed_players": [player_key, ...],
        "tournament_over": bool,
    }
    """
    per_player = {}
    tournament_total = 0.0
    for bet_type, bets in value_bets_by_type.items():
        for bet in bets:
            if not bet.get("is_value"):
                continue
            pk = bet.get("player_key")
            if not pk:
                continue
            units = stake_per_bet * bet.get("stake_multiplier", 1.0)
            per_player[pk] = per_player.get(pk, 0.0) + units
            tournament_total += units

    if bankroll and bankroll > 0:
        per_player = {k: v / bankroll for k, v in per_player.items()}
        tournament_total = tournament_total / bankroll
    else:
        # No bankroll: use raw units; caps not comparable
        pass

    over_players = [pk for pk, v in per_player.items() if v > PER_PLAYER_CAP_PCT]
    tournament_over = (bankroll and bankroll > 0) and tournament_total > PER_TOURNAMENT_CAP_PCT

    return {
        "per_player": per_player,
        "tournament_total": tournament_total,
        "over_exposed_players": over_players,
        "tournament_over": tournament_over,
    }


def filter_by_exposure(
    value_bets_by_type: dict,
    stake_per_bet: float = 1.0,
    bankroll: Optional[float] = None,
) -> tuple[dict, list[str]]:
    """
    Return a copy of value_bets_by_type with bets removed so caps are not exceeded.
    Removes lowest-EV bets first. When exposure_caps flag is off, returns unchanged.
    """
    if not is_enabled("exposure_caps"):
        return value_bets_by_type, []

    if not bankroll or bankroll <= 0:
        return value_bets_by_type, []

    warnings = []
    result = deepcopy(value_bets_by_type)

    def _exposure(result_copy: dict) -> dict:
        return compute_exposure(result_copy, stake_per_bet, bankroll)

    while True:
        exp = _exposure(result)
        over = set(exp["over_exposed_players"])
        tour_over = exp["tournament_over"]
        if not over and not tour_over:
            break

        # Collect all value bets as (bet_type, index, bet, ev)
        candidates = []
        for bet_type, bets in result.items():
            for i, bet in enumerate(bets):
                if not bet.get("is_value"):
                    continue
                pk = bet.get("player_key")
                if pk in over or tour_over:
                    candidates.append((bet_type, i, bet, bet.get("ev", 0.0)))
        if not candidates:
            break
        # Remove the one with lowest EV
        candidates.sort(key=lambda x: x[3])
        bt, idx, _b, _ev = candidates[0]
        result[bt][idx] = {**_b, "is_value": False}
        logger.debug("Exposure cap: disabled bet %s %s (ev=%.2f)", bt, _b.get("player_key"), _ev)

    exp = _exposure(result)
    if exp["over_exposed_players"] or exp["tournament_over"]:
        warnings.append("Exposure caps: some exposure remains over limit (cannot reduce further).")
    n_value = sum(1 for bets in result.values() for b in bets if b.get("is_value"))
    if n_value < MIN_BETS_AFTER_CAP and n_value < sum(1 for bets in value_bets_by_type.values() for b in bets if b.get("is_value")):
        warnings.append(f"After exposure filter, fewer than {MIN_BETS_AFTER_CAP} value bets remain.")

    return result, warnings
