"""
Marketing / public-post gates — stricter than internal ``is_value``.

Internal rows can show positive EV from ``ev_prob`` while the card still labels
probabilities as blended pre-calibration; public copy must not treat fragile
long-shots as high-conviction picks.
"""

from __future__ import annotations

from typing import Any

from src import config


def _american_int(row: dict[str, Any]) -> int:
    v = row.get("best_odds")
    if v is None:
        v = row.get("odds")
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def assess_placement_marketing(row: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (marketing_safe, warnings) for an outright / placement / prop row."""
    warnings: list[str] = []
    bt = str(row.get("bet_type") or "outright")
    ev_prob = float(row.get("ev_prob", row.get("model_prob", 0)) or 0.0)
    market_raw = float(
        row.get("market_implied_prob_raw", row.get("market_prob", 0)) or 0.0
    )
    ev = float(row.get("ev", 0) or 0.0)
    price = _american_int(row)

    min_edge_map = getattr(config, "MARKETING_MIN_ABSOLUTE_EDGE_BY_TYPE", {})
    min_edge = float(min_edge_map.get(bt, 0.02))
    abs_edge = ev_prob - market_raw

    max_ev_map = getattr(config, "MARKETING_MAX_EV_PUBLIC_BY_TYPE", {})
    max_ev = float(max_ev_map.get(bt, max_ev_map.get("outright", 1.5)))

    safe = True
    if abs_edge < min_edge:
        safe = False
        warnings.append(
            f"absolute edge {abs_edge:.3%} below marketing floor {min_edge:.3%} for {bt}"
        )

    if ev > max_ev:
        safe = False
        warnings.append(f"EV {ev:.1%} exceeds public cap {max_ev:.1%} for {bt}")

    outright_cap = int(getattr(config, "MARKETING_MAX_AMERICAN_FOR_PUBLIC_OUTRIGHT", 15000))
    longshot_thr = int(getattr(config, "MARKETING_LONGSHOT_AMERICAN_OUTRIGHT", 8000))
    longshot_min_edge = float(getattr(config, "MARKETING_MIN_ABS_EDGE_LONGSHOT_OUTRIGHT", 0.004))
    max_ev_long = float(getattr(config, "MARKETING_MAX_EV_PUBLIC_LONGSHOT_OUTRIGHT", 0.35))

    if bt == "outright":
        if price > outright_cap:
            safe = False
            warnings.append(f"outright odds +{price} above public post maximum (+{outright_cap})")
        if price >= longshot_thr:
            if abs_edge < longshot_min_edge:
                safe = False
                warnings.append(
                    f"long-shot outright (+{price}): edge {abs_edge:.3%} below "
                    f"{longshot_min_edge:.3%} required for public posts"
                )
            if ev > max_ev_long:
                safe = False
                warnings.append(
                    f"long-shot outright EV {ev:.1%} capped for public display "
                    f"(max {max_ev_long:.1%})"
                )

    if row.get("suspicious") or row.get("speculative") or row.get("ev_capped"):
        safe = False
        if row.get("suspicious"):
            warnings.append("row flagged suspicious (model vs market)")
        if row.get("speculative"):
            warnings.append("row flagged speculative (model vs market)")
        if row.get("ev_capped"):
            warnings.append("EV was capped — not suitable as a public headline")

    oq = row.get("odds_quality") or {}
    if isinstance(oq, dict) and oq.get("stale_odds"):
        safe = False
        warnings.append("stale odds flagged in odds_quality")

    return safe, warnings


def assess_matchup_marketing(row: dict[str, Any]) -> tuple[bool, list[str]]:
    """Head-to-head rows: require a minimum absolute edge on win probability."""
    warnings: list[str] = []
    model_wp = float(row.get("ev_prob", row.get("model_win_prob", 0)) or 0.0)
    implied = float(
        row.get("market_implied_prob_raw", row.get("implied_prob", 0)) or 0.0
    )
    ev = float(row.get("ev", 0) or 0.0)
    abs_edge = model_wp - implied
    min_edge = float(getattr(config, "MARKETING_MIN_ABSOLUTE_EDGE_MATCHUP", 0.03))
    max_ev = float(getattr(config, "MARKETING_MAX_EV_PUBLIC_MATCHUP", 0.45))

    safe = True
    if abs_edge < min_edge:
        safe = False
        warnings.append(
            f"matchup edge {abs_edge:.3%} below marketing minimum {min_edge:.3%}"
        )
    if ev > max_ev:
        safe = False
        warnings.append(f"matchup EV {ev:.1%} exceeds public cap {max_ev:.1%}")
    return safe, warnings
