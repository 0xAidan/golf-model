"""
Logging-first contextual summaries for shadow payloads (no live EV coupling).

Milestone C lightweight delivery: weather adjustment aggregates, field structure
proxies, leader spread — all optional and safe when keys are missing.
"""

from __future__ import annotations

from typing import Any


def build_shadow_contextual_meta(rankings: list[dict]) -> dict[str, Any]:
    """Derive a small JSON-serializable dict from snapshot ranking rows."""
    if not rankings:
        return {}

    weather_vals: list[float] = []
    for r in rankings:
        w = r.get("weather_adjustment")
        if w is None:
            continue
        try:
            weather_vals.append(float(w))
        except (TypeError, ValueError):
            continue

    cf_fm_spreads: list[float] = []
    for r in rankings:
        try:
            cf = float(r.get("course_fit") or 0.0)
            fm = float(r.get("form") or 0.0)
            cf_fm_spreads.append(cf - fm)
        except (TypeError, ValueError):
            continue

    comps: list[float] = []
    for r in rankings:
        c = r.get("composite")
        if c is None:
            continue
        try:
            comps.append(float(c))
        except (TypeError, ValueError):
            continue

    leader_margin = None
    if len(comps) >= 2:
        sorted_c = sorted(comps, reverse=True)
        anchor = sorted_c[min(9, len(sorted_c) - 1)]
        leader_margin = round(sorted_c[0] - anchor, 4)

    def _mean(xs: list[float]) -> float | None:
        if not xs:
            return None
        return round(sum(xs) / len(xs), 4)

    def _stdev(xs: list[float]) -> float | None:
        if len(xs) < 2:
            return None
        m = sum(xs) / len(xs)
        v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
        return round(v ** 0.5, 4)

    return {
        "n_rankings": len(rankings),
        "weather_adjustment_mean": _mean(weather_vals),
        "weather_adjustment_n": len(weather_vals),
        "course_fit_minus_form_stdev": _stdev(cf_fm_spreads),
        "leader_margin_composite_vs_p10": leader_margin,
    }
