"""
Weight Management and Retuning

Stores, loads, and adjusts model weights based on past results.

The retuning logic:
  - After N tournaments with results, look at which picks HIT
  - For each hit, record what the player's course_fit, form, momentum scores were
  - Compare hit vs miss distributions for each factor
  - Nudge weights toward factors that correlated with hits
"""

import json
from src import db


def get_current_weights() -> dict:
    """Get the currently active weight set."""
    return db.get_active_weights()


def save_new_weights(name: str, weights: dict):
    """Save a new weight set and make it active."""
    db.save_weights(name, weights, active=True)


def analyze_pick_performance(min_tournaments: int = 3) -> dict:
    """
    Analyze historical pick performance to find which factors
    correlate with successful picks.

    Returns analysis like:
    {
        "total_picks": int,
        "total_hits": int,
        "hit_rate": float,
        "by_bet_type": {...},
        "factor_analysis": {
            "course_fit": {"avg_hit": float, "avg_miss": float, "edge": float},
            "form": {...},
            "momentum": {...},
        }
    }
    """
    conn = db.get_conn()

    # Get all picks with outcomes
    rows = conn.execute("""
        SELECT p.*, po.hit, po.actual_finish
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
    """).fetchall()
    conn.close()

    if not rows:
        return {"total_picks": 0, "message": "No results logged yet. Enter results after tournaments to enable retuning."}

    total = len(rows)
    hits = sum(1 for r in rows if r["hit"])

    # Analyze by bet type
    by_type = {}
    for r in rows:
        bt = r["bet_type"]
        if bt not in by_type:
            by_type[bt] = {"picks": 0, "hits": 0}
        by_type[bt]["picks"] += 1
        if r["hit"]:
            by_type[bt]["hits"] += 1
    for bt in by_type:
        by_type[bt]["hit_rate"] = by_type[bt]["hits"] / by_type[bt]["picks"] if by_type[bt]["picks"] else 0

    # Analyze each factor (course_fit, form, momentum)
    factor_analysis = {}
    for factor in ["course_fit_score", "form_score", "momentum_score", "composite_score"]:
        hit_vals = [r[factor] for r in rows if r["hit"] and r[factor] is not None]
        miss_vals = [r[factor] for r in rows if not r["hit"] and r[factor] is not None]

        avg_hit = sum(hit_vals) / len(hit_vals) if hit_vals else 0
        avg_miss = sum(miss_vals) / len(miss_vals) if miss_vals else 0

        factor_name = factor.replace("_score", "")
        factor_analysis[factor_name] = {
            "avg_hit": round(avg_hit, 2),
            "avg_miss": round(avg_miss, 2),
            "edge": round(avg_hit - avg_miss, 2),
            "hit_count": len(hit_vals),
            "miss_count": len(miss_vals),
        }

    return {
        "total_picks": total,
        "total_hits": hits,
        "hit_rate": round(hits / total, 3) if total else 0,
        "by_bet_type": by_type,
        "factor_analysis": factor_analysis,
    }


def suggest_weight_adjustment(current_weights: dict, analysis: dict) -> dict:
    """
    Based on factor analysis, suggest new weights.

    Logic:
    - If a factor's avg_hit >> avg_miss, it's predictive → increase weight
    - If a factor's avg_hit ≈ avg_miss, it's not helping → decrease weight
    - Nudge conservatively (max 5% change per retune cycle)
    """
    if analysis.get("total_picks", 0) < 10:
        return current_weights  # Not enough data

    fa = analysis.get("factor_analysis", {})
    new_weights = current_weights.copy()

    # Compute edge for each top-level factor
    top_factors = ["course_fit", "form", "momentum"]
    edges = {}
    for f in top_factors:
        if f in fa:
            edges[f] = fa[f].get("edge", 0)
        else:
            edges[f] = 0

    total_edge = sum(abs(e) for e in edges.values()) or 1.0

    # Compute ideal proportions based on edges
    for f in top_factors:
        ideal = abs(edges[f]) / total_edge
        current = current_weights.get(f, 0.33)
        # Nudge toward ideal, max 0.05 per cycle
        delta = (ideal - current) * 0.3  # 30% of the gap
        delta = max(-0.05, min(0.05, delta))
        new_weights[f] = round(max(0.05, min(0.60, current + delta)), 3)

    # Renormalize top-level weights to sum to 1.0
    total_w = sum(new_weights[f] for f in top_factors)
    for f in top_factors:
        new_weights[f] = round(new_weights[f] / total_w, 3)

    return new_weights


def retune(dry_run: bool = True) -> dict:
    """
    Full retune cycle:
    1. Analyze historical performance
    2. Suggest new weights
    3. Optionally save them

    Returns the analysis and suggested weights.
    """
    current = get_current_weights()
    analysis = analyze_pick_performance()
    suggested = suggest_weight_adjustment(current, analysis)

    result = {
        "analysis": analysis,
        "current_weights": current,
        "suggested_weights": suggested,
        "changes": {
            k: round(suggested.get(k, 0) - current.get(k, 0), 4)
            for k in ["course_fit", "form", "momentum"]
        },
    }

    if not dry_run and analysis.get("total_picks", 0) >= 10:
        save_new_weights("auto_retune", suggested)
        result["saved"] = True
    else:
        result["saved"] = False
        if analysis.get("total_picks", 0) < 10:
            result["message"] = f"Need at least 10 picks with results to retune. Currently have {analysis.get('total_picks', 0)}."

    return result
