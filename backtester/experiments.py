"""
Experiment Tracking & Strategy Promotion Pipeline

Manages the lifecycle of strategy experiments:
  1. Create: Register a hypothesis + strategy config
  2. Run: Execute simulation and store results
  3. Evaluate: Statistical significance testing
  4. Promote: If significant improvement, update active strategy

The autonomous agent creates experiments; this module tracks and evaluates them.
"""

import json
import logging
import math
from datetime import datetime
from typing import Optional

from src import db
from backtester.strategy import StrategyConfig, SimulationResult, simulate_strategy

logger = logging.getLogger("experiments")


# ═══════════════════════════════════════════════════════════════════
#  Experiment CRUD
# ═══════════════════════════════════════════════════════════════════

def create_experiment(hypothesis: str,
                      strategy: StrategyConfig,
                      source: str = "manual",
                      scope: str = "global") -> int:
    """
    Register a new experiment.

    hypothesis: What we're testing (e.g., "Higher approach weight on links courses")
    source: "manual", "ai_hypothesis", "bayesian_opt", "outlier_insight"
    scope: "global", "links", "parkland", specific course_id, etc.

    Returns experiment id.
    """
    conn = db.get_conn()
    cursor = conn.execute("""
        INSERT OR IGNORE INTO experiments
        (hypothesis, source, strategy_config_json, scope, status)
        VALUES (?,?,?,?,?)
    """, (
        hypothesis, source,
        strategy.to_json(), scope, "pending",
    ))
    conn.commit()

    if cursor.lastrowid:
        logger.info("Created experiment %d: %s", cursor.lastrowid, hypothesis[:80])
        return cursor.lastrowid

    # Already exists, get its id
    row = conn.execute("""
        SELECT id FROM experiments
        WHERE strategy_config_json = ? AND scope = ?
    """, (strategy.to_json(), scope)).fetchone()
    return row[0] if row else 0


def run_experiment(experiment_id: int,
                   years: list[int] = None,
                   tour: str = "pga") -> SimulationResult:
    """
    Execute an experiment's strategy simulation and store results.
    """
    conn = db.get_conn()
    row = conn.execute("""
        SELECT strategy_config_json, scope, status
        FROM experiments WHERE id = ?
    """, (experiment_id,)).fetchone()

    if not row:
        raise ValueError(f"Experiment {experiment_id} not found")

    config_json, scope, status = row
    if status == "completed":
        logger.info("Experiment %d already completed, skipping", experiment_id)
        # Load cached result
        cached = conn.execute(
            "SELECT full_result_json FROM experiments WHERE id = ?",
            (experiment_id,)
        ).fetchone()
        if cached and cached[0]:
            # Return a minimal result
            result_data = json.loads(cached[0])
            strategy = StrategyConfig.from_json(config_json)
            sim = SimulationResult(strategy=strategy)
            sim.roi_pct = result_data.get("roi_pct", 0)
            sim.total_bets = result_data.get("total_bets", 0)
            sim.sharpe = result_data.get("sharpe", 0)
            sim.clv_avg = result_data.get("clv_avg", 0)
            return sim

    strategy = StrategyConfig.from_json(config_json)

    # Mark as running
    conn.execute("""
        UPDATE experiments SET status = 'running', started_at = datetime('now')
        WHERE id = ?
    """, (experiment_id,))
    conn.commit()

    try:
        result = simulate_strategy(strategy, years=years, tour=tour)

        # Store results
        conn.execute("""
            UPDATE experiments SET
                status = 'completed',
                completed_at = datetime('now'),
                tournaments_tested = ?,
                total_bets = ?,
                roi_pct = ?,
                clv_avg = ?,
                sharpe = ?,
                full_result_json = ?
            WHERE id = ?
        """, (
            result.events_simulated,
            result.total_bets,
            result.roi_pct,
            result.clv_avg,
            result.sharpe,
            json.dumps(result.to_dict()),
            experiment_id,
        ))
        conn.commit()

        logger.info("Experiment %d complete: ROI=%.1f%%, bets=%d, Sharpe=%.2f",
                     experiment_id, result.roi_pct, result.total_bets, result.sharpe)
        return result

    except Exception as e:
        conn.execute("""
            UPDATE experiments SET status = 'error',
            full_result_json = ?
            WHERE id = ?
        """, (json.dumps({"error": str(e)}), experiment_id))
        conn.commit()
        raise


def evaluate_significance(experiment_id: int,
                          baseline_roi: float = 0.0,
                          min_bets: int = 50) -> dict:
    """
    Test whether an experiment's results are statistically significant.

    Uses a simple z-test comparing the experiment's ROI to a baseline.
    Requires minimum number of bets for reliability.

    Returns: {significant: bool, p_value: float, vs_baseline_delta: float}
    """
    conn = db.get_conn()
    row = conn.execute("""
        SELECT roi_pct, total_bets, sharpe, full_result_json
        FROM experiments WHERE id = ?
    """, (experiment_id,)).fetchone()

    if not row:
        return {"significant": False, "reason": "not_found"}

    roi, total_bets, sharpe, result_json = row

    if total_bets is None or total_bets < min_bets:
        conn.execute("""
            UPDATE experiments SET is_significant = 0, p_value = NULL
            WHERE id = ?
        """, (experiment_id,))
        conn.commit()
        return {
            "significant": False,
            "reason": f"insufficient_bets ({total_bets or 0} < {min_bets})",
            "total_bets": total_bets or 0,
        }

    # Simple z-test for ROI
    delta = (roi or 0) - baseline_roi
    # Approximate standard error using bet count
    se = 100 / math.sqrt(total_bets) if total_bets > 0 else 100
    z_score = delta / se if se > 0 else 0

    # Two-sided p-value approximation
    p_value = 2 * (1 - _norm_cdf(abs(z_score)))
    is_significant = p_value < 0.05 and delta > 0

    conn.execute("""
        UPDATE experiments SET
            is_significant = ?,
            p_value = ?,
            vs_current_delta = ?
        WHERE id = ?
    """, (
        1 if is_significant else 0,
        round(p_value, 4),
        round(delta, 2),
        experiment_id,
    ))
    conn.commit()

    return {
        "significant": is_significant,
        "p_value": round(p_value, 4),
        "z_score": round(z_score, 3),
        "vs_baseline_delta": round(delta, 2),
        "roi_pct": roi,
        "total_bets": total_bets,
        "sharpe": sharpe,
    }


def _norm_cdf(x: float) -> float:
    """Approximate standard normal CDF using error function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ═══════════════════════════════════════════════════════════════════
#  Strategy Promotion
# ═══════════════════════════════════════════════════════════════════

def promote_strategy(experiment_id: int, scope: str = "global") -> bool:
    """
    Promote an experiment's strategy to active if it's significant and better.

    Returns True if promoted, False otherwise.
    """
    conn = db.get_conn()
    row = conn.execute("""
        SELECT strategy_config_json, roi_pct, is_significant, sharpe
        FROM experiments WHERE id = ?
    """, (experiment_id,)).fetchone()

    if not row:
        logger.warning("Experiment %d not found for promotion", experiment_id)
        return False

    config_json, roi, is_sig, sharpe = row

    if not is_sig:
        logger.info("Experiment %d not significant, skipping promotion", experiment_id)
        return False

    # Check current active strategy
    current = conn.execute("""
        SELECT roi_pct FROM active_strategy WHERE scope = ?
    """, (scope,)).fetchone()

    current_roi = current[0] if current else 0

    if (roi or 0) <= (current_roi or 0):
        logger.info("Experiment %d ROI %.1f%% not better than current %.1f%%",
                     experiment_id, roi or 0, current_roi or 0)
        return False

    # Promote
    conn.execute("""
        INSERT OR REPLACE INTO active_strategy
        (scope, strategy_config_json, experiment_id, roi_pct)
        VALUES (?,?,?,?)
    """, (scope, config_json, experiment_id, roi))

    conn.execute("""
        UPDATE experiments SET promoted = 1 WHERE id = ?
    """, (experiment_id,))
    conn.commit()

    logger.info("PROMOTED experiment %d to active (%s): ROI %.1f%% -> %.1f%%",
                experiment_id, scope, current_roi or 0, roi or 0)
    return True


def get_active_strategy(scope: str = "global") -> Optional[StrategyConfig]:
    """Get the currently active strategy for a scope."""
    conn = db.get_conn()
    row = conn.execute("""
        SELECT strategy_config_json FROM active_strategy WHERE scope = ?
    """, (scope,)).fetchone()

    if row and row[0]:
        try:
            return StrategyConfig.from_json(row[0])
        except Exception:
            pass
    return StrategyConfig()  # Return default


def get_experiment_leaderboard(scope: str = "global",
                               limit: int = 20) -> list[dict]:
    """Get top experiments ranked by ROI."""
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT id, hypothesis, source, roi_pct, total_bets,
               sharpe, clv_avg, is_significant, promoted, status
        FROM experiments
        WHERE (scope = ? OR scope = 'global')
          AND status = 'completed'
        ORDER BY roi_pct DESC
        LIMIT ?
    """, (scope, limit)).fetchall()

    return [
        {
            "id": r[0], "hypothesis": r[1], "source": r[2],
            "roi_pct": r[3], "total_bets": r[4], "sharpe": r[5],
            "clv_avg": r[6], "significant": bool(r[7]),
            "promoted": bool(r[8]), "status": r[9],
        }
        for r in rows
    ]


# ═══════════════════════════════════════════════════════════════════
#  Bayesian Optimization Helper
# ═══════════════════════════════════════════════════════════════════

def generate_neighbor_strategies(base: StrategyConfig,
                                 n: int = 5,
                                 perturbation: float = 0.03) -> list[StrategyConfig]:
    """
    Generate neighboring strategies by perturbing base weights.

    Used by the autonomous agent for Bayesian-style exploration.
    Each neighbor has one or two weights adjusted by +/- perturbation.
    """
    import random
    neighbors = []
    weight_fields = [
        "w_sg_total", "w_sg_app", "w_sg_ott", "w_sg_arg",
        "w_sg_putt", "w_form", "w_course_fit",
    ]

    for _ in range(n):
        cfg = StrategyConfig(**{
            k: getattr(base, k) for k in vars(base)
            if not k.startswith("_")
        })

        # Perturb 1-2 weights
        fields_to_change = random.sample(weight_fields, min(2, len(weight_fields)))
        for f in fields_to_change:
            current = getattr(cfg, f)
            delta = random.uniform(-perturbation, perturbation)
            new_val = max(0.0, min(0.5, current + delta))
            setattr(cfg, f, round(new_val, 4))

        # Optionally perturb other parameters
        if random.random() < 0.3:
            cfg.min_ev = round(max(0.01, min(0.15, cfg.min_ev + random.uniform(-0.02, 0.02))), 3)
        if random.random() < 0.3:
            cfg.softmax_temp = round(max(0.5, min(3.0, cfg.softmax_temp + random.uniform(-0.3, 0.3))), 2)
        if random.random() < 0.2:
            cfg.stat_window = random.choice(WINDOWS)

        cfg.name = f"{base.name}_neighbor_{len(neighbors)}"
        neighbors.append(cfg)

    return neighbors


WINDOWS = [12, 24, 50]
