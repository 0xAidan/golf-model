"""
Unified Scoring Module -- Single source of truth for bet outcome determination.

All bet-win/loss logic, dead-heat rules, matchup pushes, and profit
calculations go through this module. No other file should contain its
own scoring logic.

Dead-heat rules (golf sportsbook standard):
  When N players tie at a position that sits on the boundary of a market
  threshold, the payout is reduced. For example, if the top-5 market has
  4 clear finishers inside the threshold and 3 players tied at T5, each
  tied player receives (remaining_spots / num_tied) of the full payout.
  remaining_spots = threshold - (first_tied_position - 1)
  fraction = remaining_spots / num_tied

Matchup rules:
  If both players in a head-to-head matchup finish at the same position,
  the bet is a push (stake returned, profit = 0).
"""

import logging
from typing import Optional

logger = logging.getLogger("scoring")

# Market thresholds: bet_type -> max finish position for a win
MARKET_THRESHOLDS = {
    "outright": 1,
    "win": 1,
    "frl": 1,
    "top5": 5,
    "top_5": 5,
    "top10": 10,
    "top_10": 10,
    "top20": 20,
    "top_20": 20,
    "make_cut": None,  # special handling
}


def count_tied_at_position(finish_pos: int,
                           all_results: list[dict]) -> int:
    """
    Count how many players share the given finish position.

    Uses finish_text (e.g. "T5") to detect ties. If finish_text starts
    with "T", the player is tied. We count all players whose integer
    finish_position equals finish_pos AND whose finish_text starts with "T".

    If finish_text does NOT start with "T", the player is alone at that
    position, so the count is 1.

    Args:
        finish_pos: The integer finish position to check.
        all_results: List of result dicts, each containing at minimum
                     "finish_position" and "finish_text".

    Returns:
        Number of players sharing that position.
    """
    if finish_pos is None:
        return 0

    count = 0
    for r in all_results:
        r_pos = r.get("finish_position")
        r_text = str(r.get("finish_text", "")).strip().upper()
        if r_pos == finish_pos and r_text.startswith("T"):
            count += 1

    if count == 0:
        # No "T" prefix found -- player is alone at this position
        return 1

    return count


def dead_heat_fraction(finish_pos: int,
                       threshold: int,
                       num_tied: int) -> float:
    """
    Calculate the dead-heat payout fraction.

    When players tie at the exact threshold boundary, sportsbooks
    pay a fraction of the full payout:
      remaining_spots = threshold - (finish_pos - 1)
      fraction = remaining_spots / num_tied

    Examples:
      - T5 for top-5 market, 3 players tied at 5:
        remaining = 5 - 4 = 1, fraction = 1/3
      - T4 for top-5 market, 2 players tied at 4:
        remaining = 5 - 3 = 2, fraction = 2/2 = 1.0 (all fit)
      - T10 for top-10 market, 4 players tied at 10:
        remaining = 10 - 9 = 1, fraction = 1/4

    Args:
        finish_pos: Player's integer finish position.
        threshold: Market threshold (e.g., 5 for top-5).
        num_tied: Number of players sharing this position.

    Returns:
        Fraction between 0.0 and 1.0.
    """
    if num_tied <= 0 or finish_pos is None or threshold is None:
        return 1.0

    remaining_spots = threshold - (finish_pos - 1)
    if remaining_spots <= 0:
        return 0.0
    if remaining_spots >= num_tied:
        return 1.0

    return remaining_spots / num_tied


def determine_outcome(bet_type: str,
                      finish_position: Optional[int],
                      finish_text: Optional[str],
                      made_cut: int,
                      all_results: list[dict],
                      opponent_finish: Optional[int] = None) -> dict:
    """
    Determine the outcome of a bet.

    Args:
        bet_type: One of "outright", "win", "frl", "top5", "top_5",
                  "top10", "top_10", "top20", "top_20", "make_cut", "matchup".
        finish_position: Player's integer finish position (None if CUT/WD/DQ).
        finish_text: Raw finish text like "T5", "1", "CUT", "WD".
        made_cut: 1 if player made the cut, 0 otherwise.
        all_results: Full list of result dicts for dead-heat calculation.
        opponent_finish: For matchups, the opponent's integer finish position.

    Returns:
        Dict with:
          "hit": 1 if bet won (or partially won via dead-heat), 0 if lost
          "fraction": 1.0 for clean win, <1.0 for dead-heat, 0.0 for loss
          "is_push": True if matchup tie (stake returned)
    """
    result = {"hit": 0, "fraction": 0.0, "is_push": False}

    # Normalize bet_type to handle both formats (top5 and top_5)
    bt = bet_type.lower().strip()

    # Matchup handling
    if bt == "matchup":
        if finish_position is None:
            # Player missed cut/WD/DQ -- loss unless opponent also missed
            if opponent_finish is None:
                result["is_push"] = True
            return result

        if opponent_finish is None:
            # Opponent missed cut, player finished -- win
            result["hit"] = 1
            result["fraction"] = 1.0
            return result

        if finish_position < opponent_finish:
            result["hit"] = 1
            result["fraction"] = 1.0
        elif finish_position == opponent_finish:
            result["is_push"] = True
        # else: loss (default)
        return result

    # Make cut handling
    if bt == "make_cut":
        if made_cut:
            result["hit"] = 1
            result["fraction"] = 1.0
        return result

    # Position-based markets (outright, top5, top10, top20, frl)
    threshold = MARKET_THRESHOLDS.get(bt)
    if threshold is None:
        logger.warning("Unknown bet type: %s", bet_type)
        return result

    if finish_position is None:
        return result  # CUT/WD/DQ -- loss

    if finish_position > threshold:
        return result  # Outside threshold -- loss

    if finish_position < threshold:
        # Strictly inside threshold -- clean win regardless of ties
        result["hit"] = 1
        result["fraction"] = 1.0
        return result

    # finish_position == threshold -- check for dead-heat
    fin_text_upper = str(finish_text or "").strip().upper()
    is_tied = fin_text_upper.startswith("T")

    if not is_tied:
        # Sole occupant of the threshold position -- clean win
        result["hit"] = 1
        result["fraction"] = 1.0
        return result

    # Dead-heat: tied at the threshold boundary
    num_tied = count_tied_at_position(finish_position, all_results)
    fraction = dead_heat_fraction(finish_position, threshold, num_tied)

    if fraction > 0:
        result["hit"] = 1
        result["fraction"] = round(fraction, 6)
    # else: fraction is 0 meaning all spots are taken, loss

    return result


def compute_profit(hit: int,
                   fraction: float,
                   is_push: bool,
                   odds_decimal: Optional[float],
                   stake: float = 1.0) -> float:
    """
    Calculate profit for a bet accounting for dead-heat and push rules.

    Args:
        hit: 1 if bet won, 0 if lost.
        fraction: Dead-heat fraction (1.0 for clean win, <1.0 for dead-heat).
        is_push: True if bet is a push (stake returned).
        odds_decimal: Decimal odds (e.g., 5.0 for +400).
        stake: Wager amount.

    Returns:
        Profit (positive for wins, negative for losses, 0 for pushes).
    """
    if is_push:
        return 0.0

    if odds_decimal is None:
        return 0.0

    if hit and fraction >= 1.0:
        # Clean win: full payout
        return stake * (odds_decimal - 1.0)
    elif hit and fraction > 0:
        # Dead-heat: fractional payout
        # Dead-heat payout = (stake * fraction * (odds - 1)) - (stake * (1 - fraction))
        # Simplified: stake * (fraction * odds - 1)
        return stake * (fraction * (odds_decimal - 1.0) - (1.0 - fraction))
    else:
        # Loss: lose full stake
        return -stake


def determine_outcome_from_text(finish_text: str,
                                market: str,
                                all_finish_texts: list[str] = None) -> dict:
    """
    Convenience wrapper for backtester: determine outcome from finish_text string.

    Parses finish_text (e.g., "T5", "1", "CUT") and determines the outcome
    for the given market.

    Args:
        finish_text: Raw finish text.
        market: Market name (e.g., "win", "top_5", "top_10").
        all_finish_texts: List of all finish texts in the field (for dead-heat).

    Returns:
        Same dict as determine_outcome.
    """
    if not finish_text:
        return {"hit": 0, "fraction": 0.0, "is_push": False}

    fin = finish_text.strip().upper()
    if fin in ("CUT", "MC", "WD", "W/D", "DQ"):
        return {"hit": 0, "fraction": 0.0, "is_push": False}

    try:
        pos = int(fin.replace("T", ""))
    except ValueError:
        return {"hit": 0, "fraction": 0.0, "is_push": False}

    made_cut = 1

    # Build minimal results list for dead-heat detection
    all_results = []
    if all_finish_texts:
        for ft in all_finish_texts:
            ft_clean = ft.strip().upper()
            if ft_clean in ("CUT", "MC", "WD", "W/D", "DQ"):
                continue
            try:
                ft_pos = int(ft_clean.replace("T", ""))
                all_results.append({
                    "finish_position": ft_pos,
                    "finish_text": ft_clean,
                })
            except ValueError:
                continue
    else:
        # No field data -- can't detect dead-heats, assume clean
        all_results = [{"finish_position": pos, "finish_text": fin}]

    return determine_outcome(market, pos, fin, made_cut, all_results)


def american_to_decimal(price: int) -> Optional[float]:
    """Convert American odds to decimal odds. Returns None for invalid input."""
    if price > 0:
        return 1.0 + price / 100.0
    elif price < 0:
        return 1.0 + 100.0 / abs(price)
    return None  # price == 0 is invalid


def parse_odds_to_decimal(odds_text) -> Optional[float]:
    """
    Parse odds from various formats to decimal.

    Handles: "+400", "-150", 400, -150, "400", etc.
    """
    if odds_text is None:
        return None
    try:
        odds_int = int(str(odds_text).replace("+", ""))
        return american_to_decimal(odds_int)
    except (ValueError, TypeError):
        return None
