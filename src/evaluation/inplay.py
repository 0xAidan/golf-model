"""
T6 — Offline evaluation for in-play round matchup shadow predictions.

Given settled round outcomes, compute Brier score and a hypothetical ROI
"if we had staked" at the recorded hypothetical Kelly fraction. These
numbers exist to judge whether to promote this market OUT of shadow mode
in a later PR — they do NOT drive staking in this PR.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from src.db import get_conn, ensure_initialized


def _decimal_from_recorded(price: float) -> float:
    """Mirror of src.services.inplay_shadow._to_decimal for standalone use."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return 0.0
    if p >= 1.1 and p <= 30.0:
        return p
    if p > 0:
        return 1.0 + p / 100.0
    if p < 0:
        return 1.0 + 100.0 / abs(p)
    return 0.0


def brier_score(predictions: Iterable[Mapping[str, object]]) -> float:
    """
    Brier = mean((predicted_p1 - outcome_p1)^2), where outcome_p1 is 1 if
    player1 won the round matchup, 0 if player2, 0.5 on a tie.
    """
    preds = list(predictions or [])
    if not preds:
        return 0.0
    total = 0.0
    n = 0
    for p in preds:
        outcome = p.get("outcome_p1")
        if outcome is None:
            continue
        pred = float(p.get("predicted_p1") or 0.0)
        total += (pred - float(outcome)) ** 2
        n += 1
    return (total / n) if n else 0.0


def hypothetical_roi(predictions: Iterable[Mapping[str, object]]) -> dict:
    """
    Hypothetical ROI if we had staked at `kelly_fraction_if_hypothetically`
    on whichever side our model preferred. Uses unit bankroll.

    Returns {bets, staked, returned, roi_pct}. This is OFFLINE analysis
    only — real staking on this market is disabled.
    """
    preds = list(predictions or [])
    staked = 0.0
    returned = 0.0
    bets = 0
    for p in preds:
        outcome = p.get("outcome_p1")
        if outcome is None:
            continue
        kf = float(p.get("kelly_fraction_if_hypothetically") or 0.0)
        if kf <= 0:
            continue
        predicted_p1 = float(p.get("predicted_p1") or 0.0)
        side_is_p1 = predicted_p1 >= 0.5
        price = p.get("price1") if side_is_p1 else p.get("price2")
        dec = _decimal_from_recorded(price)
        if dec <= 1.0:
            continue
        stake = kf
        staked += stake
        bets += 1
        side_won = (side_is_p1 and float(outcome) > 0.5) or (
            (not side_is_p1) and float(outcome) < 0.5
        )
        if float(outcome) == 0.5:
            returned += stake  # push
        elif side_won:
            returned += stake * dec
        # losing side: returned unchanged (stake lost)
    roi_pct = ((returned - staked) / staked * 100.0) if staked > 0 else 0.0
    return {
        "bets": bets,
        "staked": staked,
        "returned": returned,
        "roi_pct": roi_pct,
    }


def load_predictions_for_event(event_id: str) -> list[dict]:
    """Pull prediction rows for an event from the shadow table."""
    ensure_initialized()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            SELECT event_id, round_num, hole_num_at_prediction,
                   player1, player2, book, price1, price2,
                   predicted_p1, kelly_fraction_if_hypothetically, ts
            FROM inplay_round_matchup_predictions
            WHERE event_id = ?
            ORDER BY round_num, hole_num_at_prediction, ts
            """,
            (event_id,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
