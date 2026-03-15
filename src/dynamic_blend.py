"""
Dynamic blend (EWA) for placement markets.

Uses per-source Brier loss to adapt DG vs model weight over time.
When feature flag dynamic_blend is off, uses static config.get_blend_weights.
When on: after each tournament records Brier for dg_only, model_only, blended;
after 5+ tournaments applies EWA update with floor 10% / ceiling 50% model weight.
"""

import logging
import math

from src import config
from src import db
from src.feature_flags import is_enabled

logger = logging.getLogger(__name__)

EWA_LR = 0.03
MODEL_WEIGHT_FLOOR = 0.10
MODEL_WEIGHT_CEILING = 0.50
MIN_TOURNAMENTS_FOR_EWA = 5
DRIFT_WORSE_PCT = 0.15  # flag if blend Brier >15% worse than DG-only


def get_blend_ratio(bet_type: str) -> tuple[float, float]:
    """
    Return (dg_weight, model_weight) for the given bet type.
    When dynamic_blend flag is off, uses config. When on, uses last blend_history
    and applies EWA (if 5+ tournaments) to derive next weights.
    """
    if not is_enabled("dynamic_blend"):
        return config.get_blend_weights(bet_type)

    conn = db.get_conn()
    row = conn.execute(
        """SELECT dg_weight, model_weight, brier_blended FROM blend_history
           WHERE bet_type = ? ORDER BY id DESC LIMIT 1""",
        (bet_type,),
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(DISTINCT tournament_id) AS c FROM blend_history WHERE bet_type = ?",
        (bet_type,),
    ).fetchone()["c"]
    conn.close()
    if not row:
        return config.get_blend_weights(bet_type)
    dg_w = float(row["dg_weight"])
    model_w = float(row["model_weight"])
    brier_blended = row["brier_blended"]
    if count >= MIN_TOURNAMENTS_FOR_EWA and brier_blended is not None:
        new_model = model_w * math.exp(-EWA_LR * brier_blended)
        new_model = max(MODEL_WEIGHT_FLOOR, min(MODEL_WEIGHT_CEILING, new_model))
        return (1.0 - new_model, new_model)
    return (dg_w, model_w)


def _brier_score(probs: list[float], outcomes: list[int]) -> float:
    """Brier score: (1/n) * sum((p - y)^2). Lower is better."""
    if not probs or len(probs) != len(outcomes):
        return 0.0
    n = len(probs)
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / n


def record_tournament_brier(
    tournament_id: int,
    brier_data: dict[str, dict],
) -> None:
    """
    Record per-source Brier for this tournament and optionally run EWA update.

    brier_data: {bet_type: {"brier_dg": float, "brier_model": float, "brier_blended": float,
                  "n_predictions": int, "dg_weight": float, "model_weight": float}}
    """
    if not brier_data:
        return

    conn = db.get_conn()
    for bet_type, data in brier_data.items():
        brier_dg = data.get("brier_dg")
        brier_model = data.get("brier_model")
        brier_blended = data.get("brier_blended")
        n = data.get("n_predictions", 0)
        dg_weight = data.get("dg_weight")
        model_weight = data.get("model_weight")
        if dg_weight is None or model_weight is None:
            dg_weight, model_weight = config.get_blend_weights(bet_type)

        conn.execute(
            """INSERT INTO blend_history
               (tournament_id, bet_type, brier_dg, brier_model, brier_blended,
                n_predictions, dg_weight, model_weight)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tournament_id, bet_type, brier_dg, brier_model, brier_blended,
             n, dg_weight, model_weight),
        )
        # Drift check: blend Brier >15% worse than DG-only
        if brier_dg is not None and brier_blended is not None and brier_dg > 0:
            if brier_blended >= brier_dg * (1 + DRIFT_WORSE_PCT):
                logger.warning(
                    "Blend drift: %s blended Brier %.4f is >15%% worse than DG-only %.4f",
                    bet_type, brier_blended, brier_dg,
                )
    conn.commit()
    conn.close()


def compute_brier_from_bets(value_bets_by_type: dict, result_map: dict, outcomes_fn) -> dict:
    """
    Compute per-source Brier from value_bets_by_type and results.
    outcomes_fn(bet_type, player_key, result_map, all_results) -> actual (0 or 1).

    Returns brier_data suitable for record_tournament_brier (without dg_weight/model_weight).
    """
    from src.config import get_blend_weights

    brier_data = {}
    for bet_type, bets in value_bets_by_type.items():
        dg_probs = []
        model_probs = []
        blended_probs = []
        outcomes = []
        for bet in bets:
            pk = bet.get("player_key")
            actual = outcomes_fn(pk, result_map) if outcomes_fn else 0
            dg_only = bet.get("dg_only_prob")
            model_only = bet.get("model_only_prob")
            blended = bet.get("blended_prob") or bet.get("model_prob")
            if dg_only is not None or model_only is not None or blended is not None:
                if actual is None:
                    continue
                dg_probs.append(dg_only if dg_only is not None else 0.0)
                model_probs.append(model_only if model_only is not None else 0.0)
                blended_probs.append(blended if blended is not None else 0.0)
                outcomes.append(1 if actual else 0)
        if not outcomes:
            continue
        brier_dg = _brier_score(dg_probs, outcomes) if dg_probs else None
        brier_model = _brier_score(model_probs, outcomes) if model_probs else None
        brier_blended = _brier_score(blended_probs, outcomes) if blended_probs else None
        dg_w, model_w = get_blend_weights(bet_type)
        brier_data[bet_type] = {
            "brier_dg": brier_dg,
            "brier_model": brier_model,
            "brier_blended": brier_blended,
            "n_predictions": len(outcomes),
            "dg_weight": dg_w,
            "model_weight": model_w,
        }
    return brier_data
