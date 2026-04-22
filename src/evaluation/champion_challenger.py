"""
Champion-challenger offline evaluation (defect 3.3.1).

All three public functions read from `challenger_predictions` plus the
outcomes already persisted by the live pipeline. They never read or modify
live bet history.

Evaluation contracts:

* `brier_scores(model, since)` — mean (p - outcome)^2 over rows where an
  outcome is known, plus sample size `n`.
* `matchup_roi(model, since)` — ROI the model WOULD have realized if it
  priced matchups at the recorded book price. Bets are simulated at a flat
  1-unit stake on the side the model favors, settled against the recorded
  `outcome`. The champion's ROI is computed from its own recorded
  `champion_p` on the same rows so challenger vs. champion comparisons use
  identical book prices and outcomes.
* `clv_summary(model, since)` — average difference between the model's
  implied price and the recorded book price, expressed in basis points of
  probability (10000 * (model_p - book_p)). Positive means the model is
  asking for a longer price than the book offers (i.e. it would have beat
  close).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src import db


def _fetch_rows(model_name: str, since: datetime) -> list[dict[str, Any]]:
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT model_name, model_version, matchup_id, p1_key, p2_key,
               predicted_p, champion_p, book_price_p1, book_price_p2,
               outcome, ts
        FROM challenger_predictions
        WHERE model_name = ?
          AND ts >= ?
        """,
        (model_name, since.isoformat(sep=" ", timespec="seconds")),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def brier_scores(model_name: str, since: datetime) -> dict[str, Any]:
    """Return mean Brier score + sample size for a model since `since`."""
    rows = _fetch_rows(model_name, since)
    graded = [r for r in rows if r.get("outcome") is not None]
    if not graded:
        return {"model_name": model_name, "brier": None, "n": 0}
    total = 0.0
    for r in graded:
        p = float(r["predicted_p"])
        y = 1 if int(r["outcome"]) == 1 else 0
        total += (p - y) ** 2
    return {"model_name": model_name, "brier": total / len(graded), "n": len(graded)}


def _flat_stake_roi(model_p: float, book_p: float | None, outcome: int) -> float | None:
    """Unit-stake settlement: bet `model_p` side when model > book_p.

    Returns profit in units (win - 1 or -1). `None` when there isn't enough
    information to settle (missing book price or outcome).
    """
    if book_p is None or book_p <= 0.0 or book_p >= 1.0:
        return None
    if model_p <= book_p:
        return None  # No bet
    decimal_odds = 1.0 / book_p
    return (decimal_odds - 1.0) if outcome == 1 else -1.0


def matchup_roi(model_name: str, since: datetime) -> dict[str, Any]:
    """ROI the model would have realized at flat 1-unit on every qualifying row."""
    rows = _fetch_rows(model_name, since)
    settled = [r for r in rows if r.get("outcome") is not None]

    bets = 0
    staked = 0.0
    pnl = 0.0
    for r in settled:
        model_p = float(r["predicted_p"])
        outcome_p1 = int(r["outcome"])
        # Decide which side the model favors; bet that side, grade against outcome.
        if model_p >= 0.5:
            book_p = r.get("book_price_p1")
            settled_outcome = outcome_p1
            model_side_p = model_p
        else:
            book_p = r.get("book_price_p2")
            settled_outcome = 1 - outcome_p1
            model_side_p = 1.0 - model_p
        pnl_row = _flat_stake_roi(model_side_p, book_p, settled_outcome)
        if pnl_row is None:
            continue
        bets += 1
        staked += 1.0
        pnl += pnl_row

    roi = (pnl / staked) if staked > 0 else None
    return {
        "model_name": model_name,
        "bets": bets,
        "staked": round(staked, 4),
        "pnl": round(pnl, 4),
        "roi_pct": round(roi * 100, 2) if roi is not None else None,
    }


def clv_summary(model_name: str, since: datetime) -> dict[str, Any]:
    """Mean (model_p - book_p) in basis points, on the side the model favored."""
    rows = _fetch_rows(model_name, since)
    diffs: list[float] = []
    for r in rows:
        model_p = float(r["predicted_p"])
        if model_p >= 0.5:
            book_p = r.get("book_price_p1")
            model_side_p = model_p
        else:
            book_p = r.get("book_price_p2")
            model_side_p = 1.0 - model_p
        if book_p is None or book_p <= 0.0 or book_p >= 1.0:
            continue
        diffs.append(model_side_p - float(book_p))
    if not diffs:
        return {"model_name": model_name, "clv_bps": None, "n": 0}
    avg = sum(diffs) / len(diffs)
    return {
        "model_name": model_name,
        "clv_bps": round(avg * 10000.0, 2),
        "n": len(diffs),
    }


def summarize(model_name: str, windows_days: tuple[int, ...] = (14, 30)) -> dict[str, Any]:
    """Convenience: brier + ROI + CLV for each requested trailing window."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out: dict[str, Any] = {"model_name": model_name, "windows": {}}
    for days in windows_days:
        since = now - timedelta(days=days)
        out["windows"][str(days)] = {
            "brier": brier_scores(model_name, since),
            "matchup_roi": matchup_roi(model_name, since),
            "clv": clv_summary(model_name, since),
        }
    return out


def summarize_all(windows_days: tuple[int, ...] = (14, 30)) -> dict[str, Any]:
    """Champion + every challenger. Reads CHAMPION/CHALLENGERS from config."""
    from src import config

    models: list[str] = [config.CHAMPION, *list(config.CHALLENGERS)]
    # Dedup while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in models:
        if name and name not in seen:
            ordered.append(name)
            seen.add(name)
    return {
        "champion": config.CHAMPION,
        "challengers": list(config.CHALLENGERS),
        "windows_days": list(windows_days),
        "models": [summarize(name, windows_days) for name in ordered],
    }
