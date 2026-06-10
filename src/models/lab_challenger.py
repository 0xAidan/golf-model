"""Lab challenger model for the champion-challenger shadow rails (engine-scale H-6).

Wraps the promoted matchup-lab champion (trial 327) as a ``BaseModel`` so its matchup
predictions are recorded into ``challenger_predictions`` on the SAME rows the live champion
prices. This lets us accumulate live shadow Brier/CLV for the challenger without it ever
pricing a live bet (the live pipeline never reads challenger output).

Activated only when ``LAB_CHALLENGER_SHADOW_ENABLED`` is set (``config.CHALLENGERS`` includes
``lab_trial327``); default OFF so we don't add per-tick DB writes until opted in.
"""

from __future__ import annotations

import math
from typing import Any

from src.models.base import BaseModel

_CHALLENGER_NAME = "lab_trial327"
_lab_platt: tuple[float, float] | None = None


def _lab_platt_params() -> tuple[float, float]:
    """Lab Platt (a, b), read once from the promoted lab bundle (falls back to config)."""
    global _lab_platt
    if _lab_platt is not None:
        return _lab_platt
    a, b = -0.1, 0.18
    try:
        from src.lab_champion import build_lab_pipeline_config, load_lab_champion_strategy

        cfg = build_lab_pipeline_config(load_lab_champion_strategy())
        a = float(cfg.get("platt_a", a))
        b = float(cfg.get("platt_b", b))
    except Exception:
        pass
    _lab_platt = (a, b)
    return _lab_platt


class LabChallengerModel(BaseModel):
    name = _CHALLENGER_NAME
    version = "v5"

    def predict_matchup(
        self,
        p1: dict[str, Any],
        p2: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        """P(p1 wins) using the lab's v5 uncertainty-aware pricing + lab Platt params."""
        composite_gap = features.get("composite_gap")
        if composite_gap is None:
            composite_gap = float(p1.get("composite", 0.0)) - float(p2.get("composite", 0.0))
        composite_gap = float(composite_gap)
        a, b = _lab_platt_params()
        if composite_gap == 0:
            return 0.5
        favored_is_p1 = composite_gap > 0
        favored, opp = (p1, p2) if favored_is_p1 else (p2, p1)
        try:
            from src.models.v5_probabilities import v5_matchup_win_probability

            favored_prob, _unc = v5_matchup_win_probability(
                composite_gap=composite_gap,
                pick_data=favored,
                opp_data=opp,
                platt_a=a,
                platt_b=b,
            )
        except Exception:
            favored_prob = 1.0 / (1.0 + math.exp(a * abs(composite_gap) + b))
        favored_prob = max(0.0, min(1.0, float(favored_prob)))
        return favored_prob if favored_is_p1 else (1.0 - favored_prob)

    def predict_outright(
        self,
        player: dict[str, Any],
        features: dict[str, Any],
    ) -> float:
        return float(player.get("model_prob", 0.0) or 0.0)
