"""
Value Calculator

Compare model-implied probabilities to market odds to find mispriced bets.

Expected Value (EV) = (model_prob * decimal_odds) - 1
  Positive EV = the bet is underpriced by the market
  Negative EV = overpriced

Probability priority:
  1. Data Golf course-history model (best calibrated)
  2. Data Golf baseline model
  3. Betsperts sim probabilities
  4. Softmax approximation from composite scores (fallback)
"""

from src.odds import american_to_implied_prob, american_to_decimal
from src.player_normalizer import normalize_name
from src import db


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


def _get_dg_probabilities(tournament_id: int) -> dict:
    """
    Get Data Golf pre-tournament probabilities for all players.

    Returns {player_key: {bet_type: probability}} where probability is 0-1.
    Prefers course-history model; falls back to baseline.
    """
    sim_metrics = db.get_metrics_by_category(tournament_id, "sim")
    player_probs = {}

    for m in sim_metrics:
        pk = m["player_key"]
        if pk not in player_probs:
            player_probs[pk] = {}

        name = m["metric_name"]
        val = m["metric_value"]
        if val is None:
            continue

        # DG probabilities from preds/pre-tournament are stored as decimals (0-1)
        # or percentages (0-100) depending on odds_format.
        # We requested percent format, so values might be like 0.05 (5%) or 5.0 (5%).
        # Normalize: if > 1, assume it's a percentage; divide by 100.
        prob = val / 100.0 if val > 1.0 else val

        # Map metric names to bet types
        # Prefer course-history versions when available
        if "CH" in name:  # Course-History model (better)
            if "Win" in name:
                player_probs[pk]["outright_ch"] = prob
            elif "Top 5" in name:
                player_probs[pk]["top5_ch"] = prob
            elif "Top 10" in name:
                player_probs[pk]["top10_ch"] = prob
            elif "Top 20" in name:
                player_probs[pk]["top20_ch"] = prob
            elif "Make Cut" in name or "Cut" in name:
                player_probs[pk]["make_cut_ch"] = prob
        else:
            if "Win" in name:
                player_probs[pk]["outright"] = prob
            elif "Top 5" in name:
                player_probs[pk]["top5"] = prob
            elif "Top 10" in name:
                player_probs[pk]["top10"] = prob
            elif "Top 20" in name:
                player_probs[pk]["top20"] = prob
            elif "Make Cut" in name or "Cut" in name:
                player_probs[pk]["make_cut"] = prob

    return player_probs


def _get_best_prob(player_probs: dict, bet_type: str) -> float | None:
    """
    Get the best available probability for a bet type.

    Priority: course-history model > baseline model > None.
    """
    if not player_probs:
        return None

    # Check course-history version first
    ch_key = f"{bet_type}_ch"
    if ch_key in player_probs and player_probs[ch_key] > 0:
        return player_probs[ch_key]

    # Fall back to baseline
    if bet_type in player_probs and player_probs[bet_type] > 0:
        return player_probs[bet_type]

    return None


def find_value_bets(composite_results: list[dict],
                    odds_by_player: dict,
                    bet_type: str = "top20",
                    ev_threshold: float = 0.05,
                    tournament_id: int = None) -> list[dict]:
    """
    Compare model scores to market odds and find value.

    composite_results: from composite.compute_composite()
    odds_by_player: from odds.get_best_odds() (keyed by lowercase name)
    bet_type: 'outright', 'top5', 'top10', 'top20'
    ev_threshold: minimum EV to flag as value (0.05 = 5%)
    tournament_id: if provided, uses DG calibrated probabilities

    Probability priority:
      1. DG course-history model probs
      2. DG baseline model probs
      3. Softmax approximation from composite scores

    Returns list of value bets sorted by EV (best first).
    """
    all_scores = [r["composite"] for r in composite_results]

    # Load DG probabilities if tournament_id is available
    dg_probs = {}
    if tournament_id:
        dg_probs = _get_dg_probabilities(tournament_id)

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

        # Get model probability — priority chain
        model_prob = None
        prob_source = "softmax"

        # 1. DG calibrated probabilities (best)
        if pkey in dg_probs:
            dg_prob = _get_best_prob(dg_probs[pkey], bet_type)
            if dg_prob and dg_prob > 0:
                model_prob = dg_prob
                prob_source = "datagolf_ch" if f"{bet_type}_ch" in dg_probs[pkey] else "datagolf"

        # 2. Softmax fallback from composite scores
        if model_prob is None:
            model_prob = model_score_to_prob(r["composite"], all_scores, bet_type)
            prob_source = "softmax"

        market_prob = odds_entry["implied_prob"]
        ev = compute_ev(model_prob, odds_entry["best_price"])

        # Also capture DG prob for prediction_log (even if not used for EV)
        dg_prob_for_log = None
        if pkey in dg_probs:
            dg_prob_for_log = _get_best_prob(dg_probs[pkey], bet_type)

        value_bets.append({
            "player_key": pkey,
            "player_display": pdisp,
            "rank": r["rank"],
            "composite": r["composite"],
            "course_fit": r["course_fit"],
            "form": r["form"],
            "momentum": r["momentum"],
            "model_prob": round(model_prob, 4),
            "dg_prob": round(dg_prob_for_log, 4) if dg_prob_for_log else None,
            "market_prob": round(market_prob, 4),
            "best_odds": odds_entry["best_price"],
            "best_book": odds_entry["best_book"],
            "ev": round(ev, 4),
            "ev_pct": f"{ev * 100:.1f}%",
            "is_value": ev >= ev_threshold,
            "prob_source": prob_source,
        })

    # Sort by EV descending
    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    return value_bets
