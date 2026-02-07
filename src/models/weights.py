"""
Weight Management and Deep Retuning

The improvement loop now analyzes:
  1. Top-level factors (course_fit vs form vs momentum)
  2. Per bet type (do different factors matter for outrights vs top 20?)
  3. Sub-factor analysis (which SG categories predict best?)
  4. Data source tracking (which CSV types correlate with better picks?)
  5. Score threshold analysis (is there a composite cutoff that reliably hits?)
"""

import json
from src import db


def get_current_weights() -> dict:
    """Get the currently active weight set."""
    return db.get_active_weights()


def save_new_weights(name: str, weights: dict):
    """Save a new weight set and make it active."""
    db.save_weights(name, weights, active=True)


def _get_scored_picks() -> list[dict]:
    """Get all picks that have outcomes."""
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT p.*, po.hit, po.actual_finish
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_data_sources_for_tournament(tournament_id: int) -> list[dict]:
    """Get what data files were available for a tournament."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT file_type, data_mode, round_window, row_count FROM csv_imports WHERE tournament_id = ?",
        (tournament_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def analyze_pick_performance(min_tournaments: int = 1) -> dict:
    """
    Deep analysis of historical pick performance.

    Returns:
    {
        "total_picks": int,
        "total_hits": int,
        "hit_rate": float,
        "by_bet_type": {bet_type: {picks, hits, hit_rate}},
        "factor_analysis": {
            factor: {avg_hit, avg_miss, edge, predictive_power}
        },
        "by_bet_type_factor": {
            bet_type: {factor: {avg_hit, avg_miss, edge}}
        },
        "score_thresholds": {
            "top_10_pct": {composite_cutoff, hit_rate},
            "top_25_pct": {...},
        },
        "insights": [str],  # Plain English insights
    }
    """
    rows = _get_scored_picks()

    if not rows:
        return {
            "total_picks": 0,
            "message": "No results logged yet. Enter results after tournaments to enable improvement.",
        }

    total = len(rows)
    hits = sum(1 for r in rows if r["hit"])

    # ── 1. By bet type ──
    by_type = {}
    for r in rows:
        bt = r["bet_type"]
        if bt not in by_type:
            by_type[bt] = {"picks": 0, "hits": 0}
        by_type[bt]["picks"] += 1
        if r["hit"]:
            by_type[bt]["hits"] += 1
    for bt in by_type:
        p = by_type[bt]["picks"]
        by_type[bt]["hit_rate"] = round(by_type[bt]["hits"] / p, 3) if p else 0

    # ── 2. Factor analysis (top-level) ──
    factors = ["course_fit_score", "form_score", "momentum_score", "composite_score"]
    factor_analysis = {}
    for factor in factors:
        hit_vals = [r[factor] for r in rows if r["hit"] and r[factor] is not None]
        miss_vals = [r[factor] for r in rows if not r["hit"] and r[factor] is not None]

        avg_hit = sum(hit_vals) / len(hit_vals) if hit_vals else 0
        avg_miss = sum(miss_vals) / len(miss_vals) if miss_vals else 0
        edge = avg_hit - avg_miss

        # Predictive power: how much separation between hits and misses
        # Normalized by the range of values
        all_vals = hit_vals + miss_vals
        val_range = (max(all_vals) - min(all_vals)) if all_vals and len(all_vals) > 1 else 1.0
        predictive_power = abs(edge) / val_range if val_range > 0 else 0

        fname = factor.replace("_score", "")
        factor_analysis[fname] = {
            "avg_hit": round(avg_hit, 2),
            "avg_miss": round(avg_miss, 2),
            "edge": round(edge, 2),
            "predictive_power": round(predictive_power, 3),
            "hit_count": len(hit_vals),
            "miss_count": len(miss_vals),
        }

    # ── 3. Per bet type + factor (which factors matter for which bet types?) ──
    by_type_factor = {}
    for bt in by_type:
        bt_rows = [r for r in rows if r["bet_type"] == bt]
        by_type_factor[bt] = {}
        for factor in factors:
            hit_vals = [r[factor] for r in bt_rows if r["hit"] and r[factor] is not None]
            miss_vals = [r[factor] for r in bt_rows if not r["hit"] and r[factor] is not None]
            avg_hit = sum(hit_vals) / len(hit_vals) if hit_vals else 0
            avg_miss = sum(miss_vals) / len(miss_vals) if miss_vals else 0
            fname = factor.replace("_score", "")
            by_type_factor[bt][fname] = {
                "avg_hit": round(avg_hit, 2),
                "avg_miss": round(avg_miss, 2),
                "edge": round(avg_hit - avg_miss, 2),
            }

    # ── 4. Score threshold analysis ──
    thresholds = {}
    composites = sorted([r["composite_score"] for r in rows if r["composite_score"] is not None], reverse=True)
    if composites:
        for label, pct in [("top_10_pct", 0.10), ("top_25_pct", 0.25), ("top_50_pct", 0.50)]:
            idx = max(0, int(len(composites) * pct) - 1)
            cutoff = composites[idx]
            above = [r for r in rows if r["composite_score"] is not None and r["composite_score"] >= cutoff]
            above_hits = sum(1 for r in above if r["hit"])
            thresholds[label] = {
                "composite_cutoff": round(cutoff, 1),
                "picks_above": len(above),
                "hits_above": above_hits,
                "hit_rate": round(above_hits / len(above), 3) if above else 0,
            }

    # ── 5. Data source analysis ──
    # Track which tournaments had which data types, and correlate with hit rates
    data_source_analysis = {}
    conn = db.get_conn()
    tournament_ids = set(r["tournament_id"] for r in rows)
    for tid in tournament_ids:
        sources = _get_data_sources_for_tournament(tid)
        tid_rows = [r for r in rows if r["tournament_id"] == tid]
        tid_hits = sum(1 for r in tid_rows if r["hit"])
        tid_rate = tid_hits / len(tid_rows) if tid_rows else 0

        had_course = any(s["data_mode"] == "course_specific" for s in sources)
        had_sim = any(s["file_type"] == "sim" for s in sources)
        n_files = len(sources)
        categories = set(s["file_type"] for s in sources if s["file_type"])
        windows = set(s["round_window"] for s in sources if s["round_window"])

        data_source_analysis[tid] = {
            "hit_rate": round(tid_rate, 3),
            "picks": len(tid_rows),
            "had_course_data": had_course,
            "had_sim": had_sim,
            "file_count": n_files,
            "categories": list(categories),
            "windows": list(windows),
        }
    conn.close()

    # Aggregate: do tournaments with course data perform better?
    course_data_rates = [d["hit_rate"] for d in data_source_analysis.values() if d["had_course_data"]]
    no_course_rates = [d["hit_rate"] for d in data_source_analysis.values() if not d["had_course_data"]]
    more_files_rates = [d["hit_rate"] for d in data_source_analysis.values() if d["file_count"] >= 5]
    fewer_files_rates = [d["hit_rate"] for d in data_source_analysis.values() if d["file_count"] < 5]

    data_insights = {
        "with_course_data": {
            "tournaments": len(course_data_rates),
            "avg_hit_rate": round(sum(course_data_rates) / len(course_data_rates), 3) if course_data_rates else 0,
        },
        "without_course_data": {
            "tournaments": len(no_course_rates),
            "avg_hit_rate": round(sum(no_course_rates) / len(no_course_rates), 3) if no_course_rates else 0,
        },
        "5plus_files": {
            "tournaments": len(more_files_rates),
            "avg_hit_rate": round(sum(more_files_rates) / len(more_files_rates), 3) if more_files_rates else 0,
        },
        "under_5_files": {
            "tournaments": len(fewer_files_rates),
            "avg_hit_rate": round(sum(fewer_files_rates) / len(fewer_files_rates), 3) if fewer_files_rates else 0,
        },
    }

    # ── 6. Generate plain English insights ──
    insights = []

    if total >= 10:
        # Best and worst bet type
        best_bt = max(by_type.items(), key=lambda x: x[1]["hit_rate"])
        worst_bt = min(by_type.items(), key=lambda x: x[1]["hit_rate"])
        insights.append(f"Best bet type: {best_bt[0]} ({best_bt[1]['hit_rate']:.0%} hit rate)")
        insights.append(f"Worst bet type: {worst_bt[0]} ({worst_bt[1]['hit_rate']:.0%} hit rate)")

        # Most predictive factor
        best_factor = max(factor_analysis.items(), key=lambda x: x[1]["predictive_power"])
        insights.append(f"Most predictive factor: {best_factor[0]} (edge: +{best_factor[1]['edge']:.1f})")

        # Least predictive
        worst_factor = min(factor_analysis.items(), key=lambda x: x[1]["predictive_power"])
        if worst_factor[1]["predictive_power"] < 0.05:
            insights.append(f"Least predictive factor: {worst_factor[0]} — consider reducing its weight")

        # Threshold insight
        if thresholds.get("top_25_pct"):
            t = thresholds["top_25_pct"]
            insights.append(
                f"Top 25% composite picks (>{t['composite_cutoff']:.0f}) hit at {t['hit_rate']:.0%} "
                f"vs {hits/total:.0%} overall"
            )

        # Data completeness insight
        if course_data_rates and no_course_rates:
            c_avg = sum(course_data_rates) / len(course_data_rates)
            n_avg = sum(no_course_rates) / len(no_course_rates)
            if c_avg > n_avg + 0.03:
                insights.append("Course-specific data is helping: picks hit more when you upload course history")
            elif n_avg > c_avg + 0.03:
                insights.append("Surprisingly, picks without course data hit more — form/momentum may be enough")

        # Per-type factor insight
        for bt, factors_data in by_type_factor.items():
            edges = {f: d["edge"] for f, d in factors_data.items()}
            if edges:
                best = max(edges, key=edges.get)
                if edges[best] > 3:
                    insights.append(f"For {bt}: {best} is the strongest predictor (edge +{edges[best]:.1f})")

    return {
        "total_picks": total,
        "total_hits": hits,
        "hit_rate": round(hits / total, 3) if total else 0,
        "by_bet_type": by_type,
        "factor_analysis": factor_analysis,
        "by_bet_type_factor": by_type_factor,
        "score_thresholds": thresholds,
        "data_insights": data_insights,
        "insights": insights,
    }


def suggest_weight_adjustment(current_weights: dict, analysis: dict) -> dict:
    """
    Suggest new weights based on deep analysis.

    Now adjusts:
    - Top-level (course_fit, form, momentum) based on predictive power
    - SG sub-weights (form_sg_tot, form_sg_app, etc.) based on per-type analysis
    - Nudges conservatively (max 5% per cycle)
    """
    if analysis.get("total_picks", 0) < 10:
        return current_weights

    fa = analysis.get("factor_analysis", {})
    new_weights = current_weights.copy()

    # ── Top-level weight adjustment ──
    top_factors = ["course_fit", "form", "momentum"]
    predictive_powers = {}
    for f in top_factors:
        if f in fa:
            predictive_powers[f] = fa[f].get("predictive_power", 0)
        else:
            predictive_powers[f] = 0

    total_pp = sum(predictive_powers.values()) or 1.0

    for f in top_factors:
        ideal = predictive_powers[f] / total_pp
        # Ensure minimum weight of 0.10
        ideal = max(0.10, ideal)
        current = current_weights.get(f, 0.33)
        delta = (ideal - current) * 0.25  # 25% of the gap per cycle
        delta = max(-0.05, min(0.05, delta))
        new_weights[f] = round(max(0.10, min(0.55, current + delta)), 3)

    # Renormalize to sum to 1.0
    total_w = sum(new_weights[f] for f in top_factors)
    for f in top_factors:
        new_weights[f] = round(new_weights[f] / total_w, 3)

    # ── SG sub-weight adjustment (if enough data) ──
    # This is future-ready: once we track per-SG-category hit rates,
    # we can adjust form_sg_tot, form_sg_app, etc.
    # For now, nudge based on overall factor edges by bet type
    btf = analysis.get("by_bet_type_factor", {})
    if btf:
        # Average edges across bet types for each factor
        form_edge = 0
        course_edge = 0
        mom_edge = 0
        count = 0
        for bt, factors_data in btf.items():
            if "form" in factors_data:
                form_edge += factors_data["form"]["edge"]
            if "course_fit" in factors_data:
                course_edge += factors_data["course_fit"]["edge"]
            if "momentum" in factors_data:
                mom_edge += factors_data["momentum"]["edge"]
            count += 1
        # This data will be used more as it accumulates

    return new_weights


def retune(dry_run: bool = True) -> dict:
    """
    Full retune cycle:
    1. Deep analysis of historical performance
    2. Generate insights
    3. Suggest new weights
    4. Optionally save them

    Returns everything needed for the dashboard.
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
        "insights": analysis.get("insights", []),
    }

    if not dry_run and analysis.get("total_picks", 0) >= 10:
        save_new_weights("auto_retune", suggested)
        result["saved"] = True
    else:
        result["saved"] = False
        if analysis.get("total_picks", 0) < 10:
            result["message"] = (
                f"Need at least 10 scored picks to retune. "
                f"Currently have {analysis.get('total_picks', 0)}. "
                f"Enter results after tournaments to build history."
            )

    return result
