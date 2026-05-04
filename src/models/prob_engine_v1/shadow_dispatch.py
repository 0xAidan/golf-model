"""Dispatch shadow Monte Carlo v1 vs v2 (mutually prefer v2 when enabled)."""

from __future__ import annotations

from typing import Any

from src import config
from src.models.prob_engine_v1.shadow_mc import run_field_simulation_v1


def run_shadow_field_simulation(
    field: list[tuple[str, float]],
    rankings: list[dict],
    *,
    seed: int,
) -> dict[str, Any]:
    """Run v2 when its gate is on; otherwise v1 (caller must gate on is_any_shadow_monte_carlo_enabled)."""
    from src.models.prob_engine_v1 import shadow_mc_v2 as sm2

    if sm2.is_shadow_monte_carlo_v2_enabled():
        return sm2.run_field_simulation_v2(
            field,
            n_sims=int(getattr(config, "SHADOW_MC_N_SIMS", 2000)),
            base_score_noise=float(getattr(config, "SHADOW_MC_SCORE_NOISE", 2.5)),
            field_correlation=float(getattr(config, "SHADOW_MC_FIELD_CORR", 0.12)),
            cut_keep_frac=float(getattr(config, "SHADOW_MC_CUT_KEEP_FRAC", 0.58)),
            rankings_for_context=rankings,
            seed=seed,
        )
    return run_field_simulation_v1(
        field,
        n_sims=int(getattr(config, "SHADOW_MC_N_SIMS", 2000)),
        score_noise=float(getattr(config, "SHADOW_MC_SCORE_NOISE", 2.5)),
        seed=seed,
    )
