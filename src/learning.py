"""
Self-Improving Learning System

Closes the feedback loop after each tournament:
  1. Auto-ingest results from DG round data
  2. Score all picks (hit/miss + profit/loss)
  3. Log predictions for calibration tracking
  4. Update global weights based on performance
  5. Update course-specific weight profiles
  6. Generate plain-English learning summary

This module ties together results.py, weights.py, and the new
calibration/course-learning tables.
"""

import json
import math
from datetime import datetime
from typing import Optional

from src import db
from src.player_normalizer import display_name


# ═══════════════════════════════════════════════════════════════════
#  Auto-Results & Pick Scoring
# ═══════════════════════════════════════════════════════════════════

def score_picks_for_tournament(tournament_id: int) -> dict:
    """
    Score all picks against results. Returns summary.

    This is the same logic as results.py but callable programmatically.
    """
    conn = db.get_conn()

    picks = conn.execute(
        "SELECT * FROM picks WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()

    results = conn.execute(
        "SELECT * FROM results WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()

    if not picks:
        conn.close()
        return {"status": "no_picks", "message": "No picks logged for this tournament."}
    if not results:
        conn.close()
        return {"status": "no_results", "message": "No results entered yet."}

    result_map = {r["player_key"]: dict(r) for r in results}

    scored = 0
    hits = 0
    total_profit = 0.0

    for pick in picks:
        pk = pick["player_key"]
        bt = pick["bet_type"]
        r = result_map.get(pk)
        if not r:
            continue

        finish = r.get("finish_position")
        made_cut = r.get("made_cut", 0)
        hit = 0

        if bt == "outright":
            hit = 1 if finish == 1 else 0
        elif bt == "top5":
            hit = 1 if finish is not None and finish <= 5 else 0
        elif bt == "top10":
            hit = 1 if finish is not None and finish <= 10 else 0
        elif bt == "top20":
            hit = 1 if finish is not None and finish <= 20 else 0
        elif bt == "make_cut":
            hit = 1 if made_cut else 0
        elif bt == "matchup":
            opp_key = pick["opponent_key"]
            opp_result = result_map.get(opp_key)
            if opp_result and finish is not None:
                opp_finish = opp_result.get("finish_position")
                if opp_finish is None:
                    hit = 1
                elif finish < opp_finish:
                    hit = 1

        # Calculate profit if we have odds
        odds_text = pick["market_odds"]
        odds_decimal = None
        profit = 0.0
        stake = 1.0  # Default 1 unit

        if odds_text:
            try:
                odds_int = int(str(odds_text).replace("+", ""))
                if odds_int > 0:
                    odds_decimal = (odds_int / 100.0) + 1.0
                else:
                    odds_decimal = (100.0 / abs(odds_int)) + 1.0
            except (ValueError, ZeroDivisionError):
                odds_decimal = None

        if odds_decimal and hit:
            profit = stake * (odds_decimal - 1.0)
        elif odds_decimal:
            profit = -stake

        total_profit += profit

        # Check if already scored
        existing = conn.execute(
            "SELECT id FROM pick_outcomes WHERE pick_id = ?", (pick["id"],)
        ).fetchone()

        if not existing:
            conn.execute(
                """INSERT INTO pick_outcomes
                   (pick_id, hit, actual_finish, odds_decimal, stake, profit)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pick["id"], hit, r.get("finish_text"),
                 odds_decimal, stake, profit),
            )
            scored += 1
            if hit:
                hits += 1

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "scored": scored,
        "hits": hits,
        "misses": scored - hits,
        "hit_rate": round(hits / scored, 3) if scored else 0,
        "total_profit": round(total_profit, 2),
    }


# ═══════════════════════════════════════════════════════════════════
#  Prediction Logging (for calibration)
# ═══════════════════════════════════════════════════════════════════

def log_predictions_for_tournament(tournament_id: int,
                                   value_bets_by_type: dict) -> int:
    """
    Log all predictions (model prob, DG prob, market prob, outcome)
    to the prediction_log table for calibration analysis.

    value_bets_by_type: {bet_type: [value_bet_dicts]}
    """
    # Get results for outcome
    conn = db.get_conn()
    results = conn.execute(
        "SELECT * FROM results WHERE tournament_id = ?", (tournament_id,)
    ).fetchall()
    conn.close()

    result_map = {r["player_key"]: dict(r) for r in results}

    predictions = []
    for bet_type, bets in value_bets_by_type.items():
        for bet in bets:
            pk = bet.get("player_key")
            r = result_map.get(pk)

            # Determine actual outcome
            actual = 0
            if r:
                finish = r.get("finish_position")
                made_cut = r.get("made_cut", 0)
                if bet_type == "outright" and finish == 1:
                    actual = 1
                elif bet_type == "top5" and finish is not None and finish <= 5:
                    actual = 1
                elif bet_type == "top10" and finish is not None and finish <= 10:
                    actual = 1
                elif bet_type == "top20" and finish is not None and finish <= 20:
                    actual = 1
                elif bet_type == "make_cut" and made_cut:
                    actual = 1

            # Compute odds_decimal from best_odds
            odds_decimal = None
            best_odds = bet.get("best_odds")
            if best_odds:
                try:
                    if best_odds > 0:
                        odds_decimal = (best_odds / 100.0) + 1.0
                    else:
                        odds_decimal = (100.0 / abs(best_odds)) + 1.0
                except (ValueError, ZeroDivisionError):
                    pass

            profit = None
            if odds_decimal and bet.get("is_value"):
                profit = (odds_decimal - 1.0) if actual else -1.0

            predictions.append({
                "tournament_id": tournament_id,
                "player_key": pk,
                "bet_type": bet_type,
                "model_prob": bet.get("model_prob"),
                "dg_prob": bet.get("dg_prob"),
                "market_implied_prob": bet.get("market_prob"),
                "actual_outcome": actual,
                "odds_decimal": odds_decimal,
                "profit": profit,
            })

    if predictions:
        db.log_predictions(predictions)

    return len(predictions)


# ═══════════════════════════════════════════════════════════════════
#  Calibration Analysis
# ═══════════════════════════════════════════════════════════════════

def compute_calibration() -> dict:
    """
    Analyze how well-calibrated our predictions are.

    Groups predictions into probability buckets and compares
    predicted probability to actual outcome rate.

    Also computes Brier score (lower = better).
    """
    data = db.get_calibration_data()
    if not data:
        return {"status": "no_data", "message": "No prediction data yet."}

    # Buckets for calibration curve
    buckets = [
        (0.00, 0.02, "0-2%"),
        (0.02, 0.05, "2-5%"),
        (0.05, 0.10, "5-10%"),
        (0.10, 0.20, "10-20%"),
        (0.20, 0.35, "20-35%"),
        (0.35, 0.50, "35-50%"),
        (0.50, 1.00, "50-100%"),
    ]

    calibration = []
    brier_sum = 0.0
    brier_count = 0

    for low, high, label in buckets:
        in_bucket = [
            d for d in data
            if d["model_prob"] is not None
            and low <= d["model_prob"] < high
        ]
        if not in_bucket:
            continue

        predicted_avg = sum(d["model_prob"] for d in in_bucket) / len(in_bucket)
        actual_rate = sum(d["actual_outcome"] for d in in_bucket) / len(in_bucket)

        calibration.append({
            "bucket": label,
            "count": len(in_bucket),
            "predicted_avg": round(predicted_avg, 4),
            "actual_rate": round(actual_rate, 4),
            "gap": round(actual_rate - predicted_avg, 4),
        })

    # Brier score
    for d in data:
        if d["model_prob"] is not None and d["actual_outcome"] is not None:
            brier_sum += (d["model_prob"] - d["actual_outcome"]) ** 2
            brier_count += 1

    brier = round(brier_sum / brier_count, 6) if brier_count else None

    # Compare model vs DG vs market
    model_brier = 0.0
    dg_brier = 0.0
    market_brier = 0.0
    comparison_count = 0

    for d in data:
        if (d["model_prob"] is not None and d["dg_prob"] is not None
                and d["market_implied_prob"] is not None
                and d["actual_outcome"] is not None):
            model_brier += (d["model_prob"] - d["actual_outcome"]) ** 2
            dg_brier += (d["dg_prob"] - d["actual_outcome"]) ** 2
            market_brier += (d["market_implied_prob"] - d["actual_outcome"]) ** 2
            comparison_count += 1

    model_comparison = None
    if comparison_count >= 20:
        model_comparison = {
            "count": comparison_count,
            "model_brier": round(model_brier / comparison_count, 6),
            "dg_brier": round(dg_brier / comparison_count, 6),
            "market_brier": round(market_brier / comparison_count, 6),
        }

    # ROI tracking
    value_bets = [d for d in data if d["profit"] is not None]
    total_profit = sum(d["profit"] for d in value_bets)
    total_staked = len(value_bets)  # 1 unit each
    roi = round(total_profit / total_staked * 100, 2) if total_staked else 0

    return {
        "total_predictions": len(data),
        "calibration": calibration,
        "brier_score": brier,
        "model_comparison": model_comparison,
        "roi": {
            "total_bets": total_staked,
            "total_profit": round(total_profit, 2),
            "roi_pct": roi,
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  Course-Specific Weight Learning
# ═══════════════════════════════════════════════════════════════════

def update_course_weights(tournament_id: int, course_num: int,
                          course_name: str) -> dict | None:
    """
    After a tournament, analyze which factors predicted well at THIS course
    and update the course-specific weight profile.

    Requires at least some scored picks for this tournament.
    """
    conn = db.get_conn()
    picks = conn.execute(
        """SELECT p.*, po.hit
           FROM picks p
           JOIN pick_outcomes po ON po.pick_id = p.id
           WHERE p.tournament_id = ?""",
        (tournament_id,),
    ).fetchall()
    conn.close()

    if len(picks) < 5:
        return None

    # Analyze which factors separated hits from misses
    factors = ["course_fit_score", "form_score", "momentum_score"]
    edges = {}
    for factor in factors:
        hit_vals = [p[factor] for p in picks if p["hit"] and p[factor] is not None]
        miss_vals = [p[factor] for p in picks if not p["hit"] and p[factor] is not None]

        avg_hit = sum(hit_vals) / len(hit_vals) if hit_vals else 50
        avg_miss = sum(miss_vals) / len(miss_vals) if miss_vals else 50
        edges[factor.replace("_score", "")] = avg_hit - avg_miss

    # Convert edges to weight suggestions
    total_edge = sum(abs(e) for e in edges.values()) or 1.0
    suggested = {}
    for factor, edge in edges.items():
        # Weight proportional to predictive power, but conservative
        suggested[factor] = max(0.10, abs(edge) / total_edge)

    # Normalize
    total = sum(suggested.values())
    for k in suggested:
        suggested[k] = round(suggested[k] / total, 3)

    # Load existing profile and blend
    existing = db.get_course_weight_profile(course_num)
    tournaments_used = 1
    if existing:
        tournaments_used = existing.get("tournaments_used", 0) + 1
        old_w = existing["weights"]
        # Blend: new evidence gets 1/N weight where N = tournaments
        blend_factor = 1.0 / tournaments_used
        for k in suggested:
            if k in old_w:
                suggested[k] = round(
                    old_w[k] * (1 - blend_factor) + suggested[k] * blend_factor, 3
                )

    confidence = min(1.0, 0.3 + 0.1 * tournaments_used)

    db.save_course_weight_profile(
        course_num, course_name, suggested, tournaments_used, confidence
    )

    return {
        "course": course_name,
        "course_num": course_num,
        "tournaments_used": tournaments_used,
        "confidence": round(confidence, 2),
        "weights": suggested,
        "edges": {k: round(v, 2) for k, v in edges.items()},
    }


# ═══════════════════════════════════════════════════════════════════
#  Post-Tournament Learning Orchestrator
# ═══════════════════════════════════════════════════════════════════

def post_tournament_learn(tournament_id: int,
                          event_id: str = None,
                          year: int = None,
                          course_num: int = None,
                          course_name: str = None,
                          value_bets_by_type: dict = None) -> dict:
    """
    Full post-tournament learning cycle.

    1. Auto-ingest results (if event_id/year provided and rounds exist)
    2. Score all picks
    3. Log predictions for calibration
    4. Update course-specific weights
    5. Run global weight retune
    6. Return summary

    This is the main entry point called after a tournament completes.
    """
    summary = {
        "tournament_id": tournament_id,
        "timestamp": datetime.now().isoformat(),
        "steps": {},
    }

    # 1. Auto-ingest results from DG data
    if event_id and year:
        from src.datagolf import auto_ingest_results
        result = auto_ingest_results(tournament_id, event_id, year)
        summary["steps"]["auto_results"] = result

    # 2. Score picks
    score_result = score_picks_for_tournament(tournament_id)
    summary["steps"]["scoring"] = score_result

    # 3. Log predictions for calibration
    if value_bets_by_type:
        n = log_predictions_for_tournament(tournament_id, value_bets_by_type)
        summary["steps"]["predictions_logged"] = n

    # 4. Update course-specific weights
    if course_num and course_name:
        course_result = update_course_weights(tournament_id, course_num, course_name)
        summary["steps"]["course_weights"] = course_result

    # 5. Global weight retune
    from src.models.weights import retune
    retune_result = retune(dry_run=False)
    summary["steps"]["global_retune"] = {
        "saved": retune_result.get("saved", False),
        "insights": retune_result.get("insights", []),
        "changes": retune_result.get("changes", {}),
    }

    # 6. Compute calibration summary
    cal = compute_calibration()
    summary["calibration"] = {
        "brier_score": cal.get("brier_score"),
        "roi": cal.get("roi"),
    }

    return summary
