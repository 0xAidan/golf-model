"""
Diagnostics for probability mass, placement sums, and simple monotonicity.

Used by tests and optional reporting — does not mutate model outputs.
"""

from __future__ import annotations

from typing import Any

from src.value import model_score_to_prob


def softmax_field_sum(composite_results: list[dict], bet_type: str, field_strength: str = "average") -> float:
    """Sum of softmax fallback probabilities for ``bet_type`` across the composite list."""
    scores = [float(r["composite"]) for r in composite_results]
    if not scores:
        return 0.0
    return sum(model_score_to_prob(s, scores, bet_type, field_strength) for s in scores)


def dg_market_sums(
    dg_probs: dict[str, dict[str, float]],
    market_keys: tuple[str, ...],
) -> dict[str, float]:
    """Sum DG-stored probabilities per logical market key (e.g. ``top5``, ``top10``)."""
    out: dict[str, float] = {k: 0.0 for k in market_keys}
    for _pk, mp in dg_probs.items():
        if not isinstance(mp, dict):
            continue
        for k in market_keys:
            v = mp.get(k)
            if v is not None and isinstance(v, (int, float)):
                out[k] += float(v)
    return out


def monotonicity_violations_for_player(
    dg_row: dict[str, float] | None,
    *,
    chain: tuple[tuple[str, str], ...] = (
        ("outright", "top5"),
        ("top5", "top10"),
        ("top10", "top20"),
    ),
) -> list[str]:
    """
    If DG provides both ends of a chain, check p(low) <= p(high) for the same player.

    Uses baseline keys (not _ch) when both exist; otherwise CH keys.
    """
    if not dg_row:
        return []
    issues: list[str] = []

    def _pick(base: str) -> float | None:
        ch = f"{base}_ch"
        if base in dg_row and dg_row[base] is not None:
            return float(dg_row[base])
        if ch in dg_row and dg_row[ch] is not None:
            return float(dg_row[ch])
        return None

    for low, high in chain:
        p_lo = _pick(low)
        p_hi = _pick(high)
        if p_lo is None or p_hi is None:
            continue
        if p_lo > p_hi + 1e-6:
            issues.append(f"{low} {p_lo:.4f} > {high} {p_hi:.4f}")

    return issues


def summarize_field_probability_health(
    composite_results: list[dict],
    dg_probs: dict[str, dict[str, float]] | None,
    bet_types: tuple[str, ...] = ("outright", "top5", "top10", "top20"),
) -> dict[str, Any]:
    """Aggregate softmax sums and DG sums for audit surfaces."""
    dg_probs = dg_probs or {}
    softmax_sums = {bt: softmax_field_sum(composite_results, bt) for bt in bet_types}
    dg_sums = dg_market_sums(dg_probs, bet_types)

    expected = {
        "outright": 1.0,
        "top5": 5.0,
        "top10": 10.0,
        "top20": 20.0,
    }
    softmax_flags = {
        bt: abs(softmax_sums[bt] - expected.get(bt, 1.0)) <= (0.15 if bt != "outright" else 0.08)
        for bt in bet_types
    }
    dg_flags = {}
    for bt, s in dg_sums.items():
        exp = expected.get(bt)
        if exp is None:
            continue
        dg_flags[bt] = abs(s - exp) / max(exp, 1.0) < 0.12

    mono_sample = 0
    mono_issues = 0
    for pk, row in list(dg_probs.items())[: min(30, len(dg_probs))]:
        viol = monotonicity_violations_for_player(row if isinstance(row, dict) else None)
        mono_sample += 1
        mono_issues += len(viol)

    return {
        "softmax_sums": softmax_sums,
        "dg_sums": dg_sums,
        "softmax_near_expected": softmax_flags,
        "dg_near_expected": dg_flags,
        "monotonicity_sample_players": mono_sample,
        "monotonicity_violation_count": mono_issues,
        "top15_note": (
            "top15 is not in softmax/DG expected-sum tables; pipeline skips top15 "
            "value bets until fully wired."
        ),
    }
