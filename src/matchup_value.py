"""
Matchup Value Calculator

Takes real sportsbook matchup odds from DataGolf, scores both players
using composite model data, and finds matchup edges with positive EV.
Only shows matchups that are actually bettable.
"""

import logging
import math
import time

from src.player_normalizer import normalize_name
from src import config, db
from src.odds import american_to_implied_prob

logger = logging.getLogger("matchup_value")

_platt_cache = None
_platt_cache_time = 0

def _get_platt_params() -> tuple[float, float]:
    """Read latest Platt A,B from matchup_calibration table, or use config defaults."""
    global _platt_cache, _platt_cache_time
    now = time.time()
    if _platt_cache and (now - _platt_cache_time) < config.PLATT_CACHE_TTL:
        return _platt_cache
    try:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT a_param, b_param FROM matchup_calibration ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            _platt_cache = (float(row["a_param"]), float(row["b_param"]))
            _platt_cache_time = now
            return _platt_cache
    except Exception:
        logger.warning("Platt params DB fetch failed, using config defaults", exc_info=True)
    return (config.MATCHUP_PLATT_A, config.MATCHUP_PLATT_B)


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


def _parse_book_odds(matchup: dict, book: str) -> tuple[int | None, int | None]:
    """Get (p1_odds, p2_odds) for a single book. Returns (None, None) if book doesn't have both sides."""
    books_data = matchup.get("odds", {})
    if not books_data:
        for key, val in matchup.items():
            if isinstance(val, dict) and (
                key.startswith("book_")
                or key.lower() in ("draftkings", "fanduel", "betmgm", "caesars", "bet365", "pinnacle")
            ):
                books_data[key] = val
    book_lower = book.lower()
    for book_name, book_odds in books_data.items():
        if not isinstance(book_odds, dict) or book_name.lower() != book_lower:
            continue
        p1_price = book_odds.get("p1") or book_odds.get("odds_1") or book_odds.get("player_1")
        p2_price = book_odds.get("p2") or book_odds.get("odds_2") or book_odds.get("player_2")
        try:
            p1_val = int(float(p1_price)) if p1_price is not None else None
            p2_val = int(float(p2_price)) if p2_price is not None else None
            if p1_val is not None and p2_val is not None:
                return (p1_val, p2_val)
        except (ValueError, TypeError):
            pass
        return (None, None)
    return (None, None)


def find_matchup_value_bets(composite_results: list[dict],
                             matchup_odds: list[dict],
                             ev_threshold: float = 0.05,
                             tournament_id: int = None,
                             required_book: str | None = None) -> list[dict]:
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
        except Exception as e:
            logger.warning("Adaptation state unavailable for matchup: %s", e)
            adaptation = None

    if adaptation and adaptation.get("suppress"):
        return []

    if adaptation and adaptation.get("ev_threshold") is not None:
        ev_threshold = max(ev_threshold, adaptation["ev_threshold"])

    composite_lookup = {r["player_key"]: r for r in composite_results}

    dg_pairings = {}
    try:
        from src.datagolf import fetch_dg_matchup_all_pairings
        dg_pairings = fetch_dg_matchup_all_pairings()
        if dg_pairings:
            logger.info("Loaded %d DG matchup pairings for blending", len(dg_pairings))
    except Exception as e:
        logger.warning("DG matchup pairings unavailable (using model-only): %s", e)

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

        if required_book:
            p1_odds, p2_odds = _parse_book_odds(matchup, required_book)
            if p1_odds is None or p2_odds is None:
                continue
            p1_best, p2_best = (p1_odds, required_book), (p2_odds, required_book)
        else:
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

        implied_prob = american_to_implied_prob(pick_odds)
        if not implied_prob or implied_prob <= 0:
            continue

        # Model win probability via Platt-style sigmoid: P(win) = 1/(1+exp(A*gap+B))
        gap = abs(composite_gap)
        A, B = _get_platt_params()
        platt_win_prob = 1.0 / (1.0 + math.exp(A * gap + B))

        # Blend with DG's own matchup model probability if available
        model_win_prob = platt_win_prob
        if dg_pairings:
            dg_pair = dg_pairings.get((pick_data["player_key"], opp_data["player_key"]))
            if not dg_pair:
                dg_pair_rev = dg_pairings.get((opp_data["player_key"], pick_data["player_key"]))
                if dg_pair_rev:
                    dg_pair = {"p1_win_prob": dg_pair_rev["p2_win_prob"], "p2_win_prob": dg_pair_rev["p1_win_prob"]}
            if dg_pair:
                dg_prob = dg_pair["p1_win_prob"]
                model_win_prob = (
                    config.DG_MATCHUP_BLEND_WEIGHT * dg_prob
                    + config.MODEL_MATCHUP_BLEND_WEIGHT * platt_win_prob
                )
                if config.REQUIRE_DG_MODEL_AGREEMENT:
                    if (dg_prob > 0.5) != (platt_win_prob > 0.5):
                        continue

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

        ev_pct = ev * 100
        if ev_pct >= config.MATCHUP_TIER_STRONG_EV_PCT and gap > config.MATCHUP_TIER_STRONG_GAP:
            tier = "STRONG"
        elif ev_pct >= config.MATCHUP_TIER_GOOD_EV_PCT and gap > config.MATCHUP_TIER_GOOD_GAP:
            tier = "GOOD"
        else:
            tier = "LEAN"

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
            "tier": tier,
        })

    value_bets.sort(key=lambda x: x["ev"], reverse=True)

    # Per-player exposure cap: limit how many matchup bets feature the same player (WD protection)
    max_exposure = getattr(config, "MATCHUP_MAX_PLAYER_EXPOSURE", 3)
    player_counts: dict[str, int] = {}
    capped: list[dict] = []
    for bet in value_bets:
        pk = bet["pick_key"]
        ok = bet["opponent_key"]
        if player_counts.get(pk, 0) >= max_exposure or player_counts.get(ok, 0) >= max_exposure:
            continue
        player_counts[pk] = player_counts.get(pk, 0) + 1
        player_counts[ok] = player_counts.get(ok, 0) + 1
        capped.append(bet)
    value_bets = capped[: config.MATCHUP_CAP]
    return value_bets
