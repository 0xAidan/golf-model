"""
Closing Line Value (CLV) tracking.

The stored ``clv_pct`` is the legacy (taken implied - closing implied) series.
Keep it unchanged for existing consumers. Additive quoted-price analytics derive
positive-is-better CLV from the original decimal odds; neither series is de-vigged.
"""

import logging
import math
from typing import Optional

from src import db
from src.feature_flags import is_enabled

logger = logging.getLogger(__name__)

CLV_SIGNIFICANCE_MIN_BETS = 50


def _decimal_price(value: object) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return price if math.isfinite(price) and price > 1.0 else None


def quote_price_clv_pct(odds_taken_decimal: object, closing_odds_decimal: object) -> float | None:
    """Positive means a better quoted payout; this is not a no-vig fair value.

    For example, 3.0 taken and 2.5 closing is +20%. Missing/invalid prices have
    no measured CLV. Settlement rules and close timing are not verified here.
    """
    taken = _decimal_price(odds_taken_decimal)
    close = _decimal_price(closing_odds_decimal)
    if taken is None or close is None:
        return None
    value = (taken / close - 1.0) * 100.0
    return value if math.isfinite(value) else None


def _implied_from_decimal(decimal_odds: float) -> float:
    """Implied probability from decimal odds (no de-vig)."""
    if not decimal_odds or decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def multiplicative_devig(implied_probs: list[float]) -> list[float]:
    """
    Remove margin by normalizing implied probs to sum to 1.
    Each true_prob = implied_i / sum(implied).
    """
    total = sum(implied_probs)
    if total <= 0:
        return implied_probs
    return [p / total for p in implied_probs]


def record_clv(
    tournament_id: int,
    player_key: str,
    bet_type: str,
    odds_taken_decimal: float,
    closing_odds_decimal: Optional[float],
    outcome: Optional[int] = None,
    market_book: Optional[str] = None,
) -> Optional[float]:
    """
    Record one bet for CLV. If closing_odds_decimal is None, skip.
    Returns CLV in percentage points (implied_taken - implied_closing) * 100, or None.
    """
    if not is_enabled("clv_tracking"):
        return None
    if quote_price_clv_pct(odds_taken_decimal, closing_odds_decimal) is None:
        return None
    odds_taken_decimal = float(odds_taken_decimal)
    closing_odds_decimal = float(closing_odds_decimal)
    implied_taken = _implied_from_decimal(odds_taken_decimal)
    implied_closing = _implied_from_decimal(closing_odds_decimal)
    clv_pct = (implied_taken - implied_closing) * 100.0
    book_val = (market_book or "").strip() or None
    conn = db.get_conn()
    conn.execute(
        """INSERT INTO clv_log
           (tournament_id, player_key, bet_type, market_book, odds_taken_decimal, closing_odds_decimal,
            implied_taken, implied_closing, clv_pct, outcome)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tournament_id,
            player_key,
            bet_type,
            book_val,
            odds_taken_decimal,
            closing_odds_decimal,
            implied_taken,
            implied_closing,
            clv_pct,
            outcome,
        ),
    )
    conn.commit()
    conn.close()
    return clv_pct


def compute_clv_summary() -> dict:
    """
    Aggregate CLV from clv_log. Returns avg_clv_pct, n_bets, significant (True if n >= 50).
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT odds_taken_decimal, closing_odds_decimal, clv_pct FROM clv_log"
        ).fetchall()
    finally:
        conn.close()
    return _summarize_rows(rows)


def _summarize_rows(rows: list) -> dict:
    n = len(rows)
    legacy = [float(row["clv_pct"]) for row in rows if row["clv_pct"] is not None]
    avg = sum(legacy) / len(legacy) if legacy else None
    quoted: list[float] = []
    missing = invalid = 0
    for row in rows:
        taken, close = row["odds_taken_decimal"], row["closing_odds_decimal"]
        if taken is None or close is None:
            missing += 1
            continue
        value = quote_price_clv_pct(taken, close)
        if value is None:
            invalid += 1
        else:
            quoted.append(value)
    return {
        "n_bets": n,
        "avg_clv_pct": round(avg, 2) if avg is not None else None,
        "legacy_signed_clv_pct": round(avg, 2) if avg is not None else None,
        "legacy_signed_clv_source": "stored_clv_log_clv_pct_unchanged",
        # Compatibility only: a sample-count flag is not a significance test.
        "significant": n >= CLV_SIGNIFICANCE_MIN_BETS,
        "significance_basis": "legacy_sample_count_threshold_only",
        "quote_price_clv_pct": round(sum(quoted) / len(quoted), 4) if quoted else None,
        # Legacy rows do not identify the closing event, book or quote time.
        # A valid price ratio alone cannot establish qualified closing value.
        "qualified_clv_pct": None,
        "fair_close_ev_pct": None,
        "coverage": {
            "denominator": "recorded_clv_rows",
            "recorded_rows": n,
            "valid_quote_pairs": len(quoted),
            "missing_quote_pairs": missing,
            "invalid_quote_pairs": invalid,
            "quote_pair_coverage_pct": round(len(quoted) / n * 100.0, 2) if n else None,
        },
        "quote_price_clv_provenance": {
            "version": "quoted_price_v1",
            "formula": "100 * (odds_taken_decimal / closing_odds_decimal - 1)",
            "positive_means": "better_taken_payout",
            "derived_from": "clv_log_original_decimal_odds",
            "devig_applied": False,
            "close_verified": False,
            "source_qualification": "unverified_legacy_close",
            "qualification_reason": (
                "Legacy close capture does not establish the same event, book, "
                "settlement contract or a closing quote before market start; "
                "the derived value compares recorded prices only."
            ),
            "close_timing_and_settlement_verified": False,
            "legacy_formula": "100 * (1 / odds_taken_decimal - 1 / closing_odds_decimal)",
        },
    }


def compute_clv_summary_by_book() -> dict:
    """
    CLV aggregates grouped by ``market_book``.

    Rows with NULL/blank ``market_book`` are labeled ``(unknown)``.
    Each segment includes ``significant`` when n_bets >= CLV_SIGNIFICANCE_MIN_BETS.
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT market_book, odds_taken_decimal, closing_odds_decimal, clv_pct FROM clv_log"
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[str, list] = {}
    for row in rows:
        book = str(row["market_book"] or "").strip() or "(unknown)"
        grouped.setdefault(book, []).append(row)
    segments = [
        {"market_book": book, **_summarize_rows(book_rows)}
        for book, book_rows in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    ]

    return {
        "overall": _summarize_rows(rows),
        "by_book": segments,
        "min_bets_for_significance": CLV_SIGNIFICANCE_MIN_BETS,
    }


def get_clv_for_tournament(tournament_id: int) -> list[dict]:
    """Return all clv_log rows for a tournament (for learning loop / display)."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT * FROM clv_log WHERE tournament_id = ? ORDER BY id",
        (tournament_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
