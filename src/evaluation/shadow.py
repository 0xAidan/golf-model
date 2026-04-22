"""
Shadow-prediction recorder for the champion-challenger rails (defect 3.3.1).

Invoked from the matchup value path after the champion has priced a matchup.
For every model name in `src.config.CHALLENGERS`, we invoke its
`predict_matchup` on the same inputs and insert a row into
`challenger_predictions`. If any challenger raises, we log a WARNING and move
on — challenger failures must never break the live pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from src import db
from src.models.base import iter_active_challengers

logger = logging.getLogger("evaluation.shadow")


def _matchup_id(tournament_id: int | None, p1_key: str, p2_key: str, book: str | None) -> str:
    parts = [
        str(tournament_id or ""),
        str(p1_key or ""),
        str(p2_key or ""),
        str(book or ""),
    ]
    return "|".join(parts)


def record_matchup_shadow(
    *,
    p1: dict[str, Any],
    p2: dict[str, Any],
    features: dict[str, Any],
    champion_p: float,
    tournament_id: int | None = None,
    book: str | None = None,
    book_price_p1: float | None = None,
    book_price_p2: float | None = None,
) -> None:
    """Run every active challenger on this matchup and persist its prediction.

    Must be called AFTER the champion has priced the matchup. `champion_p` is
    P(p1 wins) from the champion, stored alongside each challenger row so the
    evaluation module can diff the two without re-running anything.

    This function never raises. All exceptions are logged and swallowed —
    shadow mode is strictly additive to the live pipeline.
    """
    try:
        challengers = iter_active_challengers()
    except Exception:
        logger.warning("Failed to enumerate challengers", exc_info=True)
        return
    if not challengers:
        return

    p1_key = str(p1.get("player_key") or "")
    p2_key = str(p2.get("player_key") or "")
    matchup_id = _matchup_id(tournament_id, p1_key, p2_key, book)

    rows: list[tuple[Any, ...]] = []
    for model in challengers:
        try:
            predicted = float(model.predict_matchup(p1, p2, features))
        except Exception:
            logger.warning(
                "Challenger %s raised during predict_matchup; skipping row",
                getattr(model, "name", "<unknown>"),
                exc_info=True,
            )
            continue
        if not (0.0 <= predicted <= 1.0):
            logger.warning(
                "Challenger %s returned out-of-range prediction %r; clamping",
                getattr(model, "name", "<unknown>"),
                predicted,
            )
            predicted = max(0.0, min(1.0, predicted))
        rows.append(
            (
                model.name,
                getattr(model, "version", None),
                "matchup",
                matchup_id,
                tournament_id,
                p1_key,
                p2_key,
                predicted,
                float(champion_p),
                book_price_p1,
                book_price_p2,
            )
        )

    if not rows:
        return

    try:
        conn = db.get_conn()
        conn.executemany(
            """
            INSERT INTO challenger_predictions (
                model_name, model_version, market_type, matchup_id,
                tournament_id, p1_key, p2_key, predicted_p, champion_p,
                book_price_p1, book_price_p2
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("Failed to persist challenger_predictions rows", exc_info=True)
