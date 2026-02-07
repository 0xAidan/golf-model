"""
Value Calculator

Compare model-implied probabilities to market odds to find mispriced bets.

Expected Value (EV) = (model_prob * decimal_odds) - 1
  Positive EV = the bet is underpriced by the market
  Negative EV = overpriced

We also compute a "value rating" for quick scanning.
"""

from src.odds import american_to_implied_prob, american_to_decimal
from src.player_normalizer import normalize_name


def compute_ev(model_prob: float, american_odds: int) -> float:
    """
    Compute expected value of a bet.

    model_prob: our model's probability (0-1)
    american_odds: e.g. +4000, -150
    Returns: EV as a proportion (0.15 = 15% edge)
    """
    decimal = american_to_decimal(american_odds)
    return (model_prob * decimal) - 1.0


def model_score_to_prob(composite_score: float, all_scores: list[float],
                        bet_type: str = "top20") -> float:
    """
    Convert a composite score to an approximate probability for a given bet type.

    Uses a softmax-like approach: player's share of total "talent"
    in the field, then calibrate based on bet type.

    This is approximate — the sim probabilities from Betsperts are more
    accurate when available. This fills in when we don't have sim data.
    """
    if not all_scores:
        return 0.0

    # Shift scores to be positive (min score → small positive)
    min_score = min(all_scores)
    shifted = [s - min_score + 1.0 for s in all_scores]
    player_shifted = composite_score - min_score + 1.0

    # Temperature controls how peaked the distribution is
    # Higher temp = more spread out
    temp_by_type = {
        "outright": 0.8,   # Very peaked — only a few can win
        "top5": 1.2,
        "top10": 1.6,
        "top20": 2.0,       # More spread out
        "make_cut": 3.0,
    }
    temp = temp_by_type.get(bet_type, 1.5)

    # Power-based probability
    powered = [s ** temp for s in shifted]
    total = sum(powered)
    base_prob = (player_shifted ** temp) / total if total > 0 else 0.0

    # Calibrate: for top20, roughly 20/field_size of players finish top 20
    field_size = len(all_scores)
    calibration = {
        "outright": 1.0 / field_size * 5.0,  # ~5x base rate for top player
        "top5": 5.0 / field_size * 3.0,
        "top10": 10.0 / field_size * 2.5,
        "top20": 20.0 / field_size * 2.0,
        "make_cut": 0.65 * 1.5,  # ~65% make cut baseline
    }
    cal = calibration.get(bet_type, 1.0)

    # Scale so the sum of all probs roughly matches the base rate
    prob = base_prob * cal * field_size
    return max(0.001, min(0.99, prob))


def find_value_bets(composite_results: list[dict],
                    odds_by_player: dict,
                    bet_type: str = "top20",
                    ev_threshold: float = 0.05) -> list[dict]:
    """
    Compare model scores to market odds and find value.

    composite_results: from composite.compute_composite()
    odds_by_player: from odds.get_best_odds() (keyed by lowercase name)
    bet_type: 'outright', 'top5', 'top10', 'top20'
    ev_threshold: minimum EV to flag as value (0.05 = 5%)

    Returns list of value bets sorted by EV (best first).
    """
    all_scores = [r["composite"] for r in composite_results]

    value_bets = []
    for r in composite_results:
        pkey = r["player_key"]
        pdisp = r["player_display"]

        # Try to match player to odds (by normalized name or display name)
        odds_entry = None
        for odds_name, oe in odds_by_player.items():
            if normalize_name(odds_name) == pkey or odds_name == pdisp.lower():
                odds_entry = oe
                break

        if not odds_entry:
            continue

        # Get model probability
        # Prefer sim probability if available
        sim_prob = r.get("details", {}).get("form_components", {}).get("sim")
        if sim_prob and sim_prob > 0 and bet_type in ("outright",):
            model_prob = sim_prob / 100.0  # sim score is 0-100
        else:
            model_prob = model_score_to_prob(r["composite"], all_scores, bet_type)

        market_prob = odds_entry["implied_prob"]
        ev = compute_ev(model_prob, odds_entry["best_price"])

        value_bets.append({
            "player_key": pkey,
            "player_display": pdisp,
            "rank": r["rank"],
            "composite": r["composite"],
            "course_fit": r["course_fit"],
            "form": r["form"],
            "momentum": r["momentum"],
            "model_prob": round(model_prob, 4),
            "market_prob": round(market_prob, 4),
            "best_odds": odds_entry["best_price"],
            "best_book": odds_entry["best_book"],
            "ev": round(ev, 4),
            "ev_pct": f"{ev * 100:.1f}%",
            "is_value": ev >= ev_threshold,
        })

    # Sort by EV descending
    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    return value_bets
