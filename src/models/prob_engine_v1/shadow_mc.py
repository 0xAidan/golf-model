"""
Shadow Monte Carlo v1 — tournament-style ordinal simulation from composite scores.

Output is for offline analytics only; callers must not feed this into live EV.
"""

from __future__ import annotations

import random
from typing import Any

ENGINE_VERSION = "prob_engine_v1.0"


def run_field_simulation_v1(
    field: list[tuple[str, float]],
    *,
    n_sims: int,
    score_noise: float,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Run independent simulations: perturb each composite with Gaussian noise and
    rank the field. Aggregate empirical frequencies for outright / top5 / top10 / top20.

    field: list of (player_key, composite_score).
    """
    rng = random.Random(seed)
    n = len(field)
    if n == 0 or n_sims <= 0:
        return {
            "engine_version": ENGINE_VERSION,
            "n_sims": 0,
            "field_size": 0,
            "score_noise": score_noise,
            "player_summary": {},
        }

    keys = [str(k).strip().lower() for k, _ in field]
    base_scores = [float(s) for _, s in field]

    win_c: dict[str, int] = {k: 0 for k in keys}
    top5_c: dict[str, int] = {k: 0 for k in keys}
    top10_c: dict[str, int] = {k: 0 for k in keys}
    top20_c: dict[str, int] = {k: 0 for k in keys}

    for _ in range(n_sims):
        perturbed = [base_scores[i] + rng.gauss(0.0, score_noise) for i in range(n)]
        order = sorted(range(n), key=lambda i: perturbed[i], reverse=True)
        win_c[keys[order[0]]] += 1
        for i in order[:5]:
            top5_c[keys[i]] += 1
        for i in order[:10]:
            top10_c[keys[i]] += 1
        for i in order[:20]:
            top20_c[keys[i]] += 1

    ns = float(n_sims)
    summary: dict[str, dict[str, float]] = {}
    for i, k in enumerate(keys):
        summary[k] = {
            "composite": round(base_scores[i], 4),
            "p_outright": round(win_c[k] / ns, 6),
            "p_top5": round(top5_c[k] / ns, 6),
            "p_top10": round(top10_c[k] / ns, 6),
            "p_top20": round(top20_c[k] / ns, 6),
        }

    return {
        "engine_version": ENGINE_VERSION,
        "n_sims": n_sims,
        "field_size": n,
        "score_noise": score_noise,
        "player_summary": summary,
    }


def is_shadow_monte_carlo_enabled() -> bool:
    """True when shadow MC should run (env or feature flag). Default off."""
    import os

    if os.environ.get("SHADOW_MC_V1", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    from src.feature_flags import is_enabled

    return is_enabled("shadow_monte_carlo_v1")


def is_any_shadow_monte_carlo_enabled() -> bool:
    """True if v1 or v2 shadow engine should run (separate gates)."""
    if is_shadow_monte_carlo_enabled():
        return True
    from src.models.prob_engine_v1 import shadow_mc_v2 as sm2

    return sm2.is_shadow_monte_carlo_v2_enabled()
