"""
T6 — In-play round matchup shadow service (SHADOW MODE ONLY).

Glue between the live refresh flow and the shadow prediction pipeline.

The live refresh worker (or anything that polls book prices during active
rounds) can call `ingest_inplay_prices()` with the rows it pulled. If the
`INPLAY_ROUND_MATCHUPS_SHADOW` flag is on, we:

  1. Persist the raw book rows to `inplay_round_matchup_prices`.
  2. Compute a predicted probability via `predict_inplay_round`.
  3. Log one row per refresh tick per matchup to
     `inplay_round_matchup_predictions`, along with a HYPOTHETICAL Kelly
     fraction for offline analysis only.

Nothing here places real bets. Staking is disabled at the bet-ticket layer
(`src.models.inplay_round_matchup.assert_inplay_staking_disabled`).
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping

from src import config
from src.db import get_conn, ensure_initialized
from src.kelly import kelly_stake
from src.models.inplay_round_matchup import predict_inplay_round
from src.odds_utils import american_to_decimal  # noqa: F401  # best-effort import

logger = logging.getLogger("golf.inplay_shadow")


def _to_decimal(price) -> float:
    """
    Accept decimal odds directly, or American odds. Returns decimal odds
    or 0.0 if unparseable.
    """
    try:
        p = float(price)
    except (TypeError, ValueError):
        return 0.0
    if p <= 1.0 and p != 0.0:
        # already-implied probability is not valid here
        return 0.0
    if p >= 1.1 and p <= 30.0:
        return p  # decimal odds
    # American odds path
    if p > 0:
        return 1.0 + p / 100.0
    if p < 0:
        return 1.0 + 100.0 / abs(p)
    return 0.0


def is_shadow_enabled() -> bool:
    return bool(getattr(config, "INPLAY_ROUND_MATCHUPS_SHADOW", False))


def ingest_inplay_prices(
    price_rows: Iterable[Mapping[str, object]],
    *,
    features: Mapping[str, object] | None = None,
) -> int:
    """
    Persist raw prices and shadow-log predictions for each row.

    Each row is expected to have:
      event_id, round_num, player1, player2, book, price1, price2,
      hole_num (holes completed so far), current_scores={p1:..., p2:...}

    Returns the number of prediction rows written. No-op (returns 0) when
    the shadow flag is off.
    """
    if not is_shadow_enabled():
        return 0

    rows = list(price_rows or [])
    if not rows:
        return 0

    ensure_initialized()
    conn = get_conn()
    written = 0
    try:
        for row in rows:
            event_id = str(row.get("event_id") or "")
            round_num = int(row.get("round_num") or 0)
            p1 = str(row.get("player1") or "")
            p2 = str(row.get("player2") or "")
            book = str(row.get("book") or "")
            price1 = float(row.get("price1") or 0.0)
            price2 = float(row.get("price2") or 0.0)
            hole_num = int(row.get("hole_num") or 0)
            current_scores = row.get("current_scores") or {}

            if not (event_id and p1 and p2 and book):
                continue

            conn.execute(
                """
                INSERT INTO inplay_round_matchup_prices
                    (event_id, round_num, player1, player2, book, price1, price2)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, round_num, p1, p2, book, price1, price2),
            )

            predicted_p1 = predict_inplay_round(
                p1, p2, round_num, hole_num, current_scores, features=features
            )

            dec1 = _to_decimal(price1)
            # HYPOTHETICAL only — never used to place a real bet. Staking
            # is enforced disabled in the bet-ticket builder.
            hypothetical_kelly = kelly_stake(
                predicted_p1, dec1, bankroll=1.0, kelly_fraction=1.0
            ) if dec1 > 1.0 else 0.0

            conn.execute(
                """
                INSERT INTO inplay_round_matchup_predictions
                    (event_id, round_num, hole_num_at_prediction,
                     player1, player2, book, price1, price2,
                     predicted_p1, kelly_fraction_if_hypothetically)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, round_num, hole_num, p1, p2, book,
                 price1, price2, predicted_p1, hypothetical_kelly),
            )
            written += 1
        conn.commit()
    except Exception:
        logger.exception("inplay shadow ingest failed")
        conn.rollback()
    finally:
        conn.close()
    return written
