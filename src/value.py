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

import os

from src.odds import american_to_implied_prob, american_to_decimal, is_valid_odds
from src.player_normalizer import normalize_name
from src import db

# Default EV threshold: 2% for sharp books (bet365, Pinnacle).
# Override via env var EV_THRESHOLD (e.g. "0.05" for 5%).
DEFAULT_EV_THRESHOLD = float(os.environ.get("EV_THRESHOLD", "0.02"))

MARKET_EV_THRESHOLDS = {
    "outright": 0.05,
    "top5": 0.05,
    "top10": 0.02,
    "top20": 0.02,
    "frl": 0.05,
    "make_cut": 0.02,
}

# Maximum credible EV. Real sports betting edges are 2-20%.
# Anything above this almost certainly indicates bad data, not a real edge.
MAX_CREDIBLE_EV = 2.0  # 200%

# Minimum market implied probability to trust odds data.
# If market prob is below this, odds are likely corrupted/stale.
MIN_MARKET_PROB = 0.005  # 0.5%

# Market-specific maximum reasonable American odds.
# Anything above these thresholds for a given bet type is almost certainly
# corrupt data (e.g. +500000 outright that generates 17,000% EV).
MAX_REASONABLE_ODDS = {
    "outright": 30000,
    "top5": 5000,
    "top10": 3000,
    "top20": 1500,
    "frl": 10000,
    "make_cut": 500,
}


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
    Convert a composite score to a properly normalized probability.

    Uses true softmax normalization so probabilities sum to the correct
    total for each bet type:
      - outright: sum = 1.0 (one winner)
      - top5: sum = 5.0
      - top10: sum = 10.0
      - top20: sum = 20.0
      - make_cut: sum = 0.65 * field_size
      - frl: sum = 1.0 (one first-round leader)

    This is a fallback — DG calibrated probabilities are preferred.
    """
    import math

    if not all_scores:
        return 0.0

    field_size = len(all_scores)
    if field_size == 0:
        return 0.0

    # Temperature controls how peaked the distribution is.
    # Higher temperature = more uniform (wider markets).
    temp_by_type = {
        "outright": 8.0,
        "top5": 10.0,
        "top10": 12.0,
        "top20": 15.0,
        "make_cut": 20.0,
        "frl": 7.0,
    }
    temp = temp_by_type.get(bet_type, 12.0)

    # Target sum: how many "winners" in this market
    target_sum_by_type = {
        "outright": 1.0,
        "top5": 5.0,
        "top10": 10.0,
        "top20": 20.0,
        "make_cut": 0.65 * field_size,
        "frl": 1.0,
    }
    target_sum = target_sum_by_type.get(bet_type, 10.0)

    # True softmax: exp(score / temperature) for each player
    # Subtract max for numerical stability (prevents overflow)
    max_score = max(all_scores)
    exp_scores = [math.exp((s - max_score) / temp) for s in all_scores]
    exp_total = sum(exp_scores)

    if exp_total == 0:
        return target_sum / max(field_size, 1)

    # Compute ALL probabilities, clamp, then renormalize to preserve target_sum.
    # This prevents individual clamping from breaking the probability sum.
    raw_probs = [(math.exp((s - max_score) / temp) / exp_total) * target_sum
                 for s in all_scores]
    clamped = [max(0.001, min(0.95, p)) for p in raw_probs]
    clamped_sum = sum(clamped)

    # Find this player's index and return their renormalized probability
    try:
        player_idx = all_scores.index(composite_score)
    except ValueError:
        # Composite score not found in all_scores -- compute directly
        player_exp = math.exp((composite_score - max_score) / temp)
        prob = (player_exp / exp_total) * target_sum
        return max(0.001, min(0.95, prob))

    if clamped_sum > 0:
        return clamped[player_idx] * (target_sum / clamped_sum)
    return target_sum / max(field_size, 1)


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
        # We requested percent format, so values could be 0.05 (5%) or 5.0 (5%).
        # Heuristic: if value > 1.0, it's almost certainly a percentage.
        # Secondary check: if ALL values for a player sum > 2.0, they're percentages.
        prob = val / 100.0 if val > 1.0 else val
        # Safety: probabilities must be in (0, 1)
        if prob > 1.0:
            prob = prob / 100.0
        prob = max(0.0001, min(0.9999, prob))

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
                    ev_threshold: float = None,
                    tournament_id: int = None) -> list[dict]:
    """
    Compare model scores to market odds and find value.

    composite_results: from composite.compute_composite()
    odds_by_player: from odds.get_best_odds() (keyed by lowercase name)
    bet_type: 'outright', 'top5', 'top10', 'top20'
    ev_threshold: minimum EV to flag as value (default from EV_THRESHOLD env or 2%)
    tournament_id: if provided, uses DG calibrated probabilities

    Probability priority:
      1. DG course-history model probs
      2. DG baseline model probs
      3. Softmax approximation from composite scores

    Returns list of value bets sorted by EV (best first).
    """
    if ev_threshold is None:
        ev_threshold = MARKET_EV_THRESHOLDS.get(bet_type, DEFAULT_EV_THRESHOLD)

    BLEND_WEIGHTS = {
        "outright": {"dg": 0.90, "model": 0.10},
        "top5":     {"dg": 0.85, "model": 0.15},
        "top10":    {"dg": 0.85, "model": 0.15},
        "top20":    {"dg": 0.80, "model": 0.20},
        "frl":      {"dg": 0.90, "model": 0.10},
        "make_cut": {"dg": 0.80, "model": 0.20},
    }
    blend_cfg = BLEND_WEIGHTS.get(bet_type, {"dg": 0.85, "model": 0.15})
    DG_BLEND_WEIGHT = blend_cfg["dg"]
    MODEL_BLEND_WEIGHT = blend_cfg["model"]

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

        # Skip entries with invalid/extreme odds for this market type
        if not is_valid_odds(odds_entry.get("best_price"), bet_type=bet_type):
            continue

        # Skip entries where market probability is suspiciously low
        # (indicates bad/stale odds data, not a real opportunity)
        if odds_entry.get("implied_prob", 0) < MIN_MARKET_PROB:
            continue

        # Get model probability — priority chain with blending
        #
        # Instead of using DG probs exclusively when available, we now
        # blend DG probability (well-calibrated) with our own composite-based
        # probability (captures course_fit, weather, momentum signals that
        # DG may not weight the same way).
        #
        # Blend ratio varies by market (see BLEND_WEIGHTS above).
        # DG is preferred; model adds course_fit, weather, momentum signals.
        dg_prob_raw = None
        prob_source = "softmax"

        # 1. DG calibrated probabilities from pre-tournament predictions (best)
        if pkey in dg_probs:
            dg_candidate = _get_best_prob(dg_probs[pkey], bet_type)
            if dg_candidate and dg_candidate > 0:
                dg_prob_raw = dg_candidate
                prob_source = "datagolf_ch" if f"{bet_type}_ch" in dg_probs[pkey] else "datagolf"

        # 2. DG model prices from odds endpoint (for FRL and other markets)
        if dg_prob_raw is None:
            dg_model_prices = odds_entry.get("dg_model_prices", [])
            if dg_model_prices:
                for label in ["DG-CH", "DG-Base"]:
                    for dp in dg_model_prices:
                        if dp["bookmaker"] == label and dp.get("implied_prob"):
                            dg_prob_raw = dp["implied_prob"]
                            prob_source = "datagolf_ch" if label == "DG-CH" else "datagolf"
                            break
                    if dg_prob_raw is not None:
                        break

        # 3. Compute our own softmax probability from composite scores
        softmax_prob = model_score_to_prob(r["composite"], all_scores, bet_type)

        # 4. Blend or fall back
        if dg_prob_raw is not None:
            model_prob = DG_BLEND_WEIGHT * dg_prob_raw + MODEL_BLEND_WEIGHT * softmax_prob
            prob_source = f"blend({prob_source}+softmax)"
        else:
            model_prob = softmax_prob
            prob_source = "softmax"

        market_prob = odds_entry["implied_prob"]
        ev = compute_ev(model_prob, odds_entry["best_price"])

        # Also capture DG prob for prediction_log (even if not used for EV)
        dg_prob_for_log = None
        if pkey in dg_probs:
            dg_prob_for_log = _get_best_prob(dg_probs[pkey], bet_type)

        # Check if better odds exist at another book
        best_available_price = odds_entry.get("best_price")
        best_available_book = odds_entry.get("best_book")
        better_odds_note = None

        # Find the actual best across all books (might differ from preferred)
        all_books = odds_entry.get("all_books", [])
        for ab in all_books:
            if ab["price"] > best_available_price:
                best_available_price = ab["price"]
                best_available_book = ab["bookmaker"]

        if best_available_price > odds_entry["best_price"]:
            better_price_str = f"+{best_available_price}" if best_available_price > 0 else str(best_available_price)
            better_odds_note = f"{better_price_str} @ {best_available_book}"

        # Cap EV at a credible maximum — anything higher is data error
        if ev > MAX_CREDIBLE_EV:
            ev = MAX_CREDIBLE_EV
            ev_capped = True
        else:
            ev_capped = False

        # Flag if model prob is wildly different from market prob
        # (>10x difference suggests one side has bad data)
        prob_ratio = model_prob / max(market_prob, 0.0001)
        suspicious = prob_ratio > 10.0 or prob_ratio < 0.1

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
            "best_available_odds": best_available_price,
            "best_available_book": best_available_book,
            "better_odds_note": better_odds_note,
            "ev": round(ev, 4),
            "ev_pct": f"{ev * 100:.1f}%",
            "ev_capped": ev_capped,
            "is_value": ev >= ev_threshold and not ev_capped,
            "needs_review": ev > 1.0,
            "suspicious": suspicious,
            "prob_source": prob_source,
        })

    # Sort by EV descending
    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    return value_bets


def compute_run_quality(value_bets_by_market: dict) -> dict:
    """
    Compute a quality score for the entire prediction run.

    Flags runs with corrupt/suspicious data to prevent them from being
    logged to the picks table. Returns a dict with pass/fail status and issues.
    """
    all_bets = [b for bets in value_bets_by_market.values() for b in bets]
    if not all_bets:
        return {"score": 0.0, "issues": ["no bets computed"], "pass": False}

    total = len(all_bets)
    suspicious_count = sum(1 for b in all_bets if b.get("suspicious"))
    capped_count = sum(1 for b in all_bets if b.get("ev_capped"))
    needs_review_count = sum(1 for b in all_bets if b.get("needs_review"))
    avg_abs_ev = sum(abs(b.get("ev", 0)) for b in all_bets) / total

    suspicious_pct = suspicious_count / total
    capped_pct = capped_count / total

    issues = []
    if suspicious_pct > 0.10:
        issues.append(f"{suspicious_pct:.0%} of entries have suspicious model/market divergence")
    if capped_pct > 0.20:
        issues.append(f"{capped_pct:.0%} of entries had EV capped at maximum")
    if avg_abs_ev > 0.50:
        issues.append(f"Average |EV| = {avg_abs_ev:.0%} (likely corrupt odds data)")
    if needs_review_count > total * 0.15:
        issues.append(f"{needs_review_count}/{total} entries need review (EV > 100%)")

    quality_score = max(0.0, 1.0 - suspicious_pct - capped_pct * 0.5)
    passed = len(issues) == 0

    return {
        "score": round(quality_score, 3),
        "issues": issues,
        "pass": passed,
        "stats": {
            "total_bets": total,
            "suspicious": suspicious_count,
            "capped": capped_count,
            "needs_review": needs_review_count,
            "avg_abs_ev": round(avg_abs_ev, 4),
        }
    }
