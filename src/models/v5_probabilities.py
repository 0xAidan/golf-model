"""
Experimental v5 probability helpers.

These functions are intentionally isolated from the baseline path so we can
run A/B comparisons without changing baseline behavior.
"""

from __future__ import annotations

import math

from src import config
def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def estimate_player_uncertainty(
    player_row: dict | None,
    *,
    field_strength_index: float | None = None,
) -> float:
    """
    Estimate a 0-1 uncertainty score from existing model features.

    Lower uncertainty -> preserve edge signal.
    Higher uncertainty -> shrink probabilities toward 50/50.
    """
    if not player_row:
        return 0.35

    confidence = player_row.get("course_confidence")
    confidence_penalty = 0.0
    if isinstance(confidence, (int, float)):
        confidence_penalty = _clamp((0.85 - float(confidence)) / 0.85, 0.0, 0.6)

    momentum = player_row.get("momentum")
    momentum_penalty = 0.0
    if isinstance(momentum, (int, float)):
        # Neutral-ish momentum has less predictive value than strong trend.
        momentum_penalty = _clamp((1.0 - abs(float(momentum) - 50.0) / 25.0) * 0.25, 0.0, 0.25)

    form_flags = player_row.get("form_flags") or []
    flag_penalty = 0.05 * len(form_flags)

    fs_penalty = 0.0
    if field_strength_index is not None:
        try:
            fi = float(field_strength_index)
        except (TypeError, ValueError):
            fi = 0.5
        # Weaker fields (index below 0.5) → modest uncertainty bump (research: field strength).
        fs_penalty = max(0.0, (0.5 - fi)) * float(
            getattr(config, "V5_UNCERTAINTY_FIELD_STRENGTH_COEF", 0.12)
        )

    base = 0.20
    return _clamp(
        base + confidence_penalty + momentum_penalty + flag_penalty + fs_penalty,
        0.05,
        0.90,
    )


def v5_matchup_win_probability(
    *,
    composite_gap: float,
    pick_data: dict | None,
    opp_data: dict | None,
    platt_a: float,
    platt_b: float,
) -> tuple[float, float]:
    """
    Return (win_probability, uncertainty_score) for matchup A/B lane.
    """
    gap = abs(float(composite_gap))
    raw_prob = 1.0 / (1.0 + math.exp(platt_a * gap + platt_b))

    fs_idx = None
    if isinstance(pick_data, dict):
        fs_idx = pick_data.get("field_strength_index")
    if fs_idx is None and isinstance(opp_data, dict):
        fs_idx = opp_data.get("field_strength_index")

    pick_unc = estimate_player_uncertainty(pick_data, field_strength_index=fs_idx)
    opp_unc = estimate_player_uncertainty(opp_data, field_strength_index=fs_idx)
    uncertainty = _clamp((pick_unc + opp_unc) / 2.0, 0.05, 0.90)

    # Shrink toward 50/50 under uncertainty.
    shrunk_prob = 0.5 + (raw_prob - 0.5) * (1.0 - uncertainty)
    return (_clamp(shrunk_prob, 0.01, 0.99), uncertainty)


def v5_threeball_probabilities(players: list[dict], *, base_temp: float = 10.0) -> list[float]:
    """
    Compute 3-ball probabilities with uncertainty-aware score shrinkage.

    players: [{composite: float, ...}, ...]
    """
    if not players:
        return []

    effective_scores: list[float] = []
    uncertainties: list[float] = []
    for row in players:
        score = float(row.get("composite", 50.0))
        unc = estimate_player_uncertainty(row)
        uncertainties.append(unc)
        # Pull noisy profiles toward neutral 50 score.
        effective = 50.0 + (score - 50.0) * (1.0 - unc)
        effective_scores.append(effective)

    avg_uncertainty = sum(uncertainties) / max(len(uncertainties), 1)
    temp = base_temp * (1.0 + avg_uncertainty * 0.6)

    max_score = max(effective_scores)
    exps = [math.exp((score - max_score) / temp) for score in effective_scores]
    total = sum(exps)
    if total <= 0:
        return [1.0 / len(players)] * len(players)
    return [value / total for value in exps]
