"""
Kelly stake sizing with drawdown constraint.

When feature flag kelly_sizing is on, stakes are computed as fraction of bankroll.
Default quarter-Kelly; eighth-Kelly during bootstrap. If balance < 85% of peak,
auto-reduce to eighth-Kelly.
"""

import logging
from typing import Optional

from src import db
from src.feature_flags import is_enabled

logger = logging.getLogger(__name__)

DEFAULT_KELLY_FRACTION = 0.25   # quarter-Kelly
DRAWDOWN_KELLY_FRACTION = 0.125  # eighth-Kelly when in drawdown
DRAWDOWN_THRESHOLD = 0.85   # balance < 85% of peak -> use DRAWDOWN_KELLY_FRACTION


def get_bankroll_state() -> Optional[dict]:
    """
    Return latest bankroll row or None if not initialized.
    {balance, peak_balance, kelly_fraction, date, notes}
    """
    conn = db.get_conn()
    row = conn.execute(
        "SELECT balance, peak_balance, kelly_fraction, date, notes FROM bankroll ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "balance": row["balance"],
        "peak_balance": row["peak_balance"],
        "kelly_fraction": row["kelly_fraction"],
        "date": row["date"],
        "notes": row["notes"],
    }


def kelly_stake(
    model_prob: float,
    decimal_odds: float,
    bankroll: Optional[float] = None,
    kelly_fraction: Optional[float] = None,
) -> float:
    """
    Full Kelly edge = model_prob * decimal_odds - 1.
    Stake fraction = edge / (decimal_odds - 1). Cap at fraction of bankroll.

    If bankroll/kelly_fraction not provided, reads from bankroll table.
    Returns fraction of bankroll to stake (0 if negative edge or invalid).
    """
    if model_prob <= 0 or decimal_odds <= 1:
        return 0.0
    edge = model_prob * decimal_odds - 1.0
    if edge <= 0:
        return 0.0
    # Kelly fraction of bankroll: f = (p*odds - 1) / (odds - 1) = edge / (odds - 1)
    frac = edge / (decimal_odds - 1.0)
    if kelly_fraction is not None:
        frac = frac * kelly_fraction
    else:
        state = get_bankroll_state()
        if state:
            kf = state["kelly_fraction"]
            balance = state["balance"]
            peak = state["peak_balance"]
            if peak and peak > 0 and balance < peak * DRAWDOWN_THRESHOLD:
                kf = DRAWDOWN_KELLY_FRACTION
                logger.info("Drawdown: using eighth-Kelly (balance %.0f%% of peak)", 100 * balance / peak)
            frac = frac * kf
        else:
            frac = frac * DEFAULT_KELLY_FRACTION
    return max(0.0, min(frac, 0.25))  # cap single bet at 25% of bankroll


def units_for_bet(
    model_prob: float,
    decimal_odds: float,
    bankroll: Optional[float] = None,
) -> float:
    """
    When kelly_sizing flag is on, return stake as fraction of bankroll (for display).
    When off, return 1.0 (flat unit).
    """
    if not (is_enabled("kelly_sizing") or is_enabled("kelly_stakes")):
        return 1.0
    state = get_bankroll_state()
    bal = bankroll if bankroll is not None else (state["balance"] if state else None)
    if bal is None or bal <= 0:
        return 1.0
    frac = kelly_stake(model_prob, decimal_odds, bankroll=bal)
    return max(0.01, frac)  # minimum 1% for display


def update_bankroll_after_tournament(
    profit_units: float,
    date: str,
    notes: str = "",
) -> None:
    """
    Append a new bankroll row after settling a tournament.
    balance = previous balance + profit_units; peak_balance = max(peak, balance).
    """
    conn = db.get_conn()
    row = conn.execute(
        "SELECT balance, peak_balance, kelly_fraction FROM bankroll ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        balance = row["balance"] + profit_units
        peak = max(row["peak_balance"], balance)
        kf = row["kelly_fraction"]
    else:
        balance = profit_units
        peak = max(balance, 0)
        kf = DEFAULT_KELLY_FRACTION
    conn.execute(
        "INSERT INTO bankroll (date, balance, peak_balance, kelly_fraction, notes) VALUES (?, ?, ?, ?, ?)",
        (date, balance, peak, kf, notes),
    )
    conn.commit()
    conn.close()
