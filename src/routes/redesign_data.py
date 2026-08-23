"""Read-only data projections for the frontend terminal overhaul.

Every endpoint is a pure SELECT over existing tables. Nothing here writes,
mutates, or feeds the prediction pipeline. All queries are defensive: if an
expected table/column is missing (e.g. mid-migration), the endpoint returns
an empty payload rather than erroring.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Query

from src import db

router = APIRouter(tags=["redesign"])


def _safe_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run a read-only query; return [] on any schema/availability problem."""
    try:
        conn = db.get_conn()
    except Exception:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.Error, sqlite3.Warning):
        return []
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# 1. Player betting record — picks ⋈ pick_outcomes by player
# ─────────────────────────────────────────────────────────────
@router.get("/api/redesign/player/{player_key}/betting-record")
async def player_betting_record(player_key: str) -> dict:
    """What has the model said about this player, and was it right?"""
    graded = _safe_query(
        """SELECT po.hit, po.profit, po.stake, po.odds_decimal,
                  p.ev, p.bet_type, p.market_type, p.tournament_id,
                  p.player_display, p.opponent_display, p.market_odds, p.market_book,
                  p.created_at
           FROM pick_outcomes po
           JOIN picks p ON p.id = po.pick_id
           WHERE p.player_key = ? OR p.opponent_key = ?
           ORDER BY p.created_at DESC""",
        (player_key, player_key),
    )
    all_picks = _safe_query(
        """SELECT COUNT(*) AS n FROM picks WHERE player_key = ? OR opponent_key = ?""",
        (player_key, player_key),
    )
    total_picks = int(all_picks[0]["n"]) if all_picks else 0

    graded_n = len(graded)
    hits = sum(1 for row in graded if row["hit"])
    profit = sum(float(row["profit"] or 0) for row in graded)
    stake = sum(float(row["stake"] or 0) for row in graded)
    evs = [float(row["ev"]) for row in graded if row["ev"] is not None]

    by_market: dict[str, dict[str, Any]] = {}
    for row in graded:
        key = f"{row['bet_type'] or 'matchup'}"
        bucket = by_market.setdefault(key, {"n": 0, "hits": 0, "profit": 0.0})
        bucket["n"] += 1
        bucket["hits"] += 1 if row["hit"] else 0
        bucket["profit"] += float(row["profit"] or 0)

    display = next(
        (r["player_display"] for r in graded if r["player_display"]), None
    )
    return {
        "player_key": player_key,
        "player_display": display,
        "total_picks": total_picks,
        "graded_picks": graded_n,
        "hits": hits,
        "hit_rate": round(hits / graded_n, 4) if graded_n else None,
        "units_profit": round(profit, 2),
        "units_staked": round(stake, 2),
        "roi": round(profit / stake, 4) if stake else None,
        "avg_ev": round(sum(evs) / len(evs), 4) if evs else None,
        "by_market": {
            k: {**v, "hit_rate": round(v["hits"] / v["n"], 4) if v["n"] else None}
            for k, v in by_market.items()
        },
        "recent": graded[:20],
    }


# ─────────────────────────────────────────────────────────────
# 2. Player market history — model-flagged frequency over time
# ─────────────────────────────────────────────────────────────
@router.get("/api/redesign/player/{player_key}/market-history")
async def player_market_history(
    player_key: str,
    days: int = Query(default=120, ge=7, le=365),
) -> dict:
    """How often has the model flagged this player +EV, and at what prices?"""
    daily = _safe_query(
        """SELECT substr(generated_at, 1, 10) AS day,
                  COUNT(*) AS rows_n,
                  SUM(CASE WHEN is_value THEN 1 ELSE 0 END) AS value_rows,
                  MAX(ev) AS best_ev,
                  MIN(odds) AS best_odds
           FROM market_prediction_rows
           WHERE player_key = ?
             AND generated_at >= datetime('now', ?)
           GROUP BY substr(generated_at, 1, 10)
           ORDER BY day ASC""",
        (player_key, f"-{int(days)} days"),
    )
    totals = _safe_query(
        """SELECT COUNT(*) AS rows_n,
                  SUM(CASE WHEN is_value THEN 1 ELSE 0 END) AS value_rows,
                  MAX(ev) AS best_ev
           FROM market_prediction_rows WHERE player_key = ?""",
        (player_key,),
    )
    t = totals[0] if totals else {"rows_n": 0, "value_rows": 0, "best_ev": None}
    return {
        "player_key": player_key,
        "window_days": days,
        "daily": daily,
        "totals": {
            "rows_seen": int(t["rows_n"] or 0),
            "value_flags": int(t["value_rows"] or 0),
            "best_ev": t["best_ev"],
        },
    }


# ─────────────────────────────────────────────────────────────
# 3. Course DNA — why the fit score is what it is
# ─────────────────────────────────────────────────────────────
@router.get("/api/redesign/player/{player_key}/course-dna")
async def player_course_dna(player_key: str, course_id: str | None = None) -> dict:
    """Course importance weights vs the player's SG strengths."""
    if course_id:
        course_row = _safe_query(
            """SELECT course_name, grass_type_fairway, grass_type_greens,
                      green_speed, fairway_width, yardage, par,
                      sg_ott_importance, sg_app_importance,
                      sg_arg_importance, sg_putt_importance,
                      historical_scoring_avg
               FROM course_encyclopedia WHERE course_id = ? LIMIT 1""",
            (course_id,),
        )
    else:
        # Latest course this player has round data for.
        latest = _safe_query(
            """SELECT DISTINCT course_name FROM rounds
               WHERE player_key = ? AND course_name IS NOT NULL
               ORDER BY event_completed DESC LIMIT 1""",
            (player_key,),
        )
        name = latest[0]["course_name"] if latest else None
        course_row = (
            _safe_query(
                """SELECT course_name, grass_type_fairway, grass_type_greens,
                          green_speed, fairway_width, yardage, par,
                          sg_ott_importance, sg_app_importance,
                          sg_arg_importance, sg_putt_importance,
                          historical_scoring_avg
                   FROM course_encyclopedia WHERE lower(course_name) = lower(?) LIMIT 1""",
                (name,),
            )
            if name
            else []
        )

    sg_windows = _safe_query(
        """SELECT metric_name, metric_value, round_window
           FROM metrics
           WHERE player_key = ?
             AND metric_category = 'strokes_gained'
             AND metric_name IN ('sg_ott','sg_app','sg_arg','sg_putt')
           ORDER BY id DESC LIMIT 16""",
        (player_key,),
    )

    return {
        "player_key": player_key,
        "course_id": course_id,
        "course": course_row[0] if course_row else None,
        "player_sg_windows": sg_windows[:8],
        "has_course_profile": bool(course_row),
    }


# ─────────────────────────────────────────────────────────────
# 4. Hole heatmap — dormant tables, honest empty states
# ─────────────────────────────────────────────────────────────
@router.get("/api/redesign/player/{player_key}/hole-heat")
async def player_hole_heat(player_key: str, course_id: str | None = None) -> dict:
    """Birdie%/bogey% per hole. Returns holes=[] when no hole data ingested."""
    holes = _safe_query(
        """SELECT hole_num, rounds_played, avg_score_to_par,
                  birdie_pct, bogey_pct
           FROM player_hole_history
           WHERE player_key = ? AND (? IS NULL OR course_id = ?)
           ORDER BY hole_num ASC""",
        (player_key, course_id, course_id),
    )
    return {
        "player_key": player_key,
        "available": len(holes) > 0,
        "holes": holes,
        "note": (
            None
            if holes
            else "Hole-level history has not been ingested for this player yet."
        ),
    }


# ─────────────────────────────────────────────────────────────
# 5. Pairwise compare — two players side by side + h2h
# ─────────────────────────────────────────────────────────────
@router.get("/api/redesign/compare")
async def pairwise_compare(
    a: str = Query(...),
    b: str = Query(...),
) -> dict:
    """Everything the compare engine needs for two players in one call."""
    def _sg_block(key: str) -> list[dict]:
        return _safe_query(
            """SELECT metric_name, metric_value, round_window
               FROM metrics
               WHERE player_key = ? AND metric_name LIKE 'sg_%'
               ORDER BY id DESC LIMIT 24""",
            (key,),
        )

    def _trend(key: str, limit: int = 40) -> list[dict]:
        return _safe_query(
            """SELECT event_completed, event_name, course_name,
                      sg_total, fin_text
               FROM rounds WHERE player_key = ?
               ORDER BY event_completed DESC, id DESC LIMIT ?""",
            (key, limit),
        )

    h2h = _safe_query(
        """SELECT po.hit,
                  CASE WHEN p.player_key = ? THEN 'a' ELSE 'b' END AS side,
                  p.tournament_id
           FROM pick_outcomes po
           JOIN picks p ON p.id = po.pick_id
           WHERE (p.player_key = ? AND p.opponent_key = ?)
              OR (p.player_key = ? AND p.opponent_key = ?)
           ORDER BY p.created_at DESC LIMIT 50""",
        (a, a, b, b, a),
    )
    a_sg, b_sg = _sg_block(a), _sg_block(b)
    a_trend, b_trend = _trend(a), _trend(b)
    a_wins = sum(1 for r in h2h if r["side"] == "a" and r["hit"])
    b_wins = sum(1 for r in h2h if r["side"] == "b" and r["hit"])
    return {
        "a": {"player_key": a, "sg": a_sg, "trend": a_trend},
        "b": {"player_key": b, "sg": b_sg, "trend": b_trend},
        "head_to_head": {
            "graded": len(h2h),
            "a_wins": a_wins,
            "b_wins": b_wins,
            "note": "Graded matchup picks between these players (model card history).",
        },
    }
