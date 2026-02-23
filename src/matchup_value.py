"""
Matchup Value Calculator

Takes real sportsbook matchup odds from DataGolf, scores both players
using composite model data, and finds matchup edges with positive EV.
Only shows matchups that are actually bettable.
"""

import logging
import math

from src.player_normalizer import normalize_name

logger = logging.getLogger("matchup_value")


def _american_to_implied_prob(odds: int) -> float | None:
    """Convert American odds to implied probability (0-1)."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    return None


def _parse_best_odds(matchup: dict) -> tuple[tuple[int, str] | None, tuple[int, str] | None]:
    """Extract the best available odds for each side of a matchup.

    Returns ((best_p1_odds, best_p1_book), (best_p2_odds, best_p2_book)).
    Either tuple can be None if no valid odds found.
    """
    best_p1_odds = None
    best_p1_book = None
    best_p2_odds = None
    best_p2_book = None

    books_data = matchup.get("odds", {})
    if not books_data:
        for key, val in matchup.items():
            if isinstance(val, dict) and (
                key.startswith("book_")
                or key in ("draftkings", "fanduel", "betmgm", "caesars", "bet365", "pinnacle")
            ):
                books_data[key] = val

    for book_name, book_odds in books_data.items():
        if not isinstance(book_odds, dict):
            continue

        p1_price = book_odds.get("p1") or book_odds.get("odds_1") or book_odds.get("player_1")
        p2_price = book_odds.get("p2") or book_odds.get("odds_2") or book_odds.get("player_2")

        if p1_price is not None:
            try:
                p1_val = int(float(p1_price))
                if best_p1_odds is None or p1_val > best_p1_odds:
                    best_p1_odds = p1_val
                    best_p1_book = book_name
            except (ValueError, TypeError):
                pass

        if p2_price is not None:
            try:
                p2_val = int(float(p2_price))
                if best_p2_odds is None or p2_val > best_p2_odds:
                    best_p2_odds = p2_val
                    best_p2_book = book_name
            except (ValueError, TypeError):
                pass

    for field_p1, field_p2 in [("p1_odds", "p2_odds"), ("odds_p1", "odds_p2")]:
        if matchup.get(field_p1) is not None and best_p1_odds is None:
            try:
                best_p1_odds = int(float(matchup[field_p1]))
                best_p1_book = "datagolf"
            except (ValueError, TypeError):
                pass
        if matchup.get(field_p2) is not None and best_p2_odds is None:
            try:
                best_p2_odds = int(float(matchup[field_p2]))
                best_p2_book = "datagolf"
            except (ValueError, TypeError):
                pass

    p1 = (best_p1_odds, best_p1_book) if best_p1_odds is not None else None
    p2 = (best_p2_odds, best_p2_book) if best_p2_odds is not None else None
    return p1, p2


def find_matchup_value_bets(composite_results: list[dict],
                             matchup_odds: list[dict],
                             ev_threshold: float = 0.05,
                             tournament_id: int = None) -> list[dict]:
    """
    Find value in real sportsbook matchups using model composite scores.

    composite_results: from composite.compute_composite() — sorted list with
        player_key, player_display, composite, form, course_fit, momentum
    matchup_odds: from datagolf.fetch_matchup_odds() — list of matchup dicts
    ev_threshold: minimum EV to flag as value
    tournament_id: for adaptation state lookup

    Returns list of matchup value bets sorted by EV descending.
    """
    adaptation = None
    if tournament_id:
        try:
            from src.adaptation import get_adaptation_state
            adaptation = get_adaptation_state("matchup")
        except Exception:
            adaptation = None

    if adaptation and adaptation.get("suppress"):
        return []

    if adaptation and adaptation.get("ev_threshold") is not None:
        ev_threshold = max(ev_threshold, adaptation["ev_threshold"])

    composite_lookup = {r["player_key"]: r for r in composite_results}

    value_bets = []

    for matchup in matchup_odds:
        p1_name = matchup.get("p1_player_name") or matchup.get("player_1", {}).get("player_name", "")
        p2_name = matchup.get("p2_player_name") or matchup.get("player_2", {}).get("player_name", "")

        if not p1_name or not p2_name:
            continue

        p1_key = normalize_name(p1_name)
        p2_key = normalize_name(p2_name)

        p1_data = composite_lookup.get(p1_key)
        p2_data = composite_lookup.get(p2_key)

        if not p1_data or not p2_data:
            continue

        p1_best, p2_best = _parse_best_odds(matchup)

        composite_gap = p1_data["composite"] - p2_data["composite"]
        if composite_gap == 0:
            continue

        # Pick the player our model favors
        if composite_gap > 0:
            pick_data, opp_data = p1_data, p2_data
            pick_odds_pair = p1_best
        else:
            pick_data, opp_data = p2_data, p1_data
            pick_odds_pair = p2_best

        if pick_odds_pair is None:
            continue

        pick_odds, pick_book = pick_odds_pair

        implied_prob = _american_to_implied_prob(pick_odds)
        if not implied_prob or implied_prob <= 0:
            continue

        # Model win probability via sigmoid on composite gap
        gap = abs(composite_gap)
        model_win_prob = 1.0 / (1.0 + math.exp(-gap / 15.0))

        ev = (model_win_prob / implied_prob) - 1.0

        if ev < ev_threshold:
            continue

        # Gaps from the pick's perspective
        pick_form = pick_data.get("form", 50)
        opp_form = opp_data.get("form", 50)
        pick_cf = pick_data.get("course_fit", 50)
        opp_cf = opp_data.get("course_fit", 50)
        form_gap = pick_form - opp_form
        course_fit_gap = pick_cf - opp_cf

        reasons = []
        if abs(course_fit_gap) > 5:
            sign = "+" if course_fit_gap > 0 else ""
            reasons.append(f"course fit {sign}{course_fit_gap:.0f}")
        if abs(form_gap) > 5:
            sign = "+" if form_gap > 0 else ""
            reasons.append(f"form {sign}{form_gap:.0f}")

        stake_mult = adaptation["stake_multiplier"] if adaptation else 1.0

        value_bets.append({
            "pick": pick_data["player_display"],
            "pick_key": pick_data["player_key"],
            "opponent": opp_data["player_display"],
            "opponent_key": opp_data["player_key"],
            "odds": pick_odds,
            "book": pick_book,
            "model_win_prob": round(model_win_prob, 4),
            "implied_prob": round(implied_prob, 4),
            "ev": round(ev, 4),
            "ev_pct": f"{ev * 100:.1f}%",
            "composite_gap": round(gap, 1),
            "form_gap": round(form_gap, 1),
            "course_fit_gap": round(course_fit_gap, 1),
            "reason": "; ".join(reasons) if reasons else f"composite +{gap:.0f}",
            "adaptation_state": adaptation["state"] if adaptation else "normal",
            "stake_multiplier": stake_mult,
        })

    value_bets.sort(key=lambda x: x["ev"], reverse=True)
    return value_bets
