"""
Closing Line Value (CLV) tracking.

When feature flag clv_tracking is on, record odds at bet time and closing odds;
compute CLV as improvement in implied probability vs closing. Multiplicative de-vig
for closing line. Significance: 50+ bets for meaningful CLV read.
"""

import logging
from typing import Optional

from src import db
from src.feature_flags import is_enabled

logger = logging.getLogger(__name__)

CLV_SIGNIFICANCE_MIN_BETS = 50


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
    if not closing_odds_decimal or closing_odds_decimal <= 0:
        return None
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
    row = conn.execute(
        "SELECT COUNT(*) AS n, AVG(clv_pct) AS avg_clv FROM clv_log"
    ).fetchone()
    conn.close()
    n = row["n"] or 0
    avg = row["avg_clv"]
    return {
        "n_bets": n,
        "avg_clv_pct": round(avg, 2) if avg is not None else None,
        "significant": n >= CLV_SIGNIFICANCE_MIN_BETS,
    }


def compute_clv_summary_by_book() -> dict:
    """
    CLV aggregates grouped by ``market_book``.

    Rows with NULL/blank ``market_book`` are labeled ``(unknown)``.
    Each segment includes ``significant`` when n_bets >= CLV_SIGNIFICANCE_MIN_BETS.
    """
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT
            CASE
                WHEN market_book IS NULL OR TRIM(market_book) = '' THEN '(unknown)'
                ELSE TRIM(market_book)
            END AS book_key,
            COUNT(*) AS n_bets,
            AVG(clv_pct) AS avg_clv_pct
        FROM clv_log
        GROUP BY book_key
        ORDER BY n_bets DESC
        """
    ).fetchall()
    conn.close()

    segments = []
    for r in rows:
        n = int(r["n_bets"] or 0)
        avg = r["avg_clv_pct"]
        segments.append(
            {
                "market_book": r["book_key"],
                "n_bets": n,
                "avg_clv_pct": round(float(avg), 2) if avg is not None else None,
                "significant": n >= CLV_SIGNIFICANCE_MIN_BETS,
            }
        )

    return {
        "overall": compute_clv_summary(),
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
