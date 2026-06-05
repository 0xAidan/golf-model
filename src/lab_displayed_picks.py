"""Persist lab-sandbox displayed picks (separate ``source`` from cockpit grading lane)."""

from __future__ import annotations

from typing import Any

from src import db
from src.lab_profile import resolve_lab_model_variant
from src.player_normalizer import display_name, normalize_name

_LAB_SOURCE = "lab_sandbox"


def persist_lab_logged_picks(body: dict[str, Any]) -> int:
    """
    Accepts JSON:
    ``tournament_id`` (int), ``profile_name`` (str, maps to ``profiles.yaml``),
    ``composite_results`` (list), ``matchups`` (list), optional ``value_bets`` (dict),
    optional ``matchup_failed_candidates`` (list, diagnostics only — not stored).
    """
    tid = int(body.get("tournament_id") or 0)
    if tid <= 0:
        raise ValueError("tournament_id is required")
    profile_name = str(body.get("profile_name") or "lab_sandbox").strip()
    lab_mv = resolve_lab_model_variant(profile_name)
    composite = body.get("composite_results") or []
    if not isinstance(composite, list):
        composite = []
    comp_lookup = {row.get("player_key"): row for row in composite if isinstance(row, dict)}
    pick_rows: list[dict[str, Any]] = []

    value_bets = body.get("value_bets") or {}
    if isinstance(value_bets, dict):
        for bet_type, bets in value_bets.items():
            for bet in bets or []:
                if not isinstance(bet, dict):
                    continue
                player_key = (bet.get("player_key") or "").strip()
                if not player_key:
                    continue
                comp = comp_lookup.get(player_key, {})
                best_odds = bet.get("best_odds")
                odds_text = None
                if isinstance(best_odds, (int, float)):
                    odds_int = int(best_odds)
                    odds_text = f"+{odds_int}" if odds_int > 0 else str(odds_int)
                elif best_odds is not None:
                    odds_text = str(best_odds)
                reasoning_parts = []
                if bet.get("best_book"):
                    reasoning_parts.append(f"book={bet.get('best_book')}")
                if bet.get("ev_pct"):
                    reasoning_parts.append(f"edge={bet.get('ev_pct')}")
                pick_rows.append({
                    "tournament_id": tid,
                    "model_variant": lab_mv,
                    "source": _LAB_SOURCE,
                    "bet_type": str(bet_type),
                    "player_key": player_key,
                    "player_display": bet.get("player_display") or display_name(player_key),
                    "opponent_key": "",
                    "opponent_display": "",
                    "composite_score": comp.get("composite"),
                    "course_fit_score": comp.get("course_fit"),
                    "form_score": comp.get("form"),
                    "momentum_score": comp.get("momentum"),
                    "model_prob": bet.get("model_prob"),
                    "market_odds": odds_text,
                    "market_book": bet.get("book") or bet.get("best_book") or "",
                    "market_implied_prob": bet.get("market_prob"),
                    "ev": bet.get("ev"),
                    "confidence": bet.get("confidence") or bet.get("tier"),
                    "reasoning": "; ".join(reasoning_parts) or None,
                })

    matchups = body.get("matchups") or []
    if isinstance(matchups, list):
        for bet in matchups:
            if not isinstance(bet, dict):
                continue
            pick_key = (bet.get("pick_key") or "").strip() or normalize_name(str(bet.get("pick", "")))
            if not pick_key:
                continue
            opponent_key = (bet.get("opponent_key") or "").strip() or normalize_name(str(bet.get("opponent", "")))
            comp = comp_lookup.get(pick_key, {})
            odds_val = bet.get("odds")
            odds_text = None
            if isinstance(odds_val, (int, float)):
                odds_int = int(odds_val)
                odds_text = f"+{odds_int}" if odds_int > 0 else str(odds_int)
            elif odds_val is not None:
                odds_text = str(odds_val)
            pick_rows.append({
                "tournament_id": tid,
                "model_variant": lab_mv,
                "source": _LAB_SOURCE,
                "bet_type": "matchup",
                "player_key": pick_key,
                "player_display": bet.get("pick") or display_name(pick_key),
                "opponent_key": opponent_key,
                "opponent_display": bet.get("opponent") or display_name(opponent_key),
                "composite_score": comp.get("composite"),
                "course_fit_score": comp.get("course_fit"),
                "form_score": comp.get("form"),
                "momentum_score": comp.get("momentum"),
                "model_prob": bet.get("model_win_prob", bet.get("model_prob")),
                "market_odds": odds_text,
                "market_book": bet.get("book") or "",
                "market_implied_prob": bet.get("implied_prob", bet.get("market_prob")),
                "ev": bet.get("ev"),
                "confidence": bet.get("tier"),
                "reasoning": bet.get("why"),
            })

    # matchup_failed_candidates are diagnostics-only; not stored for grading.

    positive_ev_rows = [
        row for row in pick_rows
        if row.get("ev") is not None and row.get("ev") > 0
    ]
    if not positive_ev_rows:
        return 0
    db.store_picks(positive_ev_rows)
    return len(positive_ev_rows)
