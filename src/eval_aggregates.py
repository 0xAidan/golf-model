"""Per-track evaluation aggregates for the eval/validity platform.

Computes live graded metrics per model track (champion = cockpit lane, challenger = lab
lane) from the canonical stores: ``picks`` + ``pick_outcomes`` (graded, +EV-only per the
grading trust contract). Metrics are 1-unit flat (ROI, hit rate, Brier) so they are
comparable across tracks, plus pick overlap between the two tracks.

This is *live graded* data only — deliberately segregated from sim/walk-forward numbers
(which live in `output/research/`) so the May-audit confusion (+30% sim vs -16% live) can't
recur in the product.
"""

from __future__ import annotations

from typing import Any

from src import db
from src.odds_utils import american_to_decimal

_SOURCES = {
    "cockpit": ("cockpit", "ui_display"),
    "lab": ("lab_sandbox", "lab_sandbox_candidate"),
}


def _one_unit_profit(hit: int | None, odds_decimal: float | None, market_odds: str | None) -> float | None:
    """1-unit flat P/L: win => decimal_odds-1, loss => -1. None when odds unknown."""
    dec = odds_decimal
    if dec is None and market_odds:
        try:
            dec = american_to_decimal(int(str(market_odds).replace("+", "")))
        except Exception:
            dec = None
    if dec is None or dec <= 1.0:
        return None
    if hit is None:
        return None
    return (dec - 1.0) if hit == 1 else -1.0


def _aggregate_rows(rows: list[Any]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for r in rows if r["hit"] == 1)
    profits = [
        p
        for r in rows
        if (p := _one_unit_profit(r["hit"], r["odds_decimal"], r["market_odds"])) is not None
    ]
    brier_terms = [
        (float(r["model_prob"]) - float(r["hit"])) ** 2
        for r in rows
        if r["model_prob"] is not None and r["hit"] is not None
    ]
    staked = len(profits)
    pnl = sum(profits)
    return {
        "n": n,
        "graded_with_odds": staked,
        "wins": wins,
        "hit_rate_pct": round((wins / n) * 100, 2) if n else None,
        "roi_pct": round((pnl / staked) * 100, 2) if staked else None,
        "pnl_units": round(pnl, 3) if staked else None,
        "brier": round(sum(brier_terms) / len(brier_terms), 6) if brier_terms else None,
        "low_sample": n < 30,
    }


def _fetch_track_rows(conn, sources: tuple[str, ...], window_days: int, market: str | None, book: str | None):
    clauses = [
        "p.source IN (%s)" % ",".join("?" * len(sources)),
        "p.ev > 0",
        "p.created_at >= datetime('now', ?)",
    ]
    params: list[Any] = [*sources, f"-{int(window_days)} days"]
    if market:
        clauses.append("p.bet_type = ?")
        params.append(market)
    if book:
        clauses.append("p.market_book = ?")
        params.append(book)
    where = " AND ".join(clauses)
    return conn.execute(
        f"""
        SELECT p.player_key, p.opponent_key, p.bet_type, p.market_book, p.model_prob,
               p.market_odds, po.hit, po.odds_decimal
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE {where}
        """,
        params,
    ).fetchall()


def track_comparison(
    *,
    window_days: int = 30,
    market: str | None = None,
    book: str | None = None,
) -> dict[str, Any]:
    """Side-by-side champion (cockpit) vs challenger (lab) live-graded metrics + overlap."""
    db.ensure_initialized()
    conn = db.get_conn()
    try:
        track_rows = {
            track: _fetch_track_rows(conn, sources, window_days, market, book)
            for track, sources in _SOURCES.items()
        }
    finally:
        conn.close()

    tracks = {track: _aggregate_rows(rows) for track, rows in track_rows.items()}

    # Pick overlap on (player, opponent, bet_type) within the window.
    def _keys(rows):
        return {
            (str(r["player_key"]).lower(), str(r["opponent_key"] or "").lower(), str(r["bet_type"]).lower())
            for r in rows
        }

    cockpit_keys = _keys(track_rows["cockpit"])
    lab_keys = _keys(track_rows["lab"])
    overlap = cockpit_keys & lab_keys

    # by-market breakdown per track
    by_market: dict[str, dict[str, Any]] = {}
    for track, rows in track_rows.items():
        markets: dict[str, list[Any]] = {}
        for r in rows:
            markets.setdefault(str(r["bet_type"]), []).append(r)
        by_market[track] = {m: _aggregate_rows(rs) for m, rs in markets.items()}

    return {
        "window_days": window_days,
        "market": market,
        "book": book,
        "tracks": tracks,
        "overlap": {
            "both": len(overlap),
            "cockpit_only": len(cockpit_keys - lab_keys),
            "lab_only": len(lab_keys - cockpit_keys),
        },
        "by_market": by_market,
        "data_kind": "live_graded",
        "note": "Live graded +EV picks only (1-unit flat). Not sim/walk-forward; see output/research/ for backtests.",
    }
