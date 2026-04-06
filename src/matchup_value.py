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


def _iter_book_odds(matchup: dict) -> list[tuple[str, int, int]]:
    """Return all books that have valid two-sided prices for a matchup."""
    books: list[tuple[str, int, int]] = []
    books_data = matchup.get("odds", {})
    if not books_data:
        for key, val in matchup.items():
            if isinstance(val, dict) and (
                key.startswith("book_")
                or key.lower() in ("draftkings", "fanduel", "betmgm", "caesars", "bet365", "pinnacle")
            ):
                books_data[key] = val

    for book_name, book_odds in books_data.items():
        if not isinstance(book_odds, dict):
            continue
        p1_price = book_odds.get("p1") or book_odds.get("odds_1") or book_odds.get("player_1")
        p2_price = book_odds.get("p2") or book_odds.get("odds_2") or book_odds.get("player_2")
        try:
            p1_val = int(float(p1_price)) if p1_price is not None else None
            p2_val = int(float(p2_price)) if p2_price is not None else None
        except (ValueError, TypeError):
            p1_val = None
            p2_val = None
        if p1_val is None or p2_val is None:
            continue
        books.append((str(book_name), p1_val, p2_val))

    # DataGolf fallback if nested books are unavailable.
    if not books:
        for field_p1, field_p2 in [("p1_odds", "p2_odds"), ("odds_p1", "odds_p2")]:
            if matchup.get(field_p1) is None or matchup.get(field_p2) is None:
                continue
            try:
                p1_val = int(float(matchup[field_p1]))
                p2_val = int(float(matchup[field_p2]))
            except (ValueError, TypeError):
                continue
            books.append(("datagolf", p1_val, p2_val))
            break

    # Deduplicate by normalized book key, keep first valid pair encountered.
    deduped: list[tuple[str, int, int]] = []
    seen_books: set[str] = set()
    for book_name, p1_odds, p2_odds in books:
        key = book_name.strip().lower()
        if key in seen_books:
            continue
        seen_books.add(key)
        deduped.append((book_name, p1_odds, p2_odds))
    return deduped


def compute_conviction_score(
    form_gap: float,
    course_fit_gap: float,
    pick_momentum: float,
    opp_momentum: float,
    model_win_prob: float,
    platt_win_prob: float,
    dg_prob: float | None = None,
) -> int:
    """Compute a 0-100 conviction score for a matchup bet.

    Components:
    - Form differential (40%): normalized |form_gap| / 40, capped at 1.0
    - Course fit differential (25%): normalized |course_fit_gap| / 30, capped at 1.0
    - Momentum alignment (20%): 1.0 if pick hot + opp cold, partial otherwise
    - DG/model agreement strength (15%): how strongly both agree on the pick
    """
    form_score = min(abs(form_gap) / 40.0, 1.0)
    cf_score = min(abs(course_fit_gap) / 30.0, 1.0)

    momentum_score = 0.0
    if pick_momentum > 55 and opp_momentum < 45:
        momentum_score = 1.0
    elif pick_momentum > 50 and opp_momentum < 50:
        momentum_score = 0.5
    elif pick_momentum > opp_momentum:
        momentum_score = 0.25

    agreement_score = 0.5
    if dg_prob is not None:
        both_favor = (dg_prob > 0.5 and platt_win_prob > 0.5)
        if both_favor:
            strength = min(dg_prob, platt_win_prob)
            agreement_score = min((strength - 0.5) / 0.3, 1.0)
        else:
            agreement_score = 0.0

    raw = (
        0.40 * form_score
        + 0.25 * cf_score
        + 0.20 * momentum_score
        + 0.15 * agreement_score
    )
    return round(raw * 100)


def find_matchup_value_bets(composite_results: list[dict],
                             matchup_odds: list[dict],
                             ev_threshold: float = 0.05,
                             tournament_id: int = None,
                             required_book: str | None = None,
                             market_type: str = "tournament_matchups",
                             return_diagnostics: bool = False) -> list[dict] | tuple[list[dict], dict]:
    """
    Find value in real sportsbook matchups using model composite scores.

    composite_results: from composite.compute_composite() — sorted list with
        player_key, player_display, composite, form, course_fit, momentum
    matchup_odds: from datagolf.fetch_matchup_odds() — list of matchup dicts
    ev_threshold: minimum EV to flag as value
    tournament_id: for adaptation state lookup

    Returns list of matchup value bets sorted by EV descending.
    """
    diagnostics = {
        "input_rows": len(matchup_odds or []),
        "selected_rows": 0,
        "reason_codes": {
            "missing_player_name": 0,
            "missing_composite_player": 0,
            "equal_composite_gap": 0,
            "dg_model_disagreement": 0,
            "invalid_implied_prob": 0,
            "below_ev_threshold": 0,
            "exposure_capped": 0,
        },
        "adaptation_state": "normal",
        "ev_threshold_effective": ev_threshold,
    }
    adaptation = None
    if tournament_id:
        try:
            from src.adaptation import get_adaptation_state
            adaptation = get_adaptation_state("matchup")
        except Exception as e:
            logger.warning("Adaptation state unavailable for matchup: %s", e)
            adaptation = None

    if adaptation and adaptation.get("suppress"):
        diagnostics["adaptation_state"] = adaptation.get("state", "suppressed")
        diagnostics["selection_state"] = "suppressed_by_adaptation"
        if return_diagnostics:
            return [], diagnostics
        return []

    if adaptation and adaptation.get("ev_threshold") is not None:
        ev_threshold = max(ev_threshold, adaptation["ev_threshold"])
    diagnostics["adaptation_state"] = adaptation.get("state", "normal") if adaptation else "normal"
    diagnostics["ev_threshold_effective"] = ev_threshold

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
            diagnostics["reason_codes"]["missing_player_name"] += 1
            continue

        p1_key = normalize_name(p1_name)
        p2_key = normalize_name(p2_name)

        p1_data = composite_lookup.get(p1_key)
        p2_data = composite_lookup.get(p2_key)

        if not p1_data or not p2_data:
            diagnostics["reason_codes"]["missing_composite_player"] += 1
            continue

        composite_gap = p1_data["composite"] - p2_data["composite"]
        if composite_gap == 0:
            diagnostics["reason_codes"]["equal_composite_gap"] += 1
            continue

        # Pick the player our model favors
        if composite_gap > 0:
            pick_data, opp_data = p1_data, p2_data
            pick_side = "p1"
        else:
            pick_data, opp_data = p2_data, p1_data
            pick_side = "p2"

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
                        diagnostics["reason_codes"]["dg_model_disagreement"] += 1
                        continue

        # Gaps from the pick's perspective
        pick_form = pick_data.get("form", 50)
        opp_form = opp_data.get("form", 50)
        pick_cf = pick_data.get("course_fit", 50)
        opp_cf = opp_data.get("course_fit", 50)
        form_gap = pick_form - opp_form
        course_fit_gap = pick_cf - opp_cf

        pick_momentum = pick_data.get("momentum", 50)
        opp_momentum = opp_data.get("momentum", 50)
        momentum_aligned = pick_momentum > 55 and opp_momentum < 45

        reasons = []
        if abs(course_fit_gap) > 5:
            sign = "+" if course_fit_gap > 0 else ""
            reasons.append(f"course fit {sign}{course_fit_gap:.0f}")
        if abs(form_gap) > 5:
            sign = "+" if form_gap > 0 else ""
            reasons.append(f"form {sign}{form_gap:.0f}")
        if momentum_aligned:
            pick_dir = pick_data.get("momentum_direction", "")
            opp_dir = opp_data.get("momentum_direction", "")
            if pick_dir:
                reasons.append(f"pick {pick_dir}")
            if opp_dir:
                reasons.append(f"opp {opp_dir}")

        dg_prob_for_conviction = None
        if dg_pairings:
            dg_pair_check = dg_pairings.get((pick_data["player_key"], opp_data["player_key"]))
            if not dg_pair_check:
                dg_pair_rev_check = dg_pairings.get((opp_data["player_key"], pick_data["player_key"]))
                if dg_pair_rev_check:
                    dg_prob_for_conviction = dg_pair_rev_check["p2_win_prob"]
            else:
                dg_prob_for_conviction = dg_pair_check["p1_win_prob"]

        conviction = compute_conviction_score(
            form_gap=form_gap,
            course_fit_gap=course_fit_gap,
            pick_momentum=pick_momentum,
            opp_momentum=opp_momentum,
            model_win_prob=model_win_prob,
            platt_win_prob=platt_win_prob,
            dg_prob=dg_prob_for_conviction,
        )

        stake_mult = adaptation["stake_multiplier"] if adaptation else 1.0

        if required_book:
            p1_odds, p2_odds = _parse_book_odds(matchup, required_book)
            book_lines = [(required_book, p1_odds, p2_odds)] if p1_odds is not None and p2_odds is not None else []
        else:
            book_lines = _iter_book_odds(matchup)

        for book_name, p1_odds, p2_odds in book_lines:
            pick_odds = p1_odds if pick_side == "p1" else p2_odds
            implied_prob = american_to_implied_prob(pick_odds)
            if not implied_prob or implied_prob <= 0:
                diagnostics["reason_codes"]["invalid_implied_prob"] += 1
                continue

            ev = (model_win_prob / implied_prob) - 1.0
            if ev < ev_threshold:
                diagnostics["reason_codes"]["below_ev_threshold"] += 1
                continue

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
                "book": str(book_name).strip().lower(),
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
                "pick_momentum": round(pick_momentum, 1),
                "opp_momentum": round(opp_momentum, 1),
                "momentum_aligned": momentum_aligned,
                "conviction": conviction,
            })

    value_bets.sort(
        key=lambda x: (x["ev"], x.get("momentum_aligned", False), x.get("conviction", 0)),
        reverse=True,
    )

    # Per-player exposure cap: limit how many matchup bets feature the same player (WD protection)
    if market_type == "tournament_matchups":
        max_exposure = getattr(config, "MATCHUP_TOURNAMENT_MAX_PLAYER_EXPOSURE", 2)
    else:
        max_exposure = getattr(config, "MATCHUP_MAX_PLAYER_EXPOSURE", 3)
    def _pair_key(bet: dict) -> tuple[str, str, str]:
        return (
            str(bet.get("pick_key") or ""),
            str(bet.get("opponent_key") or ""),
            str(market_type),
        )

    best_by_pair: dict[tuple[str, str, str], dict] = {}
    for bet in value_bets:
        key = _pair_key(bet)
        current = best_by_pair.get(key)
        if current is None or float(bet.get("ev", 0.0)) > float(current.get("ev", 0.0)):
            best_by_pair[key] = bet
    ranked_pairs = sorted(
        best_by_pair.values(),
        key=lambda x: (x["ev"], x.get("momentum_aligned", False), x.get("conviction", 0)),
        reverse=True,
    )

    player_counts: dict[str, int] = {}
    allowed_pairs: set[tuple[str, str, str]] = set()
    for bet in ranked_pairs:
        pk = bet["pick_key"]
        ok = bet["opponent_key"]
        if player_counts.get(pk, 0) >= max_exposure or player_counts.get(ok, 0) >= max_exposure:
            diagnostics["reason_codes"]["exposure_capped"] += 1
            continue
        player_counts[pk] = player_counts.get(pk, 0) + 1
        player_counts[ok] = player_counts.get(ok, 0) + 1
        allowed_pairs.add(_pair_key(bet))
        if len(allowed_pairs) >= config.MATCHUP_CAP:
            break

    filtered = [bet for bet in value_bets if _pair_key(bet) in allowed_pairs]
    filtered.sort(
        key=lambda x: (x["ev"], x.get("momentum_aligned", False), x.get("conviction", 0)),
        reverse=True,
    )
    diagnostics["selected_rows"] = len(filtered)
    if diagnostics["input_rows"] == 0:
        diagnostics["selection_state"] = "no_market_rows"
    elif diagnostics["selected_rows"] == 0:
        diagnostics["selection_state"] = "market_available_no_edges"
    else:
        diagnostics["selection_state"] = "edges_available"
    if return_diagnostics:
        return filtered, diagnostics
    return filtered
