"""
Outlier Investigator

Automatically investigates major prediction misses by combining:
  - Weather conditions during the tournament
  - Equipment changes near the event date
  - Intel/news events affecting the player
  - Historical patterns at that course

Uses AI to synthesize findings and suggest model improvements.
Stores investigations in outlier_investigations table for the
autonomous research agent to learn from.
"""

import json
import logging
from datetime import datetime

from src import db
from src.player_normalizer import normalize_name

logger = logging.getLogger("outlier_investigator")


def find_outliers(event_id: str, year: int,
                  threshold: int = 30) -> list[dict]:
    """
    Find players whose actual finish deviated significantly from prediction.

    threshold: minimum rank delta to flag as outlier (e.g., predicted top10
               but finished 50th = delta of 40).

    Returns list of outlier dicts with prediction/result info.
    """
    conn = db.get_conn()

    # Get predictions for this event
    preds = conn.execute("""
        SELECT player_dg_id, player_name, win_prob, top5_prob,
               top10_prob, top20_prob, make_cut_prob
        FROM historical_predictions
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()

    if not preds:
        return []

    # Get round data for actual finishes
    finishes = conn.execute("""
        SELECT DISTINCT player_key, fin_text
        FROM rounds
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()

    finish_by_key = {}
    for f in finishes:
        pkey, fin_text = f
        if not fin_text:
            continue
        fin_upper = fin_text.strip().upper()
        pos = None
        if fin_upper in ("CUT", "MC"):
            pos = 999
        elif fin_upper in ("WD", "W/D", "DQ"):
            pos = 998
        else:
            try:
                pos = int(fin_upper.replace("T", ""))
            except ValueError:
                pass
        if pos is not None:
            finish_by_key[pkey] = {"position": pos, "text": fin_text}

    # Rank predictions by win probability (best expected rank)
    pred_sorted = sorted(preds, key=lambda p: -(p[2] or 0))
    outliers = []

    for rank, pred in enumerate(pred_sorted, 1):
        dg_id, name, win_p, t5_p, t10_p, t20_p, mc_p = pred
        pkey = normalize_name(name)
        actual = finish_by_key.get(pkey)
        if not actual:
            continue

        actual_pos = actual["position"]

        # Expected rank = predicted rank based on win probability ordering
        predicted_rank = rank
        delta = abs(actual_pos - predicted_rank)

        if delta >= threshold:
            outliers.append({
                "event_id": event_id,
                "year": year,
                "player_key": pkey,
                "player_name": name,
                "dg_id": dg_id,
                "predicted_rank": predicted_rank,
                "actual_finish": actual_pos,
                "finish_text": actual["text"],
                "delta": delta,
                "direction": "underperformed" if actual_pos > predicted_rank else "overperformed",
                "win_prob": win_p,
                "top10_prob": t10_p,
                "make_cut_prob": mc_p,
            })

    outliers.sort(key=lambda x: -x["delta"])
    return outliers


def gather_context(outlier: dict) -> dict:
    """
    Gather all available contextual data for an outlier.

    Pulls weather, equipment changes, intel events, and course history.
    """
    conn = db.get_conn()
    context = {}

    event_id = outlier["event_id"]
    year = outlier["year"]
    player_key = outlier["player_key"]

    # Weather conditions during tournament
    weather = conn.execute("""
        SELECT round_num, avg_wind_kmh, max_gust_kmh,
               total_precip_mm, conditions_rating
        FROM tournament_weather_summary
        WHERE event_id = ? AND year = ?
        ORDER BY round_num
    """, (str(event_id), year)).fetchall()

    if weather:
        context["weather"] = [
            {
                "round": w[0], "avg_wind_kmh": w[1],
                "max_gust_kmh": w[2], "precip_mm": w[3],
                "conditions_rating": w[4],
            }
            for w in weather
        ]
        avg_rating = sum(w[4] for w in weather if w[4]) / len(weather) if weather else 0
        context["weather_severity"] = "calm" if avg_rating < 15 else "moderate" if avg_rating < 35 else "severe"

    # Equipment changes near event date
    equip = conn.execute("""
        SELECT change_date, category, old_equipment, new_equipment,
               ai_impact_assessment, performance_delta_sg
        FROM equipment_changes
        WHERE player_key = ?
        ORDER BY change_date DESC
        LIMIT 5
    """, (player_key,)).fetchall()

    if equip:
        context["equipment_changes"] = [
            {
                "date": e[0], "category": e[1],
                "old": e[2], "new": e[3],
                "impact": e[4], "sg_delta": e[5],
            }
            for e in equip
        ]

    # Intel events around tournament time
    intel = conn.execute("""
        SELECT title, snippet, source, category,
               ai_summary, relevance_score
        FROM intel_events
        WHERE player_key = ?
        ORDER BY relevance_score DESC
        LIMIT 5
    """, (player_key,)).fetchall()

    if intel:
        context["intel"] = [
            {
                "title": i[0], "snippet": i[1],
                "source": i[2], "category": i[3],
                "summary": i[4], "relevance": i[5],
            }
            for i in intel
        ]

    # Player's historical SG stats at this course (from rounds data)
    course_history = conn.execute("""
        SELECT round_num, score, sg_total, sg_ott, sg_app,
               sg_arg, sg_putt
        FROM rounds
        WHERE event_id = ? AND year = ? AND player_key = ?
        ORDER BY round_num
    """, (str(event_id), year, player_key)).fetchall()

    if course_history:
        context["round_scores"] = [
            {
                "round": r[0], "score": r[1],
                "sg_total": r[2], "sg_ott": r[3],
                "sg_app": r[4], "sg_arg": r[5],
                "sg_putt": r[6],
            }
            for r in course_history
        ]

    return context


def investigate_with_ai(outlier: dict, context: dict) -> dict:
    """
    Use AI to analyze an outlier and suggest model improvements.

    Returns dict with ai_explanation, root_cause, actionable, suggested_change.
    """
    try:
        from src.ai_brain import call_ai
    except ImportError:
        logger.warning("AI brain not available for outlier investigation")
        return {
            "ai_explanation": "AI analysis unavailable",
            "root_cause": "unknown",
            "actionable": False,
            "suggested_model_change": None,
        }

    direction = outlier["direction"]
    prompt = f"""You are a professional golf analytics expert investigating a major prediction miss.

PLAYER: {outlier.get('player_name', outlier['player_key'])}
EVENT: {outlier['event_id']} ({outlier['year']})
PREDICTED RANK: {outlier['predicted_rank']} (Win prob: {outlier.get('win_prob', 'N/A')}%, Top10: {outlier.get('top10_prob', 'N/A')}%)
ACTUAL FINISH: {outlier.get('finish_text', outlier['actual_finish'])}
DIRECTION: {direction} by {outlier['delta']} positions

AVAILABLE CONTEXT:
{json.dumps(context, indent=2, default=str)}

Analyze this prediction miss and respond in valid JSON:
{{
  "explanation": "2-3 sentence explanation of what likely happened",
  "root_cause": one of ["weather_impact", "equipment_change", "injury_fitness",
                        "course_mismatch", "hot_streak", "cold_streak",
                        "field_strength", "mental_factor", "unknown"],
  "actionable": true/false (can the model be improved to avoid this?),
  "suggested_change": "specific model change if actionable, else null",
  "confidence": 0.0 to 1.0
}}"""

    try:
        response = call_ai(prompt, max_tokens=500)
        if isinstance(response, str):
            # Try to parse JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(response[start:end])
                return {
                    "ai_explanation": parsed.get("explanation", ""),
                    "root_cause": parsed.get("root_cause", "unknown"),
                    "actionable": parsed.get("actionable", False),
                    "suggested_model_change": parsed.get("suggested_change"),
                }
    except Exception as e:
        logger.warning("AI outlier analysis failed: %s", e)

    return {
        "ai_explanation": "Analysis failed",
        "root_cause": "unknown",
        "actionable": False,
        "suggested_model_change": None,
    }


def store_investigation(outlier: dict, context: dict, analysis: dict):
    """Store a completed outlier investigation in the database."""
    conn = db.get_conn()

    weather_str = json.dumps(context.get("weather", []), default=str)
    has_equip = 1 if context.get("equipment_changes") else 0
    intel_str = json.dumps(context.get("intel", []), default=str)

    try:
        conn.execute("""
            INSERT OR REPLACE INTO outlier_investigations
            (event_id, year, player_key, predicted_rank, actual_finish,
             delta, weather_conditions, equipment_change_nearby,
             intel_context, ai_explanation, root_cause, actionable,
             suggested_model_change)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(outlier["event_id"]), outlier["year"],
            outlier["player_key"],
            outlier["predicted_rank"], outlier["actual_finish"],
            outlier["delta"],
            weather_str, has_equip, intel_str,
            analysis.get("ai_explanation", ""),
            analysis.get("root_cause", "unknown"),
            1 if analysis.get("actionable") else 0,
            analysis.get("suggested_model_change"),
        ))
        conn.commit()
    except Exception as e:
        logger.error("Failed to store investigation: %s", e)


def investigate_event(event_id: str, year: int,
                      threshold: int = 30,
                      use_ai: bool = True,
                      max_outliers: int = 10) -> list[dict]:
    """
    Full investigation pipeline for one event.

    1. Find outliers
    2. Gather context for each
    3. Optionally run AI analysis
    4. Store results

    Returns list of investigation results.
    """
    outliers = find_outliers(event_id, year, threshold=threshold)
    if not outliers:
        logger.info("No outliers found for %s/%s (threshold=%d)", event_id, year, threshold)
        return []

    outliers = outliers[:max_outliers]
    logger.info("Found %d outliers for %s/%s", len(outliers), event_id, year)

    results = []
    for outlier in outliers:
        context = gather_context(outlier)

        if use_ai:
            analysis = investigate_with_ai(outlier, context)
        else:
            analysis = {
                "ai_explanation": "AI analysis disabled",
                "root_cause": "unknown",
                "actionable": False,
                "suggested_model_change": None,
            }

        store_investigation(outlier, context, analysis)
        results.append({
            **outlier,
            "context_summary": {
                "has_weather": bool(context.get("weather")),
                "has_equipment": bool(context.get("equipment_changes")),
                "has_intel": bool(context.get("intel")),
            },
            "analysis": analysis,
        })

    return results
