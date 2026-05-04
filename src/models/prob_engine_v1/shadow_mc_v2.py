"""
Shadow Monte Carlo v2 — correlated field noise, optional cut, rounds-based SD.

Offline analytics only; do not feed outputs into live EV.
"""

from __future__ import annotations

import math
import os
import random
from typing import Any

from src.models.prob_engine_v1.contextual import build_shadow_contextual_meta
from src.models.prob_engine_v1.rounds_sg import fit_player_round_sg

ENGINE_VERSION_V2 = "prob_engine_v2.0"


def is_shadow_monte_carlo_v2_enabled() -> bool:
    """v2 when env SHADOW_MC_ENGINE=v2 or feature flag shadow_monte_carlo_v2."""
    eng = (os.environ.get("SHADOW_MC_ENGINE", "") or "").strip().lower()
    if eng in ("v2", "2", "mc2"):
        return True
    from src.feature_flags import is_enabled

    return is_enabled("shadow_monte_carlo_v2")


def run_field_simulation_v2(
    field: list[tuple[str, float]],
    *,
    n_sims: int,
    base_score_noise: float,
    field_correlation: float = 0.12,
    cut_keep_frac: float = 0.58,
    rankings_for_context: list[dict] | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Correlated Gaussian shocks + per-player SD from ``fit_player_round_sg``,
    optional proportional cut, then placement counts among survivors.

    - Higher composite = better (same convention as v1).
    - ``cut_keep_frac``: fraction of field (top by simulated score) that "makes cut"
      before placement markets are evaluated among survivors only.
    """
    rng = random.Random(seed)
    n = len(field)
    if n == 0 or n_sims <= 0:
        return {
            "engine_version": ENGINE_VERSION_V2,
            "n_sims": 0,
            "field_size": 0,
            "base_score_noise": base_score_noise,
            "field_correlation": field_correlation,
            "cut_keep_frac": cut_keep_frac,
            "player_summary": {},
            "contextual": build_shadow_contextual_meta(rankings_for_context or []),
        }

    keys = [str(k).strip().lower() for k, _ in field]
    base_scores = [float(s) for _, s in field]
    rho = max(0.0, min(0.95, float(field_correlation)))
    keep = min(n, max(1, int(math.ceil(float(cut_keep_frac) * n))))

    sg_fit = fit_player_round_sg(keys)
    sigma_i = [float(sg_fit.get(k, {}).get("sd_sg") or base_score_noise) for k in keys]
    sigma_bar = sum(sigma_i) / max(len(sigma_i), 1)

    win_c: dict[str, int] = {k: 0 for k in keys}
    top5_c: dict[str, int] = {k: 0 for k in keys}
    top10_c: dict[str, int] = {k: 0 for k in keys}
    top20_c: dict[str, int] = {k: 0 for k in keys}
    made_cut_c: dict[str, int] = {k: 0 for k in keys}

    sqrt_rho = math.sqrt(rho)
    sqrt_1mr = math.sqrt(max(0.0, 1.0 - rho))

    for _ in range(n_sims):
        z_field = rng.gauss(0.0, 1.0)
        scores: list[float] = []
        for i in range(n):
            e_i = rng.gauss(0.0, 1.0)
            shock = sqrt_rho * sigma_bar * z_field + sqrt_1mr * sigma_i[i] * e_i
            scores.append(base_scores[i] + shock)

        order_full = sorted(range(n), key=lambda i: scores[i], reverse=True)
        survivors = set(order_full[:keep])
        for i in survivors:
            made_cut_c[keys[i]] += 1

        surv_order = sorted(survivors, key=lambda i: scores[i], reverse=True)
        if not surv_order:
            continue
        win_c[keys[surv_order[0]]] += 1
        for idx in surv_order[:5]:
            top5_c[keys[idx]] += 1
        for idx in surv_order[:10]:
            top10_c[keys[idx]] += 1
        for idx in surv_order[: min(20, len(surv_order))]:
            top20_c[keys[idx]] += 1

    ns = float(n_sims)
    summary: dict[str, dict[str, float]] = {}
    for i, k in enumerate(keys):
        fit = sg_fit.get(k, {})
        summary[k] = {
            "composite": round(base_scores[i], 4),
            "sd_sg_fitted": float(fit.get("sd_sg") or base_score_noise),
            "p_make_cut": round(made_cut_c[k] / ns, 6),
            "p_outright": round(win_c[k] / ns, 6),
            "p_top5": round(top5_c[k] / ns, 6),
            "p_top10": round(top10_c[k] / ns, 6),
            "p_top20": round(top20_c[k] / ns, 6),
        }

    return {
        "engine_version": ENGINE_VERSION_V2,
        "n_sims": n_sims,
        "field_size": n,
        "base_score_noise": base_score_noise,
        "field_correlation": rho,
        "cut_keep_frac": cut_keep_frac,
        "cut_survivors_k": keep,
        "player_summary": summary,
        "rounds_sg_fit": sg_fit,
        "contextual": build_shadow_contextual_meta(rankings_for_context or []),
    }
