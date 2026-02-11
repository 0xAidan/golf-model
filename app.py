#!/usr/bin/env python3
"""
Golf Betting Model — Local Web UI

Run:  python3 app.py
Open: http://localhost:8000
"""

import os
import sys
import json
import shutil
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if present (for API keys)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; keys must be in environment

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from src.csv_parser import ingest_folder, classify_file_type, detect_data_mode, detect_round_window
from src.db import (
    get_or_create_tournament, get_active_weights, get_all_players,
    get_conn, init_db, store_results, store_picks,
)
from src.models.composite import compute_composite
from src.models.weights import retune, analyze_pick_performance, get_current_weights
from src.player_normalizer import normalize_name, display_name
from src.odds import fetch_odds_api, load_manual_odds, get_best_odds
from src.value import find_value_bets

import pandas as pd

app = FastAPI(title="Golf Betting Model")

# Store last analysis in memory for the card page
_last_analysis = {}

CSV_DIR = os.path.join(os.path.dirname(__file__), "data", "csvs")
os.makedirs(CSV_DIR, exist_ok=True)


# ── API Endpoints ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML_PAGE


@app.get("/api/tournaments")
async def list_tournaments():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/analyze")
async def run_analysis(
    tournament: str = Form(...),
    course: str = Form(""),
    files: list[UploadFile] = File(...),
):
    """Upload CSVs and run the model."""
    global _last_analysis

    # Create temp folder for this upload batch
    upload_dir = tempfile.mkdtemp(prefix="golf_csvs_")

    try:
        # Save uploaded files
        saved = []
        for f in files:
            if not f.filename.lower().endswith(".csv"):
                continue
            dest = os.path.join(upload_dir, f.filename)
            content = await f.read()
            with open(dest, "wb") as out:
                out.write(content)
            saved.append(f.filename)

        if not saved:
            return JSONResponse({"error": "No CSV files uploaded"}, status_code=400)

        # Get or create tournament
        tournament_id = get_or_create_tournament(tournament, course or None)

        # Check for duplicate imports
        conn = get_conn()
        existing = conn.execute(
            "SELECT filename FROM csv_imports WHERE tournament_id = ?", (tournament_id,)
        ).fetchall()
        existing_names = {r["filename"] for r in existing}
        conn.close()

        # Filter out already-imported files
        new_files = [f for f in saved if f not in existing_names]
        skipped = [f for f in saved if f in existing_names]

        if not new_files:
            return JSONResponse({
                "error": "All files were already imported for this tournament.",
                "skipped": skipped,
            }, status_code=400)

        # If some files were skipped, remove them from the temp dir
        for s in skipped:
            p = os.path.join(upload_dir, s)
            if os.path.exists(p):
                os.remove(p)

        # Ingest CSVs
        summary = ingest_folder(upload_dir, tournament_id)

        # Run models
        weights = get_active_weights()
        composite = compute_composite(tournament_id, weights)

        # Try fetching odds (non-blocking)
        value_bets = {}
        odds_status = "No odds API key set"
        if os.environ.get("ODDS_API_KEY"):
            try:
                all_odds = []
                for market in ["outrights", "top_5", "top_10", "top_20"]:
                    api_odds = fetch_odds_api(market)
                    all_odds.extend(api_odds)
                if all_odds:
                    odds_by_market = {}
                    for o in all_odds:
                        m = o["market"]
                        if m not in odds_by_market:
                            odds_by_market[m] = []
                        odds_by_market[m].append(o)
                    for market, market_odds in odds_by_market.items():
                        best = get_best_odds(market_odds)
                        bt = "outright" if market == "outrights" else market.replace("top_", "top")
                        vb = find_value_bets(composite, best, bet_type=bt,
                                            tournament_id=tournament_id)
                        value_bets[bt] = vb
                    odds_status = f"Fetched {len(all_odds)} odds"
                else:
                    odds_status = "API returned no odds"
            except Exception as e:
                odds_status = f"Odds error: {e}"

        # Store in memory
        _last_analysis = {
            "tournament": tournament,
            "tournament_id": tournament_id,
            "course": course,
            "composite": composite,
            "value_bets": value_bets,
            "weights": weights,
            "timestamp": datetime.now().isoformat(),
        }

        # Also log top picks to DB
        pick_rows = []
        for r in composite[:20]:
            for bt in ["outright", "top5", "top10", "top20"]:
                pick_rows.append({
                    "tournament_id": tournament_id,
                    "bet_type": bt,
                    "player_key": r["player_key"],
                    "player_display": r["player_display"],
                    "opponent_key": None,
                    "opponent_display": None,
                    "composite_score": r["composite"],
                    "course_fit_score": r["course_fit"],
                    "form_score": r["form"],
                    "momentum_score": r["momentum"],
                    "model_prob": None,
                    "market_odds": None,
                    "market_implied_prob": None,
                    "ev": None,
                    "confidence": "high" if r["rank"] <= 5 else "medium" if r["rank"] <= 15 else "low",
                    "reasoning": None,
                })
        store_picks(pick_rows)

        return {
            "success": True,
            "tournament": tournament,
            "course": course,
            "files_imported": len(new_files),
            "files_skipped": skipped,
            "players_scored": len(composite),
            "odds_status": odds_status,
            "summary": {fname: {"type": s.get("type"), "rows": s.get("rows", 0)}
                        for fname, s in summary.items()},
        }

    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.get("/api/card")
async def get_card():
    """Get the latest analysis card."""
    if not _last_analysis:
        return {"error": "No analysis run yet. Upload CSVs first."}
    return _last_analysis


@app.post("/api/results")
async def enter_results(request: Request):
    """Enter tournament results."""
    data = await request.json()
    tournament_name = data.get("tournament")
    results_list = data.get("results", [])

    if not tournament_name or not results_list:
        return JSONResponse({"error": "Need tournament and results"}, status_code=400)

    conn = get_conn()
    row = conn.execute("SELECT id FROM tournaments WHERE name = ?", (tournament_name,)).fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": f"Tournament '{tournament_name}' not found"}, status_code=404)

    tid = row["id"]

    parsed = []
    for entry in results_list:
        name = entry.get("player", "").strip()
        finish = entry.get("finish", "").strip().upper()
        if not name or not finish:
            continue

        pkey = normalize_name(name)
        pdisp = display_name(name)

        made_cut = 1
        finish_pos = None
        if finish in ("CUT", "MC"):
            made_cut = 0
        elif finish in ("W/D", "WD"):
            made_cut = 0
            finish = "W/D"
        elif finish in ("DQ",):
            made_cut = 0
        else:
            try:
                finish_pos = int(finish.replace("T", ""))
            except ValueError:
                pass

        parsed.append({
            "player_key": pkey,
            "player_display": pdisp,
            "finish_position": finish_pos,
            "finish_text": finish,
            "made_cut": made_cut,
        })

    store_results(tid, parsed)

    # Score picks
    conn = get_conn()
    picks = conn.execute("SELECT * FROM picks WHERE tournament_id = ?", (tid,)).fetchall()
    results_rows = conn.execute("SELECT * FROM results WHERE tournament_id = ?", (tid,)).fetchall()

    result_map = {r["player_key"]: dict(r) for r in results_rows}
    scored = 0
    hits = 0
    for pick in picks:
        pk = pick["player_key"]
        bt = pick["bet_type"]
        r = result_map.get(pk)
        if not r:
            continue
        fp = r.get("finish_position")
        hit = 0
        if bt == "outright":
            hit = 1 if fp == 1 else 0
        elif bt == "top5":
            hit = 1 if fp and fp <= 5 else 0
        elif bt == "top10":
            hit = 1 if fp and fp <= 10 else 0
        elif bt == "top20":
            hit = 1 if fp and fp <= 20 else 0
        conn.execute(
            "INSERT INTO pick_outcomes (pick_id, hit, actual_finish) VALUES (?, ?, ?)",
            (pick["id"], hit, r.get("finish_text")),
        )
        scored += 1
        hits += hit

    conn.commit()
    conn.close()

    return {
        "success": True,
        "results_saved": len(parsed),
        "picks_scored": scored,
        "hits": hits,
        "hit_rate": f"{hits/scored:.1%}" if scored else "N/A",
    }


@app.get("/api/dashboard")
async def get_dashboard():
    """Get performance dashboard data."""
    conn = get_conn()
    tournaments = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()

    tournament_data = []
    for t in tournaments:
        picks = conn.execute("SELECT COUNT(*) as c FROM picks WHERE tournament_id = ?", (t["id"],)).fetchone()["c"]
        results = conn.execute("SELECT COUNT(*) as c FROM results WHERE tournament_id = ?", (t["id"],)).fetchone()["c"]
        outcomes = conn.execute(
            "SELECT COUNT(*) as total, SUM(hit) as hits FROM pick_outcomes po JOIN picks p ON po.pick_id = p.id WHERE p.tournament_id = ?",
            (t["id"],)
        ).fetchone()
        tournament_data.append({
            "id": t["id"], "name": t["name"], "course": t["course"],
            "picks": picks, "results": results,
            "outcomes": outcomes["total"] or 0,
            "hits": outcomes["hits"] or 0,
        })
    conn.close()

    analysis = analyze_pick_performance()
    weights = get_current_weights()

    return {
        "tournaments": tournament_data,
        "analysis": analysis,
        "weights": weights,
    }


@app.post("/api/retune")
async def do_retune():
    """Retune weights based on results."""
    result = retune(dry_run=False)
    return result


# ── Data Golf Endpoints ────────────────────────────────────────────

@app.post("/api/backfill")
async def backfill_data(request: Request):
    """Backfill historical round data from Data Golf API."""
    try:
        from src.datagolf import backfill_rounds
    except Exception as e:
        return JSONResponse({"error": f"Import error: {e}"}, status_code=500)

    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    tours = data.get("tours", ["pga"])
    years = data.get("years", [2024, 2025, 2026])

    try:
        summary = backfill_rounds(tours=tours, years=years)
        return {"success": True, "summary": summary}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/sync-datagolf")
async def sync_datagolf(request: Request):
    """Sync DG predictions, decompositions, and field for a tournament."""
    try:
        from src.datagolf import sync_tournament
        from src.rolling_stats import compute_rolling_metrics, get_field_from_metrics
    except Exception as e:
        return JSONResponse({"error": f"Import error: {e}"}, status_code=500)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid or missing JSON body"}, status_code=400)
    tournament_name = data.get("tournament", "")
    course = data.get("course", "")
    tour = data.get("tour", "pga")
    course_num = data.get("course_num")

    if not tournament_name:
        return JSONResponse({"error": "Tournament name required"}, status_code=400)

    tournament_id = get_or_create_tournament(tournament_name, course)

    results = {"tournament_id": tournament_id, "steps": {}}

    # 1. Sync DG predictions + field
    try:
        sync_result = sync_tournament(tournament_id, tour=tour)
        results["steps"]["dg_sync"] = sync_result
    except Exception as e:
        results["steps"]["dg_sync"] = {"error": str(e)}

    # 2. Compute rolling stats from stored rounds
    try:
        field = get_field_from_metrics(tournament_id)
        if field:
            rolling_result = compute_rolling_metrics(
                tournament_id, field, course_num=course_num
            )
            results["steps"]["rolling_stats"] = rolling_result
        else:
            results["steps"]["rolling_stats"] = {"status": "no_field", "message": "No players in field yet"}
    except Exception as e:
        results["steps"]["rolling_stats"] = {"error": str(e)}

    return {"success": True, **results}


@app.get("/api/backfill-status")
async def backfill_status():
    """Get the status of historical data backfill."""
    from src.db import get_rounds_backfill_status, get_rounds_count
    return {
        "total_rounds": get_rounds_count(),
        "by_tour_year": get_rounds_backfill_status(),
    }


# ── Course Profile Endpoints ──────────────────────────────────────

@app.post("/api/course-profile")
async def upload_course_profile(
    course: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload course screenshots for AI extraction (OpenAI or Anthropic vision)."""
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_openai and not has_anthropic:
        return JSONResponse(
            {"error": "No vision API key set. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."},
            status_code=400,
        )

    try:
        from src.course_profile import extract_from_folder, save_course_profile, course_to_model_weights
    except Exception as e:
        return JSONResponse({"error": f"Import error: {e}"}, status_code=500)
    # Use whichever key is available (extract_from_folder auto-detects provider)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # Save uploaded images to temp folder
    temp_dir = tempfile.mkdtemp(prefix="course_imgs_")
    try:
        for f in files:
            if f.filename and any(f.filename.lower().endswith(ext)
                                  for ext in (".png", ".jpg", ".jpeg", ".webp")):
                fpath = os.path.join(temp_dir, f.filename)
                with open(fpath, "wb") as out:
                    content = await f.read()
                    out.write(content)

        # Extract data from images
        data = extract_from_folder(temp_dir, api_key)
        if not data or (not data.get("course_facts") and not data.get("skill_ratings")):
            return JSONResponse({"error": "No data could be extracted from the screenshots."}, status_code=400)

        # Save profile
        filepath = save_course_profile(course, data)
        adjustments = course_to_model_weights(data)

        return {
            "success": True,
            "course": course,
            "filepath": filepath,
            "facts_count": len(data.get("course_facts", {})),
            "ratings_count": len(data.get("skill_ratings", {})),
            "stats_count": len(data.get("stat_comparisons", [])),
            "weight_adjustments": {k: v for k, v in adjustments.items() if k != "course_profile"},
            "profile_summary": {
                "skill_ratings": data.get("skill_ratings", {}),
                "course_facts": {k: v for k, v in data.get("course_facts", {}).items()
                                 if k in ("par", "yardage", "course_type", "greens_surface",
                                          "greens_speed", "avg_scoring_conditions")},
            },
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/saved-courses")
async def list_saved_courses():
    """List all saved course profiles."""
    from src.course_profile import list_saved_courses, load_course_profile, course_to_model_weights
    courses = list_saved_courses()
    result = []
    for name in courses:
        profile = load_course_profile(name)
        adj = course_to_model_weights(profile) if profile else {}
        result.append({
            "name": name,
            "ratings": profile.get("skill_ratings", {}) if profile else {},
            "adjustments": {k: v for k, v in adj.items() if k != "course_profile"},
        })
    return result


# ── AI Brain Endpoints ─────────────────────────────────────────────

@app.get("/api/ai-status")
async def ai_status():
    """Check AI brain configuration and status."""
    from src.ai_brain import get_ai_status
    return get_ai_status()


@app.post("/api/ai/pre-analysis")
async def ai_pre_analysis(request: Request):
    """Run AI pre-tournament analysis."""
    from src.ai_brain import pre_tournament_analysis, is_ai_available
    if not is_ai_available():
        return JSONResponse({"error": "AI brain not configured. Set OPENAI_API_KEY."}, status_code=400)

    if not _last_analysis:
        return JSONResponse({"error": "Run analysis first (upload CSVs or sync DG)."}, status_code=400)

    tournament_id = _last_analysis.get("tournament_id")
    composite = _last_analysis.get("composite", [])
    course = _last_analysis.get("course", "")

    # Load course profile if available
    course_profile = None
    if course:
        from src.course_profile import load_course_profile
        course_profile = load_course_profile(course)

    result = pre_tournament_analysis(
        tournament_id=tournament_id,
        composite_results=composite,
        course_profile=course_profile,
        tournament_name=_last_analysis.get("tournament", ""),
        course_name=course,
    )
    return result


@app.post("/api/ai/betting-decisions")
async def ai_betting_decisions(request: Request):
    """Get AI betting decisions."""
    from src.ai_brain import make_betting_decisions, is_ai_available
    if not is_ai_available():
        return JSONResponse({"error": "AI brain not configured."}, status_code=400)

    if not _last_analysis:
        return JSONResponse({"error": "Run analysis first."}, status_code=400)

    tournament_id = _last_analysis.get("tournament_id")
    value_bets = _last_analysis.get("value_bets", {})
    course = _last_analysis.get("course", "")

    # Get pre-analysis if it exists
    from src.db import get_ai_decisions
    prior = get_ai_decisions(tournament_id=tournament_id, phase="pre_analysis")
    pre_analysis = json.loads(prior[0]["output_json"]) if prior else None

    result = make_betting_decisions(
        tournament_id=tournament_id,
        value_bets_by_type=value_bets,
        pre_analysis=pre_analysis,
        composite_results=_last_analysis.get("composite", None),
        tournament_name=_last_analysis.get("tournament", ""),
        course_name=course,
    )
    return result


@app.post("/api/ai/post-review")
async def ai_post_review(request: Request):
    """Run AI post-tournament review and learning."""
    from src.ai_brain import post_tournament_review, is_ai_available
    from src.learning import score_picks_for_tournament
    if not is_ai_available():
        return JSONResponse({"error": "AI brain not configured."}, status_code=400)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid or missing JSON body"}, status_code=400)
    tournament_name = data.get("tournament", "")
    if not tournament_name:
        return JSONResponse({"error": "Tournament name required."}, status_code=400)

    conn = get_conn()
    row = conn.execute("SELECT * FROM tournaments WHERE name = ?", (tournament_name,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": f"Tournament '{tournament_name}' not found."}, status_code=404)

    tid = row["id"]
    course = row["course"] or ""

    # Score picks first
    scoring = score_picks_for_tournament(tid)

    result = post_tournament_review(
        tournament_id=tid,
        scoring_result=scoring,
        tournament_name=tournament_name,
        course_name=course,
    )
    return {"scoring": scoring, "review": result}


# ── Learning Endpoints ─────────────────────────────────────────────

@app.post("/api/learn")
async def post_tournament_learn_endpoint(request: Request):
    """Full post-tournament learning cycle."""
    from src.learning import post_tournament_learn

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid or missing JSON body"}, status_code=400)
    tournament_name = data.get("tournament", "")
    event_id = data.get("event_id")
    year = data.get("year")
    course_num = data.get("course_num")
    course_name = data.get("course_name")

    if not tournament_name:
        return JSONResponse({"error": "Tournament name required."}, status_code=400)

    conn = get_conn()
    row = conn.execute("SELECT id FROM tournaments WHERE name = ?", (tournament_name,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": f"Tournament '{tournament_name}' not found."}, status_code=404)

    result = post_tournament_learn(
        tournament_id=row["id"],
        event_id=event_id,
        year=year,
        course_num=course_num,
        course_name=course_name or "",
    )
    return result


@app.get("/api/calibration")
async def get_calibration():
    """Get model calibration and ROI data."""
    from src.learning import compute_calibration
    return compute_calibration()


@app.get("/api/ai-memories")
async def get_memories(topic: str = None):
    """Get AI brain memories, optionally filtered by topic."""
    from src.db import get_ai_memories, get_all_ai_memory_topics
    topics = [topic] if topic else None
    memories = get_ai_memories(topics=topics)
    all_topics = get_all_ai_memory_topics()
    return {"memories": memories, "topics": all_topics}


# ── HTML Page (everything in one file) ──────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Golf Betting Model</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
h1 { font-size: 1.6em; margin-bottom: 5px; color: #fff; }
h2 { font-size: 1.15em; margin: 20px 0 10px; color: #4ade80; border-bottom: 1px solid #333; padding-bottom: 5px; }
h3 { font-size: 1em; margin: 15px 0 8px; color: #94a3b8; }

/* Tabs */
.tabs { display: flex; gap: 0; margin: 20px 0 0; border-bottom: 2px solid #333; }
.tab { padding: 10px 20px; cursor: pointer; color: #888; border-bottom: 2px solid transparent; margin-bottom: -2px; font-size: 0.95em; }
.tab:hover { color: #ccc; }
.tab.active { color: #4ade80; border-bottom-color: #4ade80; }
.tab-content { display: none; padding: 20px 0; }
.tab-content.active { display: block; }

/* Forms */
input, select { background: #1e2030; border: 1px solid #333; color: #e0e0e0; padding: 8px 12px; border-radius: 6px; font-size: 0.95em; }
input:focus { outline: none; border-color: #4ade80; }
label { display: block; margin-bottom: 4px; color: #94a3b8; font-size: 0.85em; }
.form-row { display: flex; gap: 15px; margin-bottom: 15px; }
.form-row > div { flex: 1; }
button { background: #4ade80; color: #000; border: none; padding: 10px 24px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.95em; }
button:hover { background: #22c55e; }
button:disabled { background: #333; color: #666; cursor: not-allowed; }
button.secondary { background: #334155; color: #e0e0e0; }
button.secondary:hover { background: #475569; }

/* Drop zone */
.dropzone { border: 2px dashed #333; border-radius: 10px; padding: 40px; text-align: center; color: #666; cursor: pointer; transition: all 0.2s; }
.dropzone:hover, .dropzone.dragover { border-color: #4ade80; color: #4ade80; background: rgba(74, 222, 128, 0.05); }
.dropzone input { display: none; }
.file-list { margin: 10px 0; text-align: left; }
.file-item { padding: 4px 0; font-size: 0.85em; color: #94a3b8; }
.file-item .type { color: #4ade80; font-size: 0.8em; margin-left: 8px; }

/* Table */
table { width: 100%; border-collapse: collapse; font-size: 0.85em; margin: 10px 0; }
th { text-align: left; padding: 8px; color: #94a3b8; border-bottom: 1px solid #333; font-weight: 500; }
td { padding: 7px 8px; border-bottom: 1px solid #1e2030; }
tr:hover td { background: #1a1d2e; }
.rank-1 td { background: rgba(74, 222, 128, 0.1); }
.rank-top5 td { background: rgba(74, 222, 128, 0.05); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.trend-hot { color: #4ade80; }
.trend-warm { color: #86efac; }
.trend-cool { color: #fbbf24; }
.trend-cold { color: #ef4444; }

/* Card sections */
.card-section { background: #1a1d2e; border-radius: 8px; padding: 15px; margin: 10px 0; }
.pick { padding: 6px 0; border-bottom: 1px solid #252840; }
.pick:last-child { border-bottom: none; }
.pick .name { font-weight: 600; color: #fff; }
.pick .reason { color: #94a3b8; font-size: 0.85em; margin-left: 8px; }
.pick .value-tag { background: #4ade80; color: #000; font-size: 0.75em; padding: 2px 6px; border-radius: 3px; font-weight: 600; margin-left: 6px; }
.fade { color: #ef4444; }
.matchup .vs { color: #666; margin: 0 6px; }
.matchup .edge { color: #4ade80; font-size: 0.85em; margin-left: 8px; }

/* Status */
.status { padding: 10px; border-radius: 6px; margin: 10px 0; font-size: 0.9em; }
.status.info { background: #1e3a5f; color: #7dd3fc; }
.status.success { background: #14532d; color: #4ade80; }
.status.error { background: #450a0a; color: #fca5a5; }
.status.loading { background: #1e2030; color: #94a3b8; }

/* Results entry */
.results-input { width: 100%; background: #1e2030; border: 1px solid #333; color: #e0e0e0; padding: 10px; border-radius: 6px; font-family: monospace; font-size: 0.9em; min-height: 200px; resize: vertical; }

/* Dashboard stats */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 10px 0; }
.stat-box { background: #1a1d2e; border-radius: 8px; padding: 15px; text-align: center; }
.stat-box .number { font-size: 1.8em; font-weight: 700; color: #4ade80; }
.stat-box .label { font-size: 0.8em; color: #94a3b8; margin-top: 4px; }

.spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #333; border-top-color: #4ade80; border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 8px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="container">
    <h1>Golf Betting Model</h1>
    <p style="color:#94a3b8; font-size:0.85em;">Data Golf + AI Brain + Self-Improving Model</p>

    <div class="tabs">
        <div class="tab active" onclick="showTab('setup')">Setup & Sync</div>
        <div class="tab" onclick="showTab('predictions')">Predictions</div>
        <div class="tab" onclick="showTab('ai')">AI Brain</div>
        <div class="tab" onclick="showTab('data')">Add Data</div>
        <div class="tab" onclick="showTab('dashboard')">Dashboard</div>
    </div>

    <!-- ══ SETUP & SYNC TAB ══════════════════════════════ -->
    <div id="tab-setup" class="tab-content active">
        <h2>1. Tournament Setup</h2>
        <div class="form-row">
            <div>
                <label>Tournament Name</label>
                <input id="tournament" type="text" placeholder="e.g. Genesis Invitational 2026" style="width:100%">
            </div>
            <div>
                <label>Course Name</label>
                <input id="course" type="text" placeholder="e.g. Riviera" style="width:100%">
            </div>
        </div>
        <div class="form-row">
            <div>
                <label>Tour</label>
                <select id="tour" style="width:100%">
                    <option value="pga">PGA Tour</option>
                    <option value="euro">DP World Tour</option>
                    <option value="kft">Korn Ferry Tour</option>
                    <option value="alt">LIV Golf</option>
                </select>
            </div>
            <div>
                <label>DG Course Number (optional)</label>
                <input id="courseNum" type="number" placeholder="e.g. 5 for Pebble Beach" style="width:100%">
            </div>
        </div>

        <h2>2. Sync Data Golf</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">Pulls predictions, field updates, and computes rolling stats from stored round data. This is the main data source — no CSVs needed.</p>
        <button id="syncBtn" onclick="syncDG()">Sync Data Golf</button>
        <button class="secondary" onclick="runCsvAnalysis()" style="margin-left:10px;">Run CSV Analysis Instead</button>
        <div id="syncStatus" style="margin-top:10px;"></div>

        <h2>3. Backfill Status</h2>
        <div id="backfillStatus"><div class="status loading"><span class="spinner"></span>Loading...</div></div>
        <button class="secondary" onclick="runBackfill()" style="margin-top:10px;">Backfill Historical Data (PGA 2024-2026)</button>
        <div id="backfillResult" style="margin-top:8px;"></div>
    </div>

    <!-- ══ PREDICTIONS TAB ═══════════════════════════════ -->
    <div id="tab-predictions" class="tab-content">
        <div id="predictionsContent">
            <div class="status info">No analysis run yet. Go to Setup & Sync first.</div>
        </div>
    </div>

    <!-- ══ AI BRAIN TAB ══════════════════════════════════ -->
    <div id="tab-ai" class="tab-content">
        <h2>AI Brain Status</h2>
        <div id="aiStatus"><div class="status loading"><span class="spinner"></span>Checking...</div></div>

        <h2>Pre-Tournament Analysis</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">AI analyzes the field, course, and memories to find qualitative edges.</p>
        <button onclick="runAiPreAnalysis()">Run Pre-Tournament Analysis</button>
        <div id="aiPreResult" style="margin-top:10px;"></div>

        <h2>Betting Decisions</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">AI reviews value bets and makes portfolio-level betting recommendations.</p>
        <button onclick="runAiBetting()">Get Betting Decisions</button>
        <div id="aiBetResult" style="margin-top:10px;"></div>

        <h2>Post-Tournament Review</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">AI reviews results, learns from mistakes, stores insights in memory.</p>
        <div style="margin-bottom:10px;">
            <label>Tournament to review</label>
            <select id="reviewTournament" style="width:100%;"><option value="">Loading...</option></select>
        </div>
        <button onclick="runAiPostReview()">Run Post-Tournament Review</button>
        <div id="aiPostResult" style="margin-top:10px;"></div>

        <h2>AI Memories</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">Persistent learnings the AI has accumulated over time.</p>
        <div id="aiMemories"><div class="status info">Click to load memories</div></div>
        <button class="secondary" onclick="loadMemories()" style="margin-top:10px;">Load Memories</button>
    </div>

    <!-- ══ ADD DATA TAB ══════════════════════════════════ -->
    <div id="tab-data" class="tab-content">
        <h2>Upload Betsperts CSVs (Optional Supplement)</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">Data Golf provides the core data. CSVs add extra granularity (lie-specific scrambling, approach by yardage, etc.)</p>
        <div style="margin-bottom:10px;">
            <button onclick="document.getElementById('fileInput').click()" style="margin-right:10px;">Select CSV Files</button>
            <button class="secondary" onclick="clearFiles()">Clear All</button>
            <input type="file" id="fileInput" multiple accept=".csv" style="display:none">
        </div>
        <div class="dropzone" id="dropzone">
            <p style="font-size:1.1em; margin-bottom:8px;">Drag and drop CSV files here</p>
            <p style="font-size:0.85em;">Cheat sheets, sim, strokes gained, OTT, approach, putting, around green, course-specific data</p>
        </div>
        <div id="fileCount" style="margin:8px 0; font-weight:600; color:#4ade80;"></div>
        <div id="fileList" class="file-list" style="max-height:200px; overflow-y:auto;"></div>

        <h2>Upload Course Profile Screenshots</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">
            Upload Betsperts course screenshots (Course Facts, Off the Tee, Approach, Around Green, Putting, Scoring tables).
            Claude Vision extracts structured data for course-specific weight adjustments.
            <strong>Requires OPENAI_API_KEY or ANTHROPIC_API_KEY.</strong>
        </p>
        <div class="form-row">
            <div>
                <label>Course Name (for this profile)</label>
                <input id="profileCourse" type="text" placeholder="e.g. Pebble Beach" style="width:100%">
            </div>
        </div>
        <div style="margin-bottom:10px;">
            <button onclick="document.getElementById('imgInput').click()">Select Screenshot Images</button>
            <input type="file" id="imgInput" multiple accept=".png,.jpg,.jpeg,.webp" style="display:none">
        </div>
        <div id="imgList" style="margin:8px 0; font-size:0.85em; color:#94a3b8;"></div>
        <button onclick="uploadCourseProfile()">Extract Course Profile</button>
        <div id="courseProfileResult" style="margin-top:10px;"></div>

        <h2>Saved Course Profiles</h2>
        <div id="savedCourses"><div class="status info">Loading...</div></div>

        <h2>Enter Tournament Results</h2>
        <div style="margin-bottom:15px;">
            <label>Tournament</label>
            <select id="resultsTournament" style="width:100%;"><option value="">Loading...</option></select>
        </div>
        <label>Results (one per line: Player Name, Finish)</label>
        <textarea id="resultsText" class="results-input" placeholder="Scottie Scheffler, 1&#10;Xander Schauffele, T3&#10;Tom Kim, CUT"></textarea>
        <div style="margin-top:10px;">
            <button onclick="submitResults()">Save Results & Score Picks</button>
        </div>
        <div id="resultsStatus"></div>
    </div>

    <!-- ══ DASHBOARD TAB ═════════════════════════════════ -->
    <div id="tab-dashboard" class="tab-content">
        <div id="dashboardContent"><div class="status info">Loading...</div></div>
    </div>
</div>

<script>
// ── Tab switching ──
const TAB_NAMES = ['setup','predictions','ai','data','dashboard'];
function showTab(name) {
    document.querySelectorAll('.tab').forEach((t, i) => {
        t.classList.toggle('active', TAB_NAMES[i] === name);
    });
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const el = document.getElementById('tab-' + name);
    if (el) el.classList.add('active');

    if (name === 'predictions') loadPredictions();
    if (name === 'ai') { loadAiStatus(); loadTournaments(); }
    if (name === 'data') { loadTournaments(); loadSavedCourses(); }
    if (name === 'dashboard') loadDashboard();
    if (name === 'setup') loadBackfillStatus();
}

<script>
// ══ FILE UPLOAD ══
let selectedFiles = [];
let selectedImages = [];

// Deferred init — bind file/drop events after DOM is fully ready
document.addEventListener('DOMContentLoaded', function() {
    try {
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('fileInput');
        const imgInput = document.getElementById('imgInput');

        if (dropzone) {
            ['dragenter','dragover','dragleave','drop'].forEach(evt => {
                dropzone.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); });
            });
            document.body.addEventListener('dragover', e => { e.preventDefault(); });
            document.body.addEventListener('drop', e => { e.preventDefault(); });
            dropzone.addEventListener('dragenter', () => dropzone.classList.add('dragover'));
            dropzone.addEventListener('dragover', () => dropzone.classList.add('dragover'));
            dropzone.addEventListener('dragleave', e => { if (!dropzone.contains(e.relatedTarget)) dropzone.classList.remove('dragover'); });
            dropzone.addEventListener('drop', e => {
                dropzone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files && files.length > 0) addFiles(files);
            });
        }
        if (fileInput) {
            fileInput.addEventListener('change', e => { if (e.target.files.length) addFiles(e.target.files); fileInput.value = ''; });
        }
        if (imgInput) {
            imgInput.addEventListener('change', e => {
                if (e.target.files.length) {
                    selectedImages = Array.from(e.target.files);
                    const el = document.getElementById('imgList');
                    if (el) el.textContent = selectedImages.map(f=>f.name).join(', ');
                }
                imgInput.value = '';
            });
        }
    } catch(err) { console.error('File upload init error:', err); }

    // Load initial data
    loadBackfillStatus();
});

function addFiles(fl) {
    for (const f of Array.from(fl)) {
        if (f.name.toLowerCase().endsWith('.csv') && !selectedFiles.some(s=>s.name===f.name)) selectedFiles.push(f);
    }
    renderFiles();
}
function clearFiles() { selectedFiles = []; renderFiles(); }
function renderFiles() {
    const fc = document.getElementById('fileCount');
    const fl = document.getElementById('fileList');
    fc.textContent = selectedFiles.length ? selectedFiles.length + ' CSV files ready' : '';
    fl.innerHTML = selectedFiles.map(f=>'<div class="file-item">'+f.name+' <span style="color:#666;font-size:0.8em;">('+Math.round(f.size/1024)+' KB)</span></div>').join('');
}

// ══ SYNC DATA GOLF ══
async function syncDG() {
    const t = document.getElementById('tournament').value;
    const c = document.getElementById('course').value;
    const tour = document.getElementById('tour').value;
    const cn = document.getElementById('courseNum').value;
    if (!t) { alert('Enter a tournament name first'); return; }
    const el = document.getElementById('syncStatus');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Syncing Data Golf... (predictions + rolling stats, may take 30-60s)</div>';
    try {
        const resp = await fetch('/api/sync-datagolf', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({tournament:t, course:c, tour:tour, course_num:cn?parseInt(cn):null})
        });
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        const steps = data.steps || {};
        let html = '<div class="status success">Sync complete!</div>';
        if (steps.dg_sync) html += '<div class="status info">DG Sync: '+JSON.stringify(steps.dg_sync).substring(0,200)+'</div>';
        if (steps.rolling_stats) html += '<div class="status info">Rolling Stats: '+(steps.rolling_stats.total_metrics||0)+' metrics computed for '+(steps.rolling_stats.players_in_field||0)+' players</div>';
        html += '<div style="margin-top:10px;"><button onclick="showTab(\'predictions\')">View Predictions →</button></div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

async function runCsvAnalysis() {
    const t = document.getElementById('tournament').value;
    const c = document.getElementById('course').value;
    if (!t || !selectedFiles.length) { alert('Enter tournament name and select CSV files'); return; }
    const el = document.getElementById('syncStatus');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Running CSV analysis...</div>';
    const form = new FormData();
    form.append('tournament', t); form.append('course', c);
    for (const f of selectedFiles) form.append('files', f);
    try {
        const resp = await fetch('/api/analyze', {method:'POST', body:form});
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        el.innerHTML = '<div class="status success">CSV analysis complete: '+data.players_scored+' players scored.</div><div style="margin-top:10px;"><button onclick="showTab(\'predictions\')">View Predictions →</button></div>';
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

// ══ BACKFILL ══
async function loadBackfillStatus() {
    const el = document.getElementById('backfillStatus');
    try {
        const resp = await fetch('/api/backfill-status');
        const data = await resp.json();
        if (!data.total_rounds) { el.innerHTML='<div class="status info">No historical data yet. Click Backfill to load 2-3 years of PGA Tour rounds.</div>'; return; }
        let html = '<div class="stats-grid"><div class="stat-box"><div class="number">'+data.total_rounds.toLocaleString()+'</div><div class="label">Total Rounds</div></div></div>';
        if (data.by_tour_year && data.by_tour_year.length) {
            html += '<table><tr><th>Tour</th><th>Year</th><th>Rounds</th><th>Players</th><th>Events</th></tr>';
            for (const r of data.by_tour_year) html += '<tr><td>'+r.tour.toUpperCase()+'</td><td>'+r.year+'</td><td class="num">'+r.round_count+'</td><td class="num">'+r.player_count+'</td><td class="num">'+r.event_count+'</td></tr>';
            html += '</table>';
        }
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error loading status</div>'; }
}

async function runBackfill() {
    const el = document.getElementById('backfillResult');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Backfilling PGA 2024-2026... (may take 1-2 minutes)</div>';
    try {
        const resp = await fetch('/api/backfill', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tours:['pga'],years:[2024,2025,2026]})});
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        el.innerHTML = '<div class="status success">Backfill complete! '+JSON.stringify(data.summary)+'</div>';
        loadBackfillStatus();
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

// ══ PREDICTIONS ══
async function loadPredictions() {
    const el = document.getElementById('predictionsContent');
    try {
        const resp = await fetch('/api/card');
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status info">'+data.error+'</div>'; return; }
        renderPredictions(data, el);
    } catch(e) { el.innerHTML='<div class="status error">Error loading predictions</div>'; }
}

function trendIcon(dir) {
    return {hot:'<span class="trend-hot">↑↑</span>', warming:'<span class="trend-warm">↑</span>',
            cooling:'<span class="trend-cool">↓</span>', cold:'<span class="trend-cold">↓↓</span>'}[dir] || '—';
}

function renderPredictions(data, el) {
    const c = data.composite || [];
    const vb = data.value_bets || {};
    const w = data.weights || {};
    let html = '<h2>'+data.tournament+' — '+(data.course||'')+'</h2>';
    html += '<p style="color:#94a3b8;font-size:0.8em;">Generated: '+new Date(data.timestamp).toLocaleString()+' · Weights: course '+((w.course_fit||0.4)*100).toFixed(0)+'% / form '+((w.form||0.4)*100).toFixed(0)+'% / momentum '+((w.momentum||0.2)*100).toFixed(0)+'%</p>';

    // Model rankings
    html += '<h2>Model Rankings</h2><table><tr><th>#</th><th>Player</th><th>Composite</th><th>Course Fit</th><th>Form</th><th>Momentum</th><th>Trend</th></tr>';
    for (let i = 0; i < Math.min(40, c.length); i++) {
        const r = c[i];
        const cls = r.rank===1?'rank-1':r.rank<=5?'rank-top5':'';
        html += '<tr class="'+cls+'"><td class="num">'+r.rank+'</td><td>'+r.player_display+(r.ai_adjustment?(' <span style="color:#fbbf24;font-size:0.8em;">(AI '+(r.ai_adjustment>0?'+':'')+r.ai_adjustment+')</span>'):'')+
            '</td><td class="num">'+r.composite.toFixed(1)+'</td><td class="num">'+r.course_fit.toFixed(1)+'</td><td class="num">'+r.form.toFixed(1)+'</td><td class="num">'+r.momentum.toFixed(1)+'</td><td>'+trendIcon(r.momentum_direction)+'</td></tr>';
    }
    html += '</table>';

    // Value bets
    for (const [bt, bets] of Object.entries(vb)) {
        const valueBets = bets.filter(b=>b.is_value);
        if (!valueBets.length) continue;
        html += '<h2>Value Bets: '+bt+'</h2><table><tr><th>Player</th><th>Model %</th><th>Market %</th><th>Odds</th><th>EV</th><th>Source</th><th>Book</th></tr>';
        for (const b of valueBets.slice(0,15)) {
            const evColor = b.ev > 0.15 ? '#4ade80' : b.ev > 0.05 ? '#86efac' : '#fbbf24';
            html += '<tr><td>'+b.player_display+'</td><td class="num">'+(b.model_prob*100).toFixed(1)+'%</td><td class="num">'+(b.market_prob*100).toFixed(1)+'%</td><td class="num">'+b.best_odds+'</td><td class="num" style="color:'+evColor+'">'+b.ev_pct+'</td><td style="font-size:0.8em;color:#94a3b8;">'+(b.prob_source||'')+'</td><td style="font-size:0.8em;">'+b.best_book+'</td></tr>';
        }
        html += '</table>';
    }

    // Quick picks by section
    const sections = [{title:'Outright',n:5},{title:'Top 5',n:6},{title:'Top 10',n:10},{title:'Top 20',n:15}];
    for (const sec of sections) {
        html += '<h2>'+sec.title+' Picks</h2><div class="card-section">';
        for (let i=0;i<Math.min(sec.n,c.length);i++) {
            const r=c[i]; let parts=[];
            if(r.course_fit>65)parts.push('course '+r.course_fit.toFixed(0));
            if(r.form>65)parts.push('form '+r.form.toFixed(0));
            if(r.momentum_direction==='hot')parts.push('hot');
            html+='<div class="pick"><span class="name">#'+r.rank+' '+r.player_display+'</span><span class="reason">'+(parts.join(' · ')||'composite edge')+'</span></div>';
        }
        html += '</div>';
    }

    el.innerHTML = html;
}

// ══ AI BRAIN ══
async function loadAiStatus() {
    const el = document.getElementById('aiStatus');
    try {
        const resp = await fetch('/api/ai-status');
        const data = await resp.json();
        if (data.available) {
            el.innerHTML = '<div class="status success">AI Brain: '+data.provider.toUpperCase()+' ('+data.model+') · '+data.memory_count+' memories across '+data.memory_topics.length+' topics</div>';
        } else {
            el.innerHTML = '<div class="status error">AI Brain not configured. Set OPENAI_API_KEY in .env</div>';
        }
    } catch(e) { el.innerHTML='<div class="status error">Error checking AI status</div>'; }
}

async function runAiPreAnalysis() {
    const el = document.getElementById('aiPreResult');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Running AI pre-tournament analysis... (10-20 seconds)</div>';
    try {
        const resp = await fetch('/api/ai/pre-analysis', {method:'POST'});
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        let html = '<div class="card-section">';
        html += '<h3>Course Narrative</h3><p style="color:#e0e0e0;">'+data.course_narrative+'</p>';
        html += '<h3>Key Factors</h3><ul style="margin-left:20px;color:#94a3b8;">';
        for (const f of data.key_factors||[]) html += '<li>'+f+'</li>';
        html += '</ul>';
        if (data.players_to_watch && data.players_to_watch.length) {
            html += '<h3>Players to Watch</h3>';
            for (const p of data.players_to_watch) html += '<div class="pick"><span class="name">'+p.player+'</span> <span class="value-tag">+'+(p.adjustment||0)+'</span><span class="reason">'+p.edge+'</span></div>';
        }
        if (data.players_to_fade && data.players_to_fade.length) {
            html += '<h3>Players to Fade</h3>';
            for (const p of data.players_to_fade) html += '<div class="pick"><span class="name fade">'+p.player+'</span> <span style="color:#ef4444;font-size:0.8em;">'+(p.adjustment||0)+'</span><span class="reason">'+p.reason+'</span></div>';
        }
        html += '<p style="margin-top:10px;color:#94a3b8;font-size:0.85em;">Confidence: '+(data.confidence||'?')+'</p>';
        html += '</div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

async function runAiBetting() {
    const el = document.getElementById('aiBetResult');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>AI making betting decisions... (10-20 seconds)</div>';
    try {
        const resp = await fetch('/api/ai/betting-decisions', {method:'POST'});
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        let html = '<div class="card-section">';
        for (const d of data.decisions||[]) {
            html += '<div class="pick"><span class="name">'+d.player+'</span> <span class="value-tag">'+d.bet_type+' @ '+d.odds+'</span><span class="reason">'+d.recommended_stake+' · '+d.confidence+' · '+d.reasoning+'</span></div>';
        }
        html += '<h3>Portfolio Notes</h3><p style="color:#94a3b8;">'+data.portfolio_notes+'</p>';
        if (data.pass_notes) html += '<h3>Passing On</h3><p style="color:#94a3b8;">'+data.pass_notes+'</p>';
        html += '<p style="color:#4ade80;margin-top:10px;">Total: '+data.total_units+' units · Expected ROI: '+data.expected_roi+'</p>';
        html += '</div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

async function runAiPostReview() {
    const t = document.getElementById('reviewTournament').value;
    if (!t) { alert('Select a tournament to review'); return; }
    const el = document.getElementById('aiPostResult');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>AI reviewing tournament... (10-20 seconds)</div>';
    try {
        const resp = await fetch('/api/ai/post-review', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tournament:t})});
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        const r = data.review || data;
        let html = '<div class="card-section">';
        html += '<h3>Summary</h3><p style="color:#e0e0e0;">'+r.summary+'</p>';
        html += '<h3>What Worked</h3><p style="color:#4ade80;">'+r.what_worked+'</p>';
        html += '<h3>What Missed</h3><p style="color:#ef4444;">'+r.what_missed+'</p>';
        if (r.learnings && r.learnings.length) {
            html += '<h3>Learnings Stored</h3>';
            for (const l of r.learnings) html += '<div class="pick"><span style="color:#4ade80;">['+l.topic+']</span> <span class="reason">'+l.insight+' (conf: '+l.confidence+')</span></div>';
        }
        html += '<p style="color:#94a3b8;margin-top:10px;font-size:0.85em;">Calibration: '+r.calibration_note+'</p>';
        html += '</div>';
        if (data.scoring) el.innerHTML = '<div class="status info">Scoring: '+data.scoring.hits+'/'+data.scoring.scored+' hits ('+((data.scoring.hit_rate||0)*100).toFixed(0)+'%) · P/L: '+data.scoring.total_profit+' units</div>' + html;
        else el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

async function loadMemories() {
    const el = document.getElementById('aiMemories');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Loading...</div>';
    try {
        const resp = await fetch('/api/ai-memories');
        const data = await resp.json();
        if (!data.memories || !data.memories.length) { el.innerHTML='<div class="status info">No memories yet. Run a post-tournament review first.</div>'; return; }
        let html = '<p style="color:#94a3b8;font-size:0.85em;margin-bottom:8px;">Topics: '+data.topics.join(', ')+'</p>';
        html += '<table><tr><th>Topic</th><th>Insight</th><th>Confidence</th><th>Age</th></tr>';
        for (const m of data.memories) {
            let age = '';
            if (m.created_at) { const d = Math.round((Date.now()-new Date(m.created_at).getTime())/(1000*60*60*24)); age = d+'d ago'; }
            html += '<tr><td style="color:#4ade80;">'+m.topic+'</td><td>'+m.insight+'</td><td class="num">'+(m.confidence||'?')+'</td><td style="color:#94a3b8;font-size:0.8em;">'+age+'</td></tr>';
        }
        html += '</table>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error loading memories</div>'; }
}

// ══ COURSE PROFILES ══
async function uploadCourseProfile() {
    const course = document.getElementById('profileCourse').value;
    if (!course || !selectedImages.length) { alert('Enter course name and select screenshot images'); return; }
    const el = document.getElementById('courseProfileResult');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Extracting course data from screenshots... (30-60 seconds)</div>';
    const form = new FormData();
    form.append('course', course);
    for (const f of selectedImages) form.append('files', f);
    try {
        const resp = await fetch('/api/course-profile', {method:'POST', body:form});
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        let html = '<div class="status success">Course profile saved for '+data.course+'!</div>';
        const ps = data.profile_summary || {};
        if (ps.skill_ratings) {
            html += '<div class="card-section"><h3>Skill Difficulty Ratings</h3>';
            for (const [k,v] of Object.entries(ps.skill_ratings)) html += '<div style="padding:2px 0;"><span style="color:#94a3b8;">'+k+':</span> <span style="color:#4ade80;">'+v+'</span></div>';
            html += '</div>';
        }
        if (data.weight_adjustments) {
            html += '<div class="card-section"><h3>Weight Multipliers</h3>';
            for (const [k,v] of Object.entries(data.weight_adjustments)) html += '<div style="padding:2px 0;"><span style="color:#94a3b8;">'+k+':</span> '+v+'x</div>';
            html += '</div>';
        }
        el.innerHTML = html;
        loadSavedCourses();
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

async function loadSavedCourses() {
    const el = document.getElementById('savedCourses');
    try {
        const resp = await fetch('/api/saved-courses');
        const data = await resp.json();
        if (!data.length) { el.innerHTML='<div class="status info">No saved course profiles yet.</div>'; return; }
        let html = '<table><tr><th>Course</th><th>SG:OTT</th><th>SG:APP</th><th>SG:ARG</th><th>SG:Putting</th></tr>';
        for (const c of data) {
            const r = c.ratings || {};
            html += '<tr><td>'+c.name+'</td><td>'+(r.sg_ott||'—')+'</td><td>'+(r.sg_app||'—')+'</td><td>'+(r.sg_arg||'—')+'</td><td>'+(r.sg_putting||'—')+'</td></tr>';
        }
        html += '</table>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error loading courses</div>'; }
}

// ══ RESULTS ══
async function loadTournaments() {
    try {
        const resp = await fetch('/api/tournaments');
        const data = await resp.json();
        const opts = data.map(t=>'<option value="'+t.name+'">'+t.name+(t.course?' ('+t.course+')':'')+'</option>').join('');
        document.querySelectorAll('#resultsTournament, #reviewTournament').forEach(sel => { sel.innerHTML = opts; });
    } catch(e) {}
}

async function submitResults() {
    const tournament = document.getElementById('resultsTournament').value;
    const text = document.getElementById('resultsText').value;
    const status = document.getElementById('resultsStatus');
    if (!tournament || !text.trim()) { status.innerHTML='<div class="status error">Enter tournament and results</div>'; return; }
    const lines = text.trim().split('\\n').filter(l=>l.trim());
    const results = lines.map(l=>{const p=l.split(',').map(s=>s.trim()); return {player:p[0]||'',finish:p[1]||''};}).filter(r=>r.player&&r.finish);
    status.innerHTML='<div class="status loading"><span class="spinner"></span>Saving...</div>';
    try {
        const resp = await fetch('/api/results', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tournament,results})});
        const data = await resp.json();
        if (data.error) { status.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        status.innerHTML='<div class="status success">Saved '+data.results_saved+' results. Scored '+data.picks_scored+' picks: '+data.hits+' hits ('+data.hit_rate+')</div>';
    } catch(e) { status.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

// ══ DASHBOARD ══
async function loadDashboard() {
    const el = document.getElementById('dashboardContent');
    try {
        const [dashResp, calResp] = await Promise.all([fetch('/api/dashboard'), fetch('/api/calibration')]);
        const data = await dashResp.json();
        const cal = await calResp.json();
        renderDashboard(data, cal, el);
    } catch(e) { el.innerHTML='<div class="status error">Error loading dashboard</div>'; }
}

function renderDashboard(data, cal, el) {
    const a = data.analysis || {};
    let html = '<h2>Performance</h2><div class="stats-grid">';
    html += '<div class="stat-box"><div class="number">'+(a.total_picks||0)+'</div><div class="label">Total Picks</div></div>';
    html += '<div class="stat-box"><div class="number">'+(a.total_hits||0)+'</div><div class="label">Hits</div></div>';
    html += '<div class="stat-box"><div class="number">'+(a.total_picks?(a.hit_rate*100).toFixed(1)+'%':'—')+'</div><div class="label">Hit Rate</div></div>';
    html += '<div class="stat-box"><div class="number">'+(data.tournaments||[]).length+'</div><div class="label">Tournaments</div></div>';
    html += '</div>';

    // Calibration & ROI
    if (cal && cal.roi) {
        html += '<h2>ROI & Calibration</h2><div class="stats-grid">';
        html += '<div class="stat-box"><div class="number" style="color:'+(cal.roi.roi_pct>=0?'#4ade80':'#ef4444')+'">'+cal.roi.roi_pct+'%</div><div class="label">ROI</div></div>';
        html += '<div class="stat-box"><div class="number">'+(cal.roi.total_profit>=0?'+':'')+cal.roi.total_profit+'</div><div class="label">Profit (units)</div></div>';
        html += '<div class="stat-box"><div class="number">'+cal.roi.total_bets+'</div><div class="label">Value Bets</div></div>';
        if (cal.brier_score) html += '<div class="stat-box"><div class="number">'+cal.brier_score.toFixed(4)+'</div><div class="label">Brier Score</div></div>';
        html += '</div>';

        if (cal.model_comparison) {
            const mc = cal.model_comparison;
            html += '<h3>Model Comparison (Brier Score - lower is better)</h3><div class="stats-grid">';
            html += '<div class="stat-box"><div class="number">'+mc.model_brier.toFixed(4)+'</div><div class="label">Our Model</div></div>';
            html += '<div class="stat-box"><div class="number">'+mc.dg_brier.toFixed(4)+'</div><div class="label">Data Golf</div></div>';
            html += '<div class="stat-box"><div class="number">'+mc.market_brier.toFixed(4)+'</div><div class="label">Market</div></div>';
            html += '</div>';
        }

        if (cal.calibration && cal.calibration.length) {
            html += '<h3>Calibration Curve</h3><table><tr><th>Predicted Range</th><th>Count</th><th>Predicted Avg</th><th>Actual Rate</th><th>Gap</th></tr>';
            for (const b of cal.calibration) {
                const gapColor = Math.abs(b.gap) < 0.03 ? '#4ade80' : '#fbbf24';
                html += '<tr><td>'+b.bucket+'</td><td class="num">'+b.count+'</td><td class="num">'+(b.predicted_avg*100).toFixed(1)+'%</td><td class="num">'+(b.actual_rate*100).toFixed(1)+'%</td><td class="num" style="color:'+gapColor+'">'+(b.gap>0?'+':'')+(b.gap*100).toFixed(1)+'%</td></tr>';
            }
            html += '</table>';
        }
    }

    // Insights
    const insights = a.insights || [];
    if (insights.length) {
        html += '<h2>Model Insights</h2><div class="card-section">';
        for (const ins of insights) html += '<div class="pick" style="padding:5px 0;"><span style="color:#4ade80;margin-right:8px;">→</span>'+ins+'</div>';
        html += '</div>';
    }

    // By bet type
    if (a.by_bet_type && Object.keys(a.by_bet_type).length) {
        html += '<h2>By Bet Type</h2><table><tr><th>Type</th><th>Picks</th><th>Hits</th><th>Rate</th></tr>';
        for (const [bt,s] of Object.entries(a.by_bet_type)) html += '<tr><td>'+bt+'</td><td class="num">'+s.picks+'</td><td class="num">'+s.hits+'</td><td class="num">'+(s.hit_rate*100).toFixed(1)+'%</td></tr>';
        html += '</table>';
    }

    // Weights
    const w = data.weights || {};
    html += '<h2>Current Weights</h2><div class="stats-grid">';
    html += '<div class="stat-box"><div class="number">'+((w.course_fit||0.4)*100).toFixed(0)+'%</div><div class="label">Course Fit</div></div>';
    html += '<div class="stat-box"><div class="number">'+((w.form||0.4)*100).toFixed(0)+'%</div><div class="label">Form</div></div>';
    html += '<div class="stat-box"><div class="number">'+((w.momentum||0.2)*100).toFixed(0)+'%</div><div class="label">Momentum</div></div>';
    html += '</div>';
    html += '<div style="margin-top:15px;"><button class="secondary" onclick="doRetune()">Retune Weights</button> <span id="retuneStatus" style="margin-left:10px;font-size:0.85em;"></span></div>';

    // Tournaments
    html += '<h2>Tournaments</h2><table><tr><th>Name</th><th>Course</th><th>Picks</th><th>Results</th><th>Hits</th></tr>';
    for (const t of (data.tournaments||[])) html += '<tr><td>'+t.name+'</td><td>'+(t.course||'—')+'</td><td class="num">'+t.picks+'</td><td class="num">'+t.results+'</td><td class="num">'+t.hits+'/'+t.outcomes+'</td></tr>';
    html += '</table>';

    el.innerHTML = html;
}

async function doRetune() {
    const el = document.getElementById('retuneStatus');
    el.innerHTML = '<span class="spinner"></span>Retuning...';
    try {
        const resp = await fetch('/api/retune', {method:'POST'});
        const data = await resp.json();
        if (data.message) el.innerHTML = data.message;
        else if (data.saved) { el.innerHTML='<span style="color:#4ade80;">Weights updated!</span>'; loadDashboard(); }
        else el.innerHTML = 'Dry run complete.';
    } catch(e) { el.innerHTML='<span style="color:#ef4444;">Error</span>'; }
}

</script>
</body>
</html>"""


if __name__ == "__main__":
    init_db()
    print("\\n  Golf Betting Model — Web UI")
    print("  Open in browser: http://localhost:8000\\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
