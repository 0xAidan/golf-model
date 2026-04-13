#!/usr/bin/env python3
"""
Golf Betting Model — Local Web UI

Run:  python3 app.py
Open: http://localhost:8000
"""

import os
import sys
import json
import re
import asyncio
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if present (for API keys)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; keys must be in environment

from fastapi import FastAPI, UploadFile, File, Form, Request, Query
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
from src.scoring import determine_outcome

import pandas as pd
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    from src.autoresearch_settings import get_settings
    from backtester.dashboard_runtime import start_live_refresh, stop_live_refresh

    settings = get_settings().get("live_refresh", {})
    embedded_autostart_enabled = os.environ.get("LIVE_REFRESH_EMBEDDED_AUTOSTART", "1").strip().lower() not in {
        "0", "false", "off", "no"
    }
    if embedded_autostart_enabled and settings.get("enabled") and settings.get("autostart"):
        start_live_refresh(tour=str(settings.get("tour", "pga")))
    try:
        yield
    finally:
        stop_live_refresh()


app = FastAPI(title="Golf Betting Model", lifespan=_lifespan)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
FRONTEND_DIST_INDEX = FRONTEND_DIST_DIR / "index.html"
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
if (FRONTEND_DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="frontend-assets")

from src.routes.research import router as research_router
from src.routes.model_registry import router as model_registry_router

app.include_router(research_router)
app.include_router(model_registry_router)

# Store last analysis in memory for the card page
_last_analysis = {}

CSV_DIR = os.path.join(os.path.dirname(__file__), "data", "csvs")
os.makedirs(CSV_DIR, exist_ok=True)
SIMPLE_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "backtests")
os.makedirs(SIMPLE_OUTPUT_DIR, exist_ok=True)
SIMPLE_AUTORESEARCH_SCOPE = "global"
SIMPLE_AUTORESEARCH_INTERVAL_SECONDS = 300
SIMPLE_AUTORESEARCH_TRIALS_PER_CYCLE = 3
SIMPLE_AUTORESEARCH_OBJECTIVE = "weighted_roi_pct"
SIMPLE_AUTORESEARCH_STUDY_NAME = "golf_scalar_simple"


def _latest_output_file(*, subdir: str = "", suffix: str = ".md") -> str | None:
    base_dir = os.path.join(os.path.dirname(__file__), "output", subdir) if subdir else os.path.join(os.path.dirname(__file__), "output")
    if not os.path.isdir(base_dir):
        return None
    candidates = [
        os.path.join(base_dir, name)
        for name in os.listdir(base_dir)
        if name.endswith(suffix)
    ]
    if not candidates:
        return None
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _output_dir_absolute():
    """Canonical output dir for path checks."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "output"))


def _relative_output_path(path: str) -> str:
    rel = os.path.relpath(path, _output_dir_absolute()).replace("\\", "/")
    return f"output/{rel}" if rel != "." else "output"


def _read_dossier_content(artifact_markdown_path: str | None) -> str | None:
    if not artifact_markdown_path:
        return None
    try:
        path = Path(artifact_markdown_path)
        if not path.is_absolute():
            path = Path(os.path.dirname(__file__)) / artifact_markdown_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _extract_roi_metrics_from_dossier_file(artifact_markdown_path: str | None) -> tuple[float | None, float | None]:
    """Best-effort extraction of candidate and baseline ROI from markdown dossier."""
    content = _read_dossier_content(artifact_markdown_path)
    if not content:
        return (None, None)
    try:
        candidate_match = re.search(r"-\s+Weighted ROI:\s*([-\d.]+)", content)
        baseline_match = re.search(r"-\s+Baseline Weighted ROI:\s*([-\d.]+)", content)
        candidate_roi = float(candidate_match.group(1)) if candidate_match else None
        baseline_roi = float(baseline_match.group(1)) if baseline_match else None
        return (candidate_roi, baseline_roi)
    except Exception:
        return (None, None)


def _extract_baseline_summary_from_dossier(artifact_markdown_path: str | None) -> dict:
    """Extract full baseline metrics dict from dossier markdown."""
    content = _read_dossier_content(artifact_markdown_path)
    if not content:
        return {}
    result = {}
    patterns = {
        "weighted_roi_pct": r"-\s+Baseline Weighted ROI:\s*([-\d.]+)",
        "unweighted_roi_pct": r"-\s+Baseline Unweighted ROI:\s*([-\d.]+)",
        "weighted_clv_avg": r"-\s+Baseline Weighted CLV:\s*([-\d.]+)",
        "weighted_calibration_error": r"-\s+Baseline Weighted Calibration Error:\s*([-\d.]+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, content)
        if m:
            try:
                result[key] = float(m.group(1))
            except ValueError:
                pass
    return result


def _safe_output_path(relative_path: str) -> str | None:
    if not relative_path or not relative_path.startswith("output/"):
        return None
    output_root = Path(_output_dir_absolute()).resolve()
    rel = relative_path[len("output/"):]
    candidate = (output_root / rel).resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError:
        return None
    return str(candidate)


def _list_output_files(output_type: str, limit: int = 20) -> list[dict]:
    subdirs = {"prediction": "", "backtest": "backtests", "research": "research"}
    if output_type not in subdirs:
        raise ValueError("Invalid output type")
    base_dir = os.path.join(_output_dir_absolute(), subdirs[output_type]) if subdirs[output_type] else _output_dir_absolute()
    if not os.path.isdir(base_dir):
        return []
    files = []
    for name in os.listdir(base_dir):
        if not name.endswith(".md"):
            continue
        full_path = os.path.join(base_dir, name)
        if os.path.isfile(full_path):
            files.append(
                {
                    "path": _relative_output_path(full_path),
                    "label": name,
                    "mtime": os.path.getmtime(full_path),
                }
            )
    files.sort(key=lambda item: item["mtime"], reverse=True)
    return files[:limit]


def _read_output_content(relative_path: str) -> str:
    safe_path = _safe_output_path(relative_path)
    if not safe_path or not os.path.exists(safe_path):
        return ""
    with open(safe_path, "r", encoding="utf-8") as handle:
        return handle.read()


def _extract_markdown_section(content: str, heading: str) -> str:
    match = re.search(rf"## {re.escape(heading)}\n(.*?)(?:\n## |\Z)", content, re.DOTALL)
    return match.group(1).strip() if match else ""


def _summarize_prediction_output(content: str) -> dict:
    event = ""
    top_picks = []
    confidence = ""
    value_angle = ""
    for line in content.splitlines():
        if line.startswith("# "):
            event = line[2:].replace(" — Betting Card", "").strip()
        if line.startswith("**AI Analysis:**"):
            confidence = line.replace("**AI Analysis:**", "").strip()
        if line.startswith("| **") and len(top_picks) < 3:
            parts = [part.strip() for part in line.split("|") if part.strip()]
            if len(parts) >= 5:
                top_picks.append(f"{parts[0].replace('**', '')} {parts[1]} at {parts[2]} ({parts[3]} EV)")
        if line.startswith("- **VALUE**") and not value_angle:
            value_angle = re.sub(r"^- \*\*VALUE\*\*\s*", "", line).strip()
    return {
        "event": event or "Latest prediction",
        "top_picks": top_picks,
        "strongest_value_angle": value_angle or "No strong value angle surfaced.",
        "confidence_note": confidence or "AI confidence unavailable.",
    }


def _summarize_backtest_output(content: str) -> dict:
    candidate = re.search(r"We tested `([^`]+)` against the current baseline `([^`]+)`", content)
    verdict = re.search(r"\*\*Verdict: ([^*]+)\.\*\*", content)
    candidate_roi = re.search(r"- Candidate weighted ROI: ([^\n]+)", content)
    baseline_roi = re.search(r"- Baseline weighted ROI: ([^\n]+)", content)
    clv_delta = re.search(r"- CLV delta: ([^\n]+)", content)
    guardrail = re.search(r"- Passed: ([^\n]+)", content)
    recommendation = re.search(r"## Recommendation\n(.+)", content, re.DOTALL)
    return {
        "candidate_tested": candidate.group(1) if candidate else "Unknown candidate",
        "baseline_name": candidate.group(2) if candidate else "Unknown baseline",
        "verdict": verdict.group(1).strip() if verdict else "No verdict found",
        "candidate_roi": candidate_roi.group(1).strip() if candidate_roi else "n/a",
        "baseline_roi": baseline_roi.group(1).strip() if baseline_roi else "n/a",
        "clv_delta": clv_delta.group(1).strip() if clv_delta else "n/a",
        "guardrail_result": guardrail.group(1).strip() if guardrail else "n/a",
        "recommended_next_action": recommendation.group(1).strip() if recommendation else "Review full backtest report.",
    }


def _summarize_research_output(content: str) -> dict:
    title = re.search(r"# (?:Autoresearch Run: )?(.+)", content)
    decision = re.search(r"- Decision: ([^\n]+)", content)
    why = re.search(r"- Why: ([^\n]+)", content)
    hypothesis_section = _extract_markdown_section(content, "Hypothesis")
    roi_delta = re.search(r"- ROI Delta: ([^\n]+)", content)
    return {
        "candidate_title": title.group(1).strip() if title else "Latest research run",
        "why_it_was_tested": hypothesis_section.splitlines()[0] if hypothesis_section else "See full report for the tested idea.",
        "did_it_beat_champion": "yes" if decision and decision.group(1).strip() == "kept" else "no",
        "decision": decision.group(1).strip() if decision else "unknown",
        "why": why.group(1).strip() if why else (f"ROI delta: {roi_delta.group(1).strip()}" if roi_delta else "No plain-English reason stored."),
    }


def _summarize_output(output_type: str, content: str) -> dict:
    if output_type == "prediction":
        return _summarize_prediction_output(content)
    if output_type == "backtest":
        return _summarize_backtest_output(content)
    if output_type == "research":
        return _summarize_research_output(content)
    return {}


def _latest_output_summary(output_type: str) -> dict | None:
    files = _list_output_files(output_type, limit=1)
    if not files:
        return None
    path = files[0]["path"]
    content = _read_output_content(path)
    return {
        "path": path,
        "label": files[0]["label"],
        "summary": _summarize_output(output_type, content),
    }


def _latest_completed_event_summary() -> dict | None:
    from scripts.grade_tournament import find_latest_completed_event

    return find_latest_completed_event()


def _latest_output_artifact(output_type: str) -> dict | None:
    subdirs = {"prediction": "", "backtest": "backtests", "research": "research"}
    path = _latest_output_file(subdir=subdirs[output_type], suffix=".md")
    if not path:
        return None
    return {
        "type": output_type,
        "path": _relative_output_path(path),
        "summary": _summarize_output(output_type, _read_output_content(_relative_output_path(path))),
    }


def _latest_graded_tournament_summary() -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
            t.id,
            t.name,
            t.course,
            t.year,
            t.event_id,
            COUNT(DISTINCT r.id) AS results_count,
            COUNT(DISTINCT p.id) AS picks_count,
            COUNT(DISTINCT po.id) AS graded_pick_count,
            COALESCE(SUM(po.hit), 0) AS hits,
            ROUND(COALESCE(SUM(po.profit), 0), 2) AS total_profit,
            MAX(po.entered_at) AS last_graded_at
        FROM tournaments t
        JOIN results r ON r.tournament_id = t.id
        LEFT JOIN picks p ON p.tournament_id = t.id
        LEFT JOIN pick_outcomes po ON po.pick_id = p.id
        GROUP BY t.id, t.name, t.course, t.year, t.event_id
        ORDER BY COALESCE(MAX(po.entered_at), MAX(r.entered_at)) DESC, t.id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@app.get("/api/output/latest")
async def get_latest_output_content(type: str = "backtest"):
    """
    Return the latest output file content by type.
    type: 'prediction' | 'backtest' | 'research'
    Safe: only serves files under output/.
    """
    allowed = {"prediction", "backtest", "research"}
    if type not in allowed:
        return {"error": f"type must be one of: {', '.join(sorted(allowed))}"}
    subdirs = {"prediction": "", "backtest": "backtests", "research": "research"}
    path = _latest_output_file(subdir=subdirs[type], suffix=".md")
    if not path:
        return {"path": None, "content": None, "not_found": True}
    path_abs = os.path.abspath(path)
    output_abs = _output_dir_absolute()
    if not path_abs.startswith(output_abs):
        return {"error": "Invalid path"}
    try:
        with open(path_abs, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return {"path": path, "content": None, "error": str(e)}
    # Return path relative to project root for display
    rel_path = os.path.relpath(path_abs, os.path.dirname(__file__))
    return {"path": rel_path, "content": content, "not_found": False}


@app.get("/api/output/list")
async def get_output_list(type: str = "prediction", limit: int = 20):
    """List readable markdown artifacts by output type."""
    try:
        files = _list_output_files(type, limit=limit)
    except ValueError:
        return JSONResponse({"error": "Invalid output type"}, status_code=400)
    return {"files": files}


@app.get("/api/output/content")
async def get_output_content(path: str):
    """Return markdown content for one artifact under output/."""
    safe_path = _safe_output_path(path)
    if not safe_path:
        return JSONResponse({"error": "Invalid output path"}, status_code=400)
    if not os.path.exists(safe_path):
        return JSONResponse({"error": "Output file not found"}, status_code=404)
    with open(safe_path, "r", encoding="utf-8") as handle:
        return {"path": path, "content": handle.read()}


@app.get("/api/output/latest-summaries")
async def get_latest_output_summaries():
    """Return the latest human-readable summary for each major artifact type."""
    return {
        "prediction": _latest_output_summary("prediction"),
        "backtest": _latest_output_summary("backtest"),
        "research": _latest_output_summary("research"),
    }


@app.get("/api/events/latest-completed")
async def get_latest_completed_event():
    """Return the most recently completed event for grading defaults."""
    event = _latest_completed_event_summary()
    if not event:
        return JSONResponse({"error": "No completed event found"}, status_code=404)
    return event


@app.get("/api/events/schedule")
async def get_events_schedule(tour: str = "pga", upcoming_only: bool = True):
    """Return selectable schedule events for a tour."""
    from src.datagolf import get_schedule_events

    return {"events": get_schedule_events(tour=tour, upcoming_only=upcoming_only)}


@app.get("/api/grading/history")
async def get_grading_history(limit: int = 20):
    """Return durable grading history from stored tournaments, results, and pick outcomes."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            t.id,
            t.name,
            t.course,
            t.year,
            t.event_id,
            COUNT(DISTINCT r.id) AS results_count,
            COUNT(DISTINCT p.id) AS picks_count,
            COUNT(DISTINCT po.id) AS graded_pick_count,
            COALESCE(SUM(po.hit), 0) AS hits,
            ROUND(COALESCE(SUM(po.profit), 0), 2) AS total_profit,
            MAX(po.entered_at) AS last_graded_at
        FROM tournaments t
        JOIN results r ON r.tournament_id = t.id
        LEFT JOIN picks p ON p.tournament_id = t.id
        LEFT JOIN pick_outcomes po ON po.pick_id = p.id
        GROUP BY t.id, t.name, t.course, t.year, t.event_id
        ORDER BY COALESCE(MAX(po.entered_at), MAX(r.entered_at)) DESC, t.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return {"tournaments": [dict(row) for row in rows]}


@app.get("/api/track-record")
async def get_track_record(limit: int = 20):
    """Return graded event history with individual pick results for the track record page."""
    conn = get_conn()
    events = conn.execute(
        """
        SELECT
            t.id, t.name, t.course, t.year, t.event_id,
            COUNT(DISTINCT po.id) AS graded_pick_count,
            COALESCE(SUM(po.hit), 0) AS hits,
            COALESCE(SUM(CASE WHEN po.hit = 1 THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(SUM(CASE WHEN po.hit = 0 AND po.profit = 0 THEN 1 ELSE 0 END), 0) AS pushes,
            COALESCE(SUM(CASE WHEN po.hit = 0 AND po.profit < 0 THEN 1 ELSE 0 END), 0) AS losses,
            ROUND(COALESCE(SUM(po.profit), 0), 2) AS total_profit,
            MAX(po.entered_at) AS last_graded_at
        FROM tournaments t
        JOIN pick_outcomes po ON po.pick_id IN (SELECT id FROM picks WHERE tournament_id = t.id)
        JOIN picks p ON p.id = po.pick_id
        GROUP BY t.id
        ORDER BY MAX(po.entered_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    result = []
    for event in events:
        picks = conn.execute(
            """
            SELECT
                p.player_display, p.opponent_display, p.market_odds,
                p.bet_type, po.hit, ROUND(po.profit, 2) AS profit
            FROM picks p
            JOIN pick_outcomes po ON po.pick_id = p.id
            WHERE p.tournament_id = ?
            ORDER BY po.entered_at
            """,
            (event["id"],),
        ).fetchall()
        result.append({
            **dict(event),
            "picks": [dict(p) for p in picks],
        })
    conn.close()
    return {"events": result}


@app.get("/api/players/{player_key}/profile")
async def get_player_profile(player_key: str, tournament_id: int, course_num: int | None = None):
    """Return deep profile data for one player in the current tournament context."""
    from src import db

    metrics = db.get_player_metrics(tournament_id, player_key)
    recent_rounds = db.get_player_recent_rounds_by_key(player_key, limit=24)

    metrics_by_category: dict[str, dict[str, float | str | None]] = {}
    for metric in metrics:
        category = metric.get("metric_category") or "other"
        bucket = metrics_by_category.setdefault(category, {})
        bucket[metric.get("metric_name") or "value"] = metric.get("metric_value", metric.get("metric_text"))

    dg_id = recent_rounds[0].get("dg_id") if recent_rounds else None
    course_history = []
    if dg_id and course_num is not None:
        course_history = db.get_player_course_rounds(int(dg_id), course_num)

    conn = get_conn()
    linked_bets = conn.execute(
        """
        SELECT bet_type, player_display, opponent_display, market_odds, ev, confidence, reasoning
        FROM picks
        WHERE tournament_id = ?
          AND (player_key = ? OR opponent_key = ?)
        ORDER BY ev DESC, id DESC
        """,
        (tournament_id, player_key, player_key),
    ).fetchall()
    conn.close()

    player_display = None
    for metric in metrics:
        if metric.get("player_display"):
            player_display = metric["player_display"]
            break
    if not player_display and recent_rounds:
        player_display = recent_rounds[0].get("player_name")
    if not player_display:
        player_display = " ".join(part.capitalize() for part in player_key.split("_") if part)

    return {
        "player_key": player_key,
        "player_display": player_display,
        "current_metrics": metrics_by_category,
        "recent_rounds": recent_rounds,
        "course_history": course_history,
        "linked_bets": [dict(row) for row in linked_bets],
    }


# ── API Endpoints ───────────────────────────────────────────────────

def _render_dashboard_html():
    """Load the built React dashboard when present, otherwise fall back to the legacy shell."""
    if FRONTEND_DIST_INDEX.is_file():
        return FRONTEND_DIST_INDEX.read_text(encoding="utf-8")

    path = BASE_DIR / "templates" / "index.html"
    if not path.is_file():
        return _fallback_dashboard_html()
    html = path.read_text(encoding="utf-8")
    css_path = BASE_DIR / "static" / "css" / "main.css"
    js_path = BASE_DIR / "static" / "js" / "app.js"
    css_version = str(int(css_path.stat().st_mtime)) if css_path.is_file() else "0"
    js_version = str(int(js_path.stat().st_mtime)) if js_path.is_file() else "0"
    html = html.replace('/static/css/main.css', f'/static/css/main.css?v={css_version}')
    html = html.replace('/static/js/app.js', f'/static/js/app.js?v={js_version}')
    return html


def _fallback_dashboard_html():
    """Fallback if template is missing (e.g. in tests)."""
    return SIMPLE_HTML_PAGE


@app.get("/", response_class=HTMLResponse)
async def home():
    return _render_dashboard_html()


@app.get("/legacy", response_class=HTMLResponse)
async def legacy_home():
    return _render_dashboard_html()


@app.get("/legacy-classic", response_class=HTMLResponse)
async def legacy_classic_home():
    return HTML_PAGE


@app.get("/api/tournaments")
async def list_tournaments():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tournaments ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _format_delta(candidate_value, baseline_value, unit=""):
    delta = (candidate_value or 0) - (baseline_value or 0)
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.2f}{unit}"


def _decide_backtest_verdict(summary, baseline_summary, guardrails):
    candidate_roi = summary.get("weighted_roi_pct", 0.0)
    baseline_roi = baseline_summary.get("weighted_roi_pct", 0.0)
    if not guardrails.get("passed", False):
        return "needs review"
    if candidate_roi > baseline_roi:
        return "better than baseline"
    if candidate_roi < baseline_roi:
        return "worse than baseline"
    return "roughly tied with baseline"


def _write_simple_backtest_report(strategy, baseline_strategy, years, evaluation):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = (strategy.name or "backtest").replace(" ", "_").lower()
    path = os.path.join(SIMPLE_OUTPUT_DIR, f"{safe_name}_{timestamp}.md")
    summary = evaluation["summary_metrics"]
    baseline_summary = evaluation["baseline_summary_metrics"]
    guardrails = evaluation["guardrail_results"]
    verdict = _decide_backtest_verdict(summary, baseline_summary, guardrails)
    segment_lines = []
    for segment, metrics in (evaluation.get("segmented_metrics") or {}).items():
        segment_lines.append(
            f"- {segment.title()}: ROI {metrics.get('weighted_roi_pct', 0):.2f}%, "
            f"Events {metrics.get('events_evaluated', 0)}"
        )
    if not segment_lines:
        segment_lines.append("- No segment breakdown available.")

    reasons = guardrails.get("reasons") or []
    recommendation = {
        "better than baseline": "This candidate looks stronger than the current baseline and clears the basic guardrails.",
        "worse than baseline": "Keep the current baseline. This test did not beat it.",
        "roughly tied with baseline": "This looks too close to call. Keep the current baseline until a clearer edge appears.",
        "needs review": "Do not treat this as a winner yet. The guardrails found risks that need review first.",
    }[verdict]

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            f"# Backtest Evaluation: {strategy.name}\n\n"
            f"## What We Tested\n"
            f"We tested `{strategy.name}` against the current baseline `{baseline_strategy.name}` on years {years}.\n\n"
            f"Candidate settings:\n"
            f"- Minimum EV: {strategy.min_ev}\n"
            f"- Stat window: {strategy.stat_window}\n"
            f"- Kelly fraction: {strategy.kelly_fraction}\n\n"
            f"## Synthetic Odds Warning\n"
            f"This report uses synthetic DataGolf-derived historical odds instead of true sportsbook tape. "
            f"Use ROI as research evidence, not as guaranteed real-world profit proof.\n\n"
            f"## Is It Better Than The Baseline?\n"
            f"**Verdict: {verdict}.**\n\n"
            f"- Candidate weighted ROI: {summary.get('weighted_roi_pct', 0):.2f}%\n"
            f"- Baseline weighted ROI: {baseline_summary.get('weighted_roi_pct', 0):.2f}%\n"
            f"- ROI delta: {_format_delta(summary.get('weighted_roi_pct', 0), baseline_summary.get('weighted_roi_pct', 0), '%')}\n"
            f"- Candidate weighted CLV: {summary.get('weighted_clv_avg', 0):.4f}\n"
            f"- Baseline weighted CLV: {baseline_summary.get('weighted_clv_avg', 0):.4f}\n"
            f"- CLV delta: {_format_delta(summary.get('weighted_clv_avg', 0), baseline_summary.get('weighted_clv_avg', 0))}\n"
            f"- Candidate calibration error: {summary.get('weighted_calibration_error', 0):.4f}\n"
            f"- Baseline calibration error: {baseline_summary.get('weighted_calibration_error', 0):.4f}\n"
            f"- Drawdown: {summary.get('max_drawdown_pct', 0):.2f}% vs baseline {baseline_summary.get('max_drawdown_pct', 0):.2f}%\n"
            f"- Events evaluated: {summary.get('events_evaluated', 0)}\n"
            f"- Total bets: {summary.get('total_bets', 0)}\n\n"
            f"## Guardrails\n"
            f"- Passed: {guardrails.get('passed', False)}\n"
            f"- Engine verdict: {guardrails.get('verdict', 'unknown')}\n"
            f"- Reasons: {', '.join(reasons) if reasons else 'none'}\n\n"
            f"## Segment Highlights\n"
            f"{chr(10).join(segment_lines)}\n\n"
            f"## Recommendation\n"
            f"{recommendation}\n"
        )
    return {"path": path, "verdict": verdict}


def _simple_autoresearch_state(status: dict) -> str:
    if status.get("running"):
        return "running"
    if status.get("last_error"):
        return "error"
    if status.get("last_run_finished_at"):
        return "completed"
    return "idle"


def _simple_cycle_in_progress(status: dict) -> bool:
    """True while a walk-forward / Optuna batch is actively running (started_at > last finished)."""
    if not status.get("running"):
        return False
    started = status.get("last_run_started_at")
    if not started:
        return False
    finished = status.get("last_run_finished_at")
    if not finished:
        return True
    return str(started) > str(finished)


def _simple_scalar_trial_summary(trial: dict | None) -> dict | None:
    if not trial:
        return None
    user_attrs = trial.get("user_attrs") or {}
    return {
        "trial_number": trial.get("number"),
        "metric_name": SIMPLE_AUTORESEARCH_OBJECTIVE,
        "metric_value": trial.get("value"),
        "roi_pct": user_attrs.get("weighted_roi_pct"),
        "clv_avg": user_attrs.get("weighted_clv_avg"),
        "blended_score": user_attrs.get("blended_score"),
        "guardrails_passed": bool(user_attrs.get("guardrail_passed")),
        "feasible": bool(user_attrs.get("feasible")),
    }


def _simple_recent_scalar_attempts(study, limit: int = 3) -> list[dict]:
    attempts = []
    complete_trials = [
        trial for trial in getattr(study, "trials", [])
        if trial.state.name == "COMPLETE" and trial.value is not None
    ]
    for trial in sorted(complete_trials, key=lambda item: item.number, reverse=True)[:limit]:
        attempts.append(
            _simple_scalar_trial_summary(
                {
                    "number": trial.number,
                    "value": trial.value,
                    "user_attrs": dict(trial.user_attrs),
                }
            )
        )
    return [attempt for attempt in attempts if attempt]


def _simple_autoresearch_payload(status: dict) -> dict:
    state = _simple_autoresearch_state(status)
    last_result = status.get("last_result") or {}
    scalar_summary = last_result.get("optuna_scalar_summary") or {}
    best_trial = scalar_summary.get("best_promotable_trial") or scalar_summary.get("best_trial")
    recent_trials = scalar_summary.get("recent_trials") or []
    cycle_in_progress = _simple_cycle_in_progress(status)
    if status.get("running"):
        headline = (
            "Running a walk-forward tuning batch (each trial can take several minutes)…"
            if cycle_in_progress
            else "Between batches — next run is scheduled on the timer."
        )
    else:
        headline = "Edge tuner is idle."
    return {
        "mode": "simple_scalar",
        "report_only": True,
        "scope": status.get("scope", SIMPLE_AUTORESEARCH_SCOPE),
        "state": state,
        "is_running": bool(status.get("running")),
        "cycle_in_progress": cycle_in_progress,
        "objective": status.get("scalar_objective") or SIMPLE_AUTORESEARCH_OBJECTIVE,
        "study_name": status.get("optuna_scalar_study_name") or SIMPLE_AUTORESEARCH_STUDY_NAME,
        "interval_seconds": status.get("interval_seconds") or SIMPLE_AUTORESEARCH_INTERVAL_SECONDS,
        "goal": "Testing small matchup-strategy tweaks against the current baseline.",
        "headline": headline,
        "last_run_started_at": status.get("last_run_started_at"),
        "last_run_finished_at": status.get("last_run_finished_at"),
        "error": status.get("last_error"),
        "best_improvement": _simple_scalar_trial_summary(best_trial),
        "recent_attempts": [
            attempt
            for attempt in (_simple_scalar_trial_summary(trial) for trial in recent_trials)
            if attempt
        ],
    }


def _write_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _fetch_table_rows(conn, table_name: str) -> list[dict]:
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [dict(row) for row in rows]


def _table_has_column(conn, table_name: str, column_name: str) -> bool:
    cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(col[1] == column_name for col in cols)


def _archive_active_research_files(output_dir: Path, archive_root: Path) -> list[str]:
    research_dir = output_dir / "research"
    archived_files: list[str] = []
    if not research_dir.exists():
        return archived_files
    files_root = archive_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    for child in list(research_dir.iterdir()):
        if child.name == "archive":
            continue
        destination = files_root / child.name
        if child.is_dir():
            shutil.move(str(child), str(destination))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(child), str(destination))
        archived_files.append(_relative_output_path(str(child)))
    (research_dir / "optuna").mkdir(parents=True, exist_ok=True)
    return archived_files


def _archive_autoresearch_settings_file(archive_root: Path) -> str | None:
    import src.autoresearch_settings as settings_module

    settings_path = Path(settings_module._SETTINGS_FILE)
    if not settings_path.exists():
        settings_module.invalidate_cache()
        return None
    destination = archive_root / "settings" / settings_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(settings_path), str(destination))
    settings_module.invalidate_cache()
    return str(destination)


@app.post("/api/simple/autoresearch/start")
async def simple_autoresearch_start():
    """Start the simple scalar autoresearch loop with safe defaults."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.optimizer_runtime import start_continuous_optimizer

    status = start_continuous_optimizer(
        scope=SIMPLE_AUTORESEARCH_SCOPE,
        interval_seconds=SIMPLE_AUTORESEARCH_INTERVAL_SECONDS,
        engine_mode="optuna_scalar",
        optuna_scalar_study_name=SIMPLE_AUTORESEARCH_STUDY_NAME,
        scalar_objective=SIMPLE_AUTORESEARCH_OBJECTIVE,
        optuna_trials_per_cycle=SIMPLE_AUTORESEARCH_TRIALS_PER_CYCLE,
    )
    return _simple_autoresearch_payload(status)


@app.get("/api/simple/autoresearch/status")
async def simple_autoresearch_status():
    """Return plain-language status for the simple scalar autoresearch loop."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.optimizer_runtime import get_optimizer_status

    return _simple_autoresearch_payload(get_optimizer_status())


@app.post("/api/simple/autoresearch/stop")
async def simple_autoresearch_stop():
    """Stop the simple scalar autoresearch loop."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.optimizer_runtime import stop_continuous_optimizer

    return _simple_autoresearch_payload(stop_continuous_optimizer())


@app.post("/api/simple/autoresearch/run-once")
async def simple_autoresearch_run_once():
    """Run one bounded simple scalar autoresearch batch and summarize the result."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.experiments import get_active_strategy
    from backtester.model_registry import get_live_weekly_model, get_research_champion
    from backtester.optimizer_runtime import record_manual_autoresearch_result
    from backtester.research_cycle import PIT_EVALUATION_YEARS
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import run_scalar_study, study_scalar_summary

    baseline = (
        get_research_champion(SIMPLE_AUTORESEARCH_SCOPE)
        or get_live_weekly_model(SIMPLE_AUTORESEARCH_SCOPE)
        or get_active_strategy(SIMPLE_AUTORESEARCH_SCOPE)
    )
    benchmark_spec = WalkForwardBenchmarkSpec(years=PIT_EVALUATION_YEARS)
    study = run_scalar_study(
        n_trials=SIMPLE_AUTORESEARCH_TRIALS_PER_CYCLE,
        baseline=baseline,
        benchmark_spec=benchmark_spec,
        study_name=SIMPLE_AUTORESEARCH_STUDY_NAME,
        scalar_metric=SIMPLE_AUTORESEARCH_OBJECTIVE,
    )
    summary = study_scalar_summary(study)
    best_trial = summary.get("best_promotable_trial") or summary.get("best_trial")
    record_manual_autoresearch_result(
        {
            "evaluation_mode": "optuna_scalar",
            "scalar_objective": SIMPLE_AUTORESEARCH_OBJECTIVE,
            "optuna_scalar_summary": summary,
        },
        scope=SIMPLE_AUTORESEARCH_SCOPE,
        engine_mode="optuna_scalar",
        scalar_objective=SIMPLE_AUTORESEARCH_OBJECTIVE,
        optuna_scalar_study_name=SIMPLE_AUTORESEARCH_STUDY_NAME,
    )
    return {
        "status": "complete",
        "mode": "simple_scalar",
        "report_only": True,
        "objective": SIMPLE_AUTORESEARCH_OBJECTIVE,
        "goal": "Testing small matchup-strategy tweaks against the current baseline.",
        "study_name": summary.get("study_name"),
        "best_improvement": _simple_scalar_trial_summary(best_trial),
        "recent_attempts": _simple_recent_scalar_attempts(study),
    }


@app.post("/api/simple/upcoming-prediction")
async def run_upcoming_prediction(request: Request):
    """Run the normal upcoming-event prediction flow with simple JSON input."""
    payload = await request.json()

    from src.db import ensure_initialized
    ensure_initialized()
    from src.services.live_snapshot_service import run_snapshot_analysis

    mode = payload.get("mode", "full")
    if mode not in ("full", "matchups-only", "placements-only", "round-matchups"):
        mode = "full"
    result = run_snapshot_analysis(
        tour=payload.get("tour", "pga"),
        tournament_name=payload.get("tournament"),
        course_name=payload.get("course"),
        enable_ai=payload.get("enable_ai", False),
        enable_backfill=payload.get("enable_backfill", False),
        mode=mode,
    )
    if not result.get("output_file") and result.get("card_filepath"):
        result["output_file"] = result["card_filepath"]
    if result.get("card_filepath"):
        result["card_content_path"] = _relative_output_path(result["card_filepath"])
        # Include card markdown in response so frontend can show it without a second request
        card_path_abs = _safe_output_path(result["card_content_path"])
        if not card_path_abs and result["card_filepath"] and os.path.isabs(result["card_filepath"]):
            card_path_abs = result["card_filepath"]
        if card_path_abs and os.path.isfile(card_path_abs):
            try:
                with open(card_path_abs, "r", encoding="utf-8") as f:
                    result["card_content"] = f.read()
            except Exception:
                result["card_content"] = None
        else:
            result["card_content"] = None
    return result


@app.post("/api/grade-tournament")
async def grade_tournament_endpoint(request: Request):
    """Grade a completed tournament using DG results and run learning pipeline."""
    payload = await request.json()

    from src.db import ensure_initialized
    ensure_initialized()

    from scripts.grade_tournament import grade_tournament, find_latest_completed_event

    event_id = payload.get("event_id")
    event_name = payload.get("event_name")
    year = payload.get("year")

    if not event_id:
        info = find_latest_completed_event()
        if info:
            event_id = info["event_id"]
            year = year or info["year"]
            event_name = event_name or info.get("event_name")
        else:
            return {"error": "Could not determine latest event and no event_id provided"}

    if not year:
        from datetime import datetime as _dt
        year = _dt.now().year

    report = grade_tournament(event_id, year, event_name=event_name)
    return report


@app.post("/api/simple/backtest")
async def run_simple_backtest(request: Request):
    """Run a readable backtest report against the active baseline."""
    payload = await request.json()

    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.model_registry import get_live_weekly_model, get_research_champion
    from backtester.strategy import StrategyConfig
    from backtester.weighted_walkforward import evaluate_weighted_walkforward

    strategy = StrategyConfig(name=payload.get("name") or "ui_backtest")
    if payload.get("min_ev") is not None:
        strategy.min_ev = float(payload["min_ev"])
    if payload.get("window") is not None:
        strategy.stat_window = int(payload["window"])

    years = payload.get("years") or [2024, 2025]
    baseline_strategy = get_research_champion("global") or get_live_weekly_model("global") or StrategyConfig(name="current_baseline")
    evaluation = evaluate_weighted_walkforward(
        strategy=strategy,
        baseline_strategy=baseline_strategy,
        years=years,
    )
    report = _write_simple_backtest_report(strategy, baseline_strategy, years, evaluation)
    summary = evaluation["summary_metrics"]

    return {
        "status": "complete",
        "report_path": report["path"],
        "events_simulated": summary.get("events_evaluated", 0),
        "total_bets": summary.get("total_bets", 0),
        "roi_pct": summary.get("weighted_roi_pct", 0.0),
        "clv_avg": summary.get("weighted_clv_avg", 0.0),
        "calibration_error": summary.get("weighted_calibration_error", 0.0),
        "max_drawdown_pct": summary.get("max_drawdown_pct", 0.0),
        "verdict": report["verdict"],
        "baseline_strategy": baseline_strategy.name,
    }


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


@app.get("/api/dashboard/state")
async def get_dashboard_state(scope: str = "global"):
    """Return actionable dashboard state for the simple UI."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.model_registry import (
        get_live_weekly_model,
        get_live_weekly_model_record,
        get_research_champion,
        get_research_champion_record,
    )
    from backtester.optimizer_runtime import get_optimizer_status
    from src.ai_brain import get_ai_status
    from src.datagolf import get_datagolf_throttle_status

    return {
        "ai_status": get_ai_status(),
        "effective_live_weekly_model": get_live_weekly_model(scope).__dict__,
        "effective_research_champion": get_research_champion(scope).__dict__,
        "live_weekly_model_record": get_live_weekly_model_record(scope),
        "research_champion_record": get_research_champion_record(scope),
        "baseline_provenance": {
            "strategy_source": "live" if get_live_weekly_model_record(scope) else "research_champion",
            "live_record_id": (get_live_weekly_model_record(scope) or {}).get("id"),
            "research_record_id": (get_research_champion_record(scope) or {}).get("id"),
            "live_strategy_name": get_live_weekly_model(scope).__dict__.get("name"),
        },
        "latest_outputs": {
            "prediction_markdown_path": _latest_output_file(subdir="", suffix=".md"),
            "backtest_markdown_path": _latest_output_file(subdir="backtests", suffix=".md"),
            "research_markdown_path": _latest_output_file(subdir="research", suffix=".md"),
        },
        "latest_prediction_artifact": _latest_output_artifact("prediction"),
        "latest_backtest_artifact": _latest_output_artifact("backtest"),
        "latest_research_artifact": _latest_output_artifact("research"),
        "latest_completed_event": _latest_completed_event_summary(),
        "latest_graded_tournament": _latest_graded_tournament_summary(),
        "optimizer": get_optimizer_status(),
        "autoresearch": {
            "running": get_optimizer_status().get("running", False),
            "run_count": get_optimizer_status().get("run_count", 0),
            "last_started_at": get_optimizer_status().get("last_run_started_at"),
            "last_finished_at": get_optimizer_status().get("last_run_finished_at"),
            "last_result": get_optimizer_status().get("last_result"),
            "last_error": get_optimizer_status().get("last_error"),
            "scope": get_optimizer_status().get("scope", scope),
        },
        "datagolf": get_datagolf_throttle_status(),
    }


@app.post("/api/live-refresh/start")
async def start_live_refresh_runtime(request: Request):
    """Start always-on live refresh runtime."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.dashboard_runtime import start_live_refresh
    from src.autoresearch_settings import get_settings, set_settings

    if os.environ.get("LIVE_REFRESH_ENABLED", "1").strip().lower() in {"0", "false", "off", "no"}:
        return JSONResponse({"error": "LIVE_REFRESH_ENABLED is disabled"}, status_code=403)

    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    current = get_settings()
    live_cfg = dict(current.get("live_refresh") or {})
    if isinstance(payload.get("live_refresh"), dict):
        live_cfg.update(payload["live_refresh"])
    if payload.get("tour"):
        requested_tour = str(payload["tour"]).strip().lower()
        live_cfg["tour"] = requested_tour if requested_tour in {"pga", "euro", "kft", "alt"} else "pga"
    live_cfg["enabled"] = True
    set_settings({"live_refresh": live_cfg})
    status = start_live_refresh(tour=live_cfg.get("tour", "pga"))
    return {"ok": True, "status": status}


@app.post("/api/live-refresh/stop")
async def stop_live_refresh_runtime():
    """Stop always-on live refresh runtime."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.dashboard_runtime import stop_live_refresh
    from src.autoresearch_settings import get_settings, set_settings

    cfg = dict((get_settings().get("live_refresh") or {}))
    cfg["enabled"] = False
    set_settings({"live_refresh": cfg})
    status = stop_live_refresh()
    return {"ok": True, "status": status}


@app.get("/api/live-refresh/status")
async def get_live_refresh_runtime_status():
    """Return always-on runtime status and live refresh settings."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.dashboard_runtime import get_live_refresh_status
    from src.autoresearch_settings import get_settings

    return {
        "status": get_live_refresh_status(),
        "settings": (get_settings().get("live_refresh") or {}),
    }


@app.get("/api/live-refresh/snapshot")
async def get_live_refresh_snapshot():
    """Return latest always-on snapshot for Live/Upcoming dashboard tabs."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.dashboard_runtime import read_snapshot

    snapshot = read_snapshot()
    if not snapshot:
        return {
            "ok": False,
            "snapshot": None,
            "stale_reason": "No snapshot generated yet. Start live refresh runtime.",
        }
    generated_at = snapshot.get("generated_at")
    age_seconds = None
    if generated_at:
        try:
            age_seconds = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(generated_at)).total_seconds()))
        except ValueError:
            age_seconds = None
    # Trust guard: never serve stale snapshot payloads as current rankings.
    # Returning stale rows can leak invalid players from prior events.
    if age_seconds is not None and age_seconds > 900:
        return {
            "ok": False,
            "snapshot": None,
            "generated_at": generated_at,
            "age_seconds": age_seconds,
            "stale_reason": "Snapshot is stale (>15 minutes); waiting for a fresh recompute.",
            "fallback_reason": None,
        }
    return {
        "ok": True,
        "snapshot": snapshot,
        "generated_at": generated_at,
        "age_seconds": age_seconds,
        "stale_reason": (
            "Live snapshot indicates a degraded pipeline state."
            if (
                (snapshot.get("live_tournament", {}).get("diagnostics", {}).get("state") == "pipeline_error")
                or (snapshot.get("upcoming_tournament", {}).get("diagnostics", {}).get("state") == "pipeline_error")
            )
            else None
        ),
        "fallback_reason": (
            "Showing fallback rankings source."
            if snapshot.get("live_tournament", {}).get("ranking_source") in {"current_event_model_fallback", "live_fallback"}
            else None
        ),
    }


@app.get("/api/optimizer/status")
async def get_optimizer_runtime_status():
    """Return continuous optimizer status plus DataGolf throttle health."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.optimizer_runtime import get_optimizer_status
    from src.datagolf import get_datagolf_throttle_status

    return {
        "optimizer": get_optimizer_status(),
        "datagolf": get_datagolf_throttle_status(),
    }


@app.post("/api/optimizer/start")
async def start_optimizer_runtime(request: Request):
    """Start the continuous optimizer loop."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.optimizer_runtime import start_continuous_optimizer

    payload = await request.json()
    mc = payload.get("max_candidates")
    status = start_continuous_optimizer(
        scope=payload.get("scope", "global"),
        interval_seconds=float(payload.get("interval_seconds", 300)),
        max_candidates=int(mc) if mc is not None else None,
        years=payload.get("years"),
        engine_mode=payload.get("engine_mode"),
        optuna_study_name=payload.get("optuna_study_name"),
        optuna_scalar_study_name=payload.get("optuna_scalar_study_name"),
        scalar_objective=payload.get("scalar_objective"),
        optuna_trials_per_cycle=payload.get("optuna_trials_per_cycle"),
    )
    return {"ok": True, "optimizer": status}


@app.post("/api/optimizer/stop")
async def stop_optimizer_runtime():
    """Stop the continuous optimizer loop."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.optimizer_runtime import stop_continuous_optimizer

    status = stop_continuous_optimizer()
    return {"ok": True, "optimizer": status}


@app.get("/api/autoresearch/settings")
async def get_autoresearch_settings():
    """Return UI-persisted autoresearch settings (e.g. guardrail_mode: strict | loose)."""
    from src.autoresearch_settings import get_settings
    return get_settings()


@app.patch("/api/autoresearch/settings")
async def patch_autoresearch_settings(request: Request):
    """Update autoresearch settings (guardrail_mode, engine_mode, use_theory_engine_llm, optuna_*)."""
    from src.autoresearch_settings import set_settings
    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}
    updated = set_settings(body)
    return updated


@app.get("/api/autoresearch/study")
async def get_autoresearch_study(
    study_name: str | None = Query(None),
    study_kind: str | None = Query("mo"),
):
    """Load persisted Optuna study and return Pareto or scalar summary (read-only)."""
    from src.db import ensure_initialized
    ensure_initialized()
    from src.autoresearch_settings import get_settings
    from backtester.research_cycle import PIT_EVALUATION_YEARS
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import (
        create_or_load_scalar_study,
        create_or_load_study,
        resolve_scalar_study_name,
        study_dashboard_metrics,
        study_scalar_dashboard_metrics,
        study_scalar_summary,
        study_summary,
    )

    settings = get_settings()
    kind = (study_kind or "mo").strip().lower()
    if kind == "scalar":
        scalar_objective = (settings.get("scalar_objective") or "blended_score").strip().lower()
        if scalar_objective not in ("blended_score", "weighted_roi_pct"):
            scalar_objective = "blended_score"
        base_name = (study_name or settings.get("optuna_scalar_study_name") or "golf_scalar_dashboard").strip()[:120]
        name = resolve_scalar_study_name(
            base_name,
            benchmark_spec=WalkForwardBenchmarkSpec(years=PIT_EVALUATION_YEARS),
            scalar_metric=scalar_objective,
        )
    else:
        name = (study_name or settings.get("optuna_study_name") or "golf_mo_dashboard").strip()[:120]
    try:
        if kind == "scalar":
            study = create_or_load_scalar_study(name)
            return {
                "ok": True,
                "study_name": name,
                "study_kind": "scalar",
                "summary": study_scalar_summary(study),
                "dashboard": study_scalar_dashboard_metrics(study),
            }
        study = create_or_load_study(name)
        return {
            "ok": True,
            "study_name": name,
            "study_kind": "mo",
            "summary": study_summary(study),
            "dashboard": study_dashboard_metrics(study),
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.post("/api/autoresearch/optuna/run")
async def post_autoresearch_optuna_run(request: Request):
    """Run N Optuna MO or scalar trials in a worker thread (can take minutes)."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.experiments import get_active_strategy
    from backtester.model_registry import get_live_weekly_model, get_research_champion
    from backtester.research_lab.canonical import WalkForwardBenchmarkSpec
    from backtester.research_lab.mo_study import run_mo_study, run_scalar_study, study_scalar_summary, study_summary
    from src.autoresearch_settings import get_settings

    try:
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    except Exception:
        body = {}
    n_trials = max(1, min(50, int(body.get("n_trials", 5))))
    years = body.get("years")
    if years is None:
        years = [2024, 2025]
    scope = body.get("scope", "global")
    settings = get_settings()
    study_kind = (body.get("study_kind") or "mo").strip().lower()
    if study_kind == "scalar":
        study_name = (body.get("study_name") or settings.get("optuna_scalar_study_name") or "golf_scalar_dashboard").strip()[:120]
        so = (body.get("scalar_objective") or settings.get("scalar_objective") or "blended_score").strip().lower()
        if so not in ("blended_score", "weighted_roi_pct"):
            so = "blended_score"

        def _run_scalar():
            baseline = get_research_champion(scope) or get_live_weekly_model(scope) or get_active_strategy(scope)
            spec = WalkForwardBenchmarkSpec(years=years)
            study = run_scalar_study(
                n_trials=n_trials,
                baseline=baseline,
                benchmark_spec=spec,
                study_name=study_name,
                scalar_metric=so,
            )
            return study_scalar_summary(study)

        summary = await asyncio.to_thread(_run_scalar)
        return {"ok": True, "study_name": study_name, "study_kind": "scalar", "summary": summary}

    study_name = (body.get("study_name") or settings.get("optuna_study_name") or "golf_mo_dashboard").strip()[:120]

    def _run_block():
        baseline = get_research_champion(scope) or get_live_weekly_model(scope) or get_active_strategy(scope)
        spec = WalkForwardBenchmarkSpec(years=years)
        study = run_mo_study(
            n_trials=n_trials,
            baseline=baseline,
            benchmark_spec=spec,
            study_name=study_name,
        )
        return study_summary(study)

    summary = await asyncio.to_thread(_run_block)
    return {"ok": True, "study_name": study_name, "study_kind": "mo", "summary": summary}


@app.get("/api/autoresearch/status")
async def get_autoresearch_status():
    """Return autoresearch runtime status using the existing optimizer runtime."""
    from src.db import ensure_initialized
    ensure_initialized()

    from backtester.optimizer_runtime import get_optimizer_status

    status = get_optimizer_status()
    running = status.get("running", False)
    last_error = status.get("last_error")
    if running:
        state = "running"
    elif last_error:
        state = "error"
    elif status.get("run_count", 0) > 0:
        state = "completed"
    else:
        state = "idle"
    last_result = status.get("last_result") or {}
    evaluation_mode = last_result.get("evaluation_mode")
    winner = last_result.get("winner") or {}
    winner_score = winner.get("blended_score")
    guardrail_failures = 0 if (winner.get("guardrail_results") or {}).get("passed", True) else 1
    if evaluation_mode == "optuna_scalar":
        scalar_summary = last_result.get("optuna_scalar_summary") or {}
        best_promotable_trial = scalar_summary.get("best_promotable_trial") or {}
        best_trial = scalar_summary.get("best_trial") or {}
        if best_promotable_trial:
            winner_score = scalar_summary.get("best_promotable_value")
            guardrail_failures = 0
        elif best_trial:
            winner_score = scalar_summary.get("best_value")
            guardrail_failures = 0 if (best_trial.get("user_attrs") or {}).get("guardrail_passed") else 1
    return {
        "status": {
            "state": state,
            "running": status.get("running", False),
            "run_count": status.get("run_count", 0),
            "last_started_at": status.get("last_run_started_at"),
            "last_finished_at": status.get("last_run_finished_at"),
            "last_result": status.get("last_result"),
            "last_error": status.get("last_error"),
            "scope": status.get("scope", "global"),
            "interval_seconds": status.get("interval_seconds"),
            "best_metric": winner_score,
            "baseline_metric": None,
            "delta_metric": None,
            "guardrail_failures": guardrail_failures,
            "last_updated_at": status.get("last_run_finished_at") or status.get("last_run_started_at"),
            "keep_rate": status.get("keep_rate", 0.0),
            "crash_rate": status.get("crash_rate", 0.0),
            "guardrail_fail_rate": status.get("guardrail_fail_rate", 0.0),
            "at_start_baseline_roi": status.get("at_start_baseline_roi"),
            "at_start_baseline_clv": status.get("at_start_baseline_clv"),
            "engine_mode": status.get("engine_mode", "research_cycle"),
            "optuna_study_name": status.get("optuna_study_name"),
            "optuna_scalar_study_name": status.get("optuna_scalar_study_name"),
            "scalar_objective": status.get("scalar_objective"),
            "optuna_trials_per_cycle": status.get("optuna_trials_per_cycle"),
            "max_candidates": status.get("max_candidates"),
        }
    }


@app.post("/api/autoresearch/start")
async def start_autoresearch_runtime(request: Request):
    """Start the looping autoresearch runtime."""
    return await start_optimizer_runtime(request)


@app.post("/api/autoresearch/stop")
async def stop_autoresearch_runtime():
    """Stop the looping autoresearch runtime."""
    result = await stop_optimizer_runtime()
    optimizer = result.get("optimizer", {})
    return {"status": {
        "running": optimizer.get("running", False),
        "run_count": optimizer.get("run_count", 0),
        "last_error": optimizer.get("last_error"),
    }}


@app.post("/api/autoresearch/run-once")
async def run_autoresearch_once(request: Request):
    """Run one bounded autoresearch cycle."""
    from src.db import ensure_initialized
    ensure_initialized()
    try:
        from backtester.autoresearch_engine import run_cycle as run_autoresearch_cycle
        payload = await request.json() if request.headers.get("content-type") == "application/json" else {}
        kwargs = dict(
            max_candidates=int(payload.get("max_candidates", 3)),
            scope=payload.get("scope", "global"),
            source="manual_autoresearch",
        )
        if payload.get("years") is not None:
            kwargs["years"] = payload["years"]
        result = run_autoresearch_cycle(**kwargs)
        pd = result.get("promotion_decision") or ""
        champion_updated = bool(result.get("research_champion_updated"))
        cycle_ok = champion_updated or pd in (
            "updated_research_champion",
            "updated_iteration_baseline",
        )
        return {
            "state": "completed",
            "decision": "kept" if cycle_ok else ("discarded" if result.get("proposals_evaluated") else "no_op"),
            **result,
        }
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/autoresearch/run-batch")
async def run_autoresearch_batch(request: Request):
    """Run N bounded autoresearch cycles and return aggregated result."""
    from src.db import ensure_initialized
    ensure_initialized()
    from backtester.autoresearch_engine import run_cycle as run_autoresearch_cycle

    payload = await request.json() if request.headers.get("content-type") == "application/json" else {}
    scope = payload.get("scope", "global")
    years = payload.get("years")
    cycles = max(1, int(payload.get("cycles", 3)))
    max_candidates = max(1, int(payload.get("max_candidates", 3)))
    runs = []
    for idx in range(cycles):
        runs.append(
            run_autoresearch_cycle(
                years=years,
                max_candidates=max_candidates,
                scope=scope,
                source="manual_autoresearch_batch",
                seed=42 + idx,
            )
        )
    winners = [r.get("winner") for r in runs if r.get("winner")]
    best_winner = sorted(winners, key=lambda x: x.get("blended_score", -999), reverse=True)[0] if winners else None
    return {
        "status": "complete",
        "state": "completed",
        "scope": scope,
        "cycles": cycles,
        "max_candidates": max_candidates,
        "runs": runs,
        "best_winner": best_winner,
    }


@app.get("/api/autoresearch/runs")
async def get_autoresearch_runs(scope: str = "global", limit: int = 20):
    """Return recent evaluated research proposals shaped for dashboard review."""
    from src.db import ensure_initialized
    ensure_initialized()
    try:
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT id, name, hypothesis, source, scope, status, years_json, theory_metadata_json,
                   summary_metrics_json, guardrail_results_json, artifact_markdown_path,
                   created_at, evaluated_at
            FROM research_proposals
            WHERE scope = ?
              AND status IN ('evaluated', 'approved', 'rejected', 'converted')
            ORDER BY COALESCE(evaluated_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            (scope, limit),
        ).fetchall()
        conn.close()

        runs = []
        for row in rows:
            summary_metrics = json.loads(row["summary_metrics_json"] or "{}")
            guardrails = json.loads(row["guardrail_results_json"] or "{}")
            theory = json.loads(row["theory_metadata_json"] or "{}")
            baseline_summary = guardrails.get("baseline_summary_metrics", {}) or {}
            candidate_roi = summary_metrics.get("weighted_roi_pct")
            baseline_roi = baseline_summary.get("weighted_roi_pct")
            if candidate_roi is None or baseline_roi is None or not baseline_summary.get("weighted_clv_avg"):
                dossier_baseline = _extract_baseline_summary_from_dossier(row["artifact_markdown_path"])
                if dossier_baseline:
                    dossier_candidate_roi, _ = _extract_roi_metrics_from_dossier_file(row["artifact_markdown_path"])
                    if candidate_roi is None and dossier_candidate_roi is not None:
                        summary_metrics["weighted_roi_pct"] = dossier_candidate_roi
                        candidate_roi = dossier_candidate_roi
                    if not baseline_summary.get("weighted_roi_pct") and dossier_baseline.get("weighted_roi_pct"):
                        baseline_summary["weighted_roi_pct"] = dossier_baseline["weighted_roi_pct"]
                        baseline_roi = dossier_baseline["weighted_roi_pct"]
                    if not baseline_summary.get("weighted_clv_avg") and dossier_baseline.get("weighted_clv_avg"):
                        baseline_summary["weighted_clv_avg"] = dossier_baseline["weighted_clv_avg"]
                    for k, v in dossier_baseline.items():
                        if k not in baseline_summary:
                            baseline_summary[k] = v
            roi_delta = None
            if candidate_roi is not None and baseline_roi is not None:
                try:
                    roi_delta = float(candidate_roi) - float(baseline_roi)
                except Exception:
                    roi_delta = None
            status = row["status"]
            blocked_reason = guardrails.get("reasons", []) if isinstance(guardrails, dict) else []
            gr_passed = bool(guardrails.get("passed", False))
            blocked_by_guardrails = not gr_passed
            status_approved = status in {"approved", "converted"}
            promotable = bool(guardrails.get("is_positive_test")) or (
                roi_delta is not None and roi_delta > 0
            )
            # Previously only approved/converted → "kept", so passing evaluated runs looked like failures.
            kept = status_approved or (gr_passed and promotable)
            if blocked_by_guardrails:
                decision = "blocked_by_guardrails"
            elif kept:
                decision = "kept"
            else:
                decision = "discarded"
            runs.append(
                {
                    "id": row["id"],
                    "scope": row["scope"],
                    "candidate_name": row["name"],
                    "display_title": theory.get("title") or row["name"],
                    "baseline_name": "current champion",
                    "hypothesis": row["hypothesis"],
                    "source_type": row["source"],
                    "strategy_source": row["source"],
                    "decision": decision,
                    "kept": kept,
                    "blocked_reason": blocked_reason,
                    "benchmark_years": json.loads(row["years_json"] or "[]"),
                    "benchmark_label": f"Fixed PIT benchmark ({', '.join(str(y) for y in json.loads(row['years_json'] or '[]'))})" if row["years_json"] else "Fixed PIT benchmark",
                    "roi_delta": roi_delta,
                    "clv_delta": (
                        float(summary_metrics.get("weighted_clv_avg", 0.0) or 0.0)
                        - float((guardrails.get("baseline_summary_metrics", {}) or {}).get("weighted_clv_avg", 0.0) or 0.0)
                    ),
                    "guardrail_verdict": guardrails.get("verdict"),
                    "summary_reason": guardrails.get("summary") or ("Approved for follow-up" if kept else "Not promoted from this run."),
                    "what_tested": theory.get("what_tested") or row["hypothesis"],
                    "next_attempt_hint": guardrails.get("next_attempt_hint"),
                    "is_positive_test": bool(guardrails.get("is_positive_test", False)),
                    "artifact_markdown_path": row["artifact_markdown_path"],
                    "summary_metrics": summary_metrics,
                    "baseline_summary_metrics": baseline_summary,
                    "guardrail_results": guardrails,
                    "created_at": row["evaluated_at"] or row["created_at"],
                }
            )
        return {"runs": runs}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc), "runs": []})


# Maximum best candidates to show; we iterate on 1–3 only.
BEST_CANDIDATES_MAX = 3


@app.get("/api/autoresearch/best-candidates")
async def get_autoresearch_best_candidates(scope: str = "global", limit: int = BEST_CANDIDATES_MAX):
    """Return the top 1–3 best evaluated proposals by ROI for dashboard; no stale/long tail."""
    from src.db import ensure_initialized
    ensure_initialized()
    try:
        from backtester.weighted_walkforward import compute_blended_score
        from backtester.strategy import StrategyConfig

        cap = min(max(1, limit), BEST_CANDIDATES_MAX)
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT id, name, hypothesis, source, strategy_config_json,
                   summary_metrics_json, guardrail_results_json, theory_metadata_json,
                   artifact_markdown_path
            FROM research_proposals
            WHERE scope = ?
              AND status IN ('evaluated', 'approved', 'converted')
              AND summary_metrics_json IS NOT NULL
              AND guardrail_results_json IS NOT NULL
            ORDER BY COALESCE(evaluated_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            (scope, 200),
        ).fetchall()
        conn.close()
        # Pool is "most recently evaluated" so newly evaluated (often better) proposals
        # compete for top 3 by ROI; sort below picks best by weighted_roi_pct/clv/score.

        candidates = []
        for row in rows:
            try:
                summary = json.loads(row["summary_metrics_json"] or "{}")
                guardrails = json.loads(row["guardrail_results_json"] or "{}")
                score = compute_blended_score(summary, guardrails)
                theory = json.loads(row["theory_metadata_json"] or "{}")
                why = (theory.get("why_it_may_work") or "").strip()
                hypothesis = (row["hypothesis"] or "").strip()
                strategy_tldr = hypothesis
                if why:
                    strategy_tldr = f"{hypothesis}\n\n{why}" if hypothesis else why
                strategy_tldr = strategy_tldr.strip() or "No description."
                if len(strategy_tldr) > 500:
                    strategy_tldr = strategy_tldr[:497] + "..."
            except Exception:
                continue
            art_path = row["artifact_markdown_path"]
            content_path = (_relative_output_path(art_path) if art_path and (art_path.startswith("/") or (len(art_path) > 1 and art_path[1] == ":")) else art_path) if art_path else None
            baseline_summary = guardrails.get("baseline_summary_metrics", {}) or {}
            if not baseline_summary.get("weighted_roi_pct"):
                baseline_summary = _extract_baseline_summary_from_dossier(art_path) or baseline_summary
            candidates.append({
                "id": row["id"],
                "name": theory.get("title") or row["name"],
                "hypothesis": row["hypothesis"],
                "strategy_tldr": strategy_tldr,
                "what_tested": theory.get("what_tested") or row["hypothesis"],
                "summary_reason": guardrails.get("summary"),
                "next_attempt_hint": guardrails.get("next_attempt_hint"),
                "is_positive_test": bool(guardrails.get("is_positive_test", False)),
                "summary_metrics": summary,
                "baseline_summary_metrics": baseline_summary,
                "guardrail_results": guardrails,
                "blended_score": score,
                "artifact_markdown_path": art_path,
                "artifact_content_path": content_path,
            })

        # Primary sort: best ROI first (highest weighted_roi_pct). Then CLV, then blended_score.
        candidates.sort(
            key=lambda item: (
                item["summary_metrics"].get("weighted_roi_pct", -999),
                item["summary_metrics"].get("weighted_clv_avg", -999),
                item["blended_score"],
            ),
            reverse=True,
        )
        return {"candidates": candidates[:cap]}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc), "candidates": []})


@app.post("/api/autoresearch/reset")
async def reset_autoresearch_state():
    """Archive old research data and clear the active autoresearch lane for a fresh start."""
    from src.db import ensure_initialized
    from backtester.optimizer_runtime import reset_optimizer_state
    from backtester.model_registry import get_live_weekly_model_record, set_live_weekly_model
    from src.strategy_resolution import resolve_runtime_strategy

    ensure_initialized()
    try:
        effective_strategy, strategy_meta = resolve_runtime_strategy("global")
        prediction_lane_preserved = False
        if strategy_meta.get("strategy_source") == "research_champion" and not get_live_weekly_model_record("global"):
            set_live_weekly_model(
                effective_strategy,
                scope="global",
                promoted_by="reset",
                action="reset_preserve_current_prediction_lane",
                notes="Preserved the current prediction strategy before clearing old autoresearch history.",
            )
            prediction_lane_preserved = True

        conn = get_conn()
        output_dir = Path(_output_dir_absolute())
        research_dir = output_dir / "research"
        archive_root = research_dir / "archive" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_root.mkdir(parents=True, exist_ok=False)

        archived_tables = {
            "research_proposals": _fetch_table_rows(conn, "research_proposals"),
            "proposal_reviews": _fetch_table_rows(conn, "proposal_reviews"),
            "research_model_registry": _fetch_table_rows(conn, "research_model_registry"),
        }
        for table_name, rows in archived_tables.items():
            _write_json_file(archive_root / "db" / f"{table_name}.json", rows)

        archived_files = _archive_active_research_files(output_dir, archive_root)
        archived_settings_path = _archive_autoresearch_settings_file(archive_root)

        if _table_has_column(conn, "live_model_registry", "source_research_registry_id"):
            conn.execute("UPDATE live_model_registry SET source_research_registry_id = NULL WHERE source_research_registry_id IS NOT NULL")
        conn.execute("DELETE FROM research_model_registry")
        conn.execute("DELETE FROM proposal_reviews")
        conn.execute("DELETE FROM research_proposals")
        conn.commit()
        conn.close()

        reset_optimizer_state()

        archive_manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "archive_dir": str(archive_root),
            "db_counts": {table_name: len(rows) for table_name, rows in archived_tables.items()},
            "archived_files": archived_files,
            "archived_settings": bool(archived_settings_path),
            "active_prediction_lane_preserved": True,
            "prediction_lane_snapshot_created": prediction_lane_preserved,
        }
        _write_json_file(archive_root / "archive_manifest.json", archive_manifest)
        return {
            "ok": True,
            "archive_dir": _relative_output_path(str(archive_root)),
            "message": "Old research was archived and the active autoresearch process was reset.",
            "archived_counts": archive_manifest["db_counts"],
        }
    except Exception as exc:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"error": str(exc)})


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
    all_results_list = [dict(r) for r in results_rows]
    scored = 0
    hits = 0
    for pick in picks:
        pk = pick["player_key"]
        bt = pick["bet_type"]
        r = result_map.get(pk)
        if not r:
            continue

        # Determine opponent finish for matchups
        opp_finish = None
        if bt == "matchup":
            opp_key = pick.get("opponent_key")
            opp_result = result_map.get(opp_key) if opp_key else None
            opp_finish = opp_result.get("finish_position") if opp_result else None

        outcome = determine_outcome(
            bt,
            r.get("finish_position"),
            r.get("finish_text"),
            r.get("made_cut", 0),
            all_results_list,
            opponent_finish=opp_finish,
        )
        hit = outcome["hit"]

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
    if result is None:
        return JSONResponse(
            {"message": "AI betting decisions disabled. Bet selection is purely quantitative."},
            status_code=200,
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


@app.post("/api/run-service")
async def run_service_analysis(request: Request):
    """Run the full unified pipeline via GolfModelService."""
    from src.services.golf_model_service import GolfModelService

    try:
        data = await request.json()
    except Exception:
        data = {}

    service = GolfModelService(tour=data.get("tour", "pga"))
    result = service.run_analysis(
        tournament_name=data.get("tournament"),
        course_name=data.get("course"),
        event_id=data.get("event_id"),
        course_num=data.get("course_num"),
        enable_ai=data.get("enable_ai", True),
        enable_backfill=data.get("enable_backfill", True),
    )

    # Store results for the card/predictions pages
    global _last_analysis
    if result.get("status") == "complete":
        _last_analysis = {
            "tournament": result.get("event_name", ""),
            "tournament_id": result.get("tournament_id"),
            "course": result.get("course_name", ""),
            "composite": result.get("composite_results", []),
            "value_bets": result.get("value_bets", {}),
            "weights": get_active_weights(),
            "timestamp": datetime.now().isoformat(),
        }

    return result


@app.get("/api/ai-memories")
async def get_memories(topic: str = None):
    """Get AI brain memories, optionally filtered by topic."""
    from src.db import get_ai_memories, get_all_ai_memory_topics
    topics = [topic] if topic else None
    memories = get_ai_memories(topics=topics)
    all_topics = get_all_ai_memory_topics()
    return {"memories": memories, "topics": all_topics}


# ── Backtester & Experiments Endpoints ─────────────────────────────

@app.get("/api/experiments")
async def list_experiments():
    """Get experiment leaderboard."""
    try:
        from backtester.experiments import get_experiment_leaderboard
        return {"experiments": get_experiment_leaderboard(limit=50)}
    except Exception as e:
        return {"experiments": [], "error": str(e)}


@app.post("/api/experiments/create")
async def create_experiment_endpoint(request: Request):
    """Create a new experiment."""
    from backtester.experiments import create_experiment
    from backtester.strategy import StrategyConfig
    data = await request.json()
    strategy = StrategyConfig(**(data.get("config", {})))
    strategy.name = data.get("name", "manual")
    exp_id = create_experiment(
        hypothesis=data.get("hypothesis", "Manual experiment"),
        strategy=strategy,
        source="manual",
        scope=data.get("scope", "global"),
    )
    return {"id": exp_id}


@app.post("/api/experiments/{exp_id}/run")
async def run_experiment_endpoint(exp_id: int):
    """Run a pending experiment."""
    from backtester.experiments import run_experiment, evaluate_significance
    try:
        result = run_experiment(exp_id)
        sig = evaluate_significance(exp_id)
        return {"result": result.to_dict(), "significance": sig}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/active-strategy")
async def get_active_strategy():
    """Get the current live weekly model and research champion."""
    try:
        from backtester.model_registry import get_live_weekly_model, get_research_champion

        live_strategy = get_live_weekly_model("global")
        research_strategy = get_research_champion("global")
        return {
            "strategy": live_strategy.__dict__,
            "live_weekly_model": live_strategy.__dict__,
            "research_champion": research_strategy.__dict__,
        }
    except Exception as e:
        return {"strategy": None, "error": str(e)}


@app.get("/api/agent-status")
async def get_agent_status():
    """Get research agent status."""
    conn = get_conn()
    try:
        pending = conn.execute("SELECT COUNT(*) FROM experiments WHERE status='pending'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM experiments WHERE status='running'").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM experiments WHERE status='completed'").fetchone()[0]
        promoted = conn.execute("SELECT COUNT(*) FROM experiments WHERE promoted=1").fetchone()[0]
        outliers = conn.execute("SELECT COUNT(*) FROM outlier_investigations").fetchone()[0]
        weather_hours = conn.execute("SELECT COUNT(*) FROM tournament_weather").fetchone()[0]
        return {
            "experiments": {"pending": pending, "running": running, "completed": completed, "promoted": promoted},
            "outlier_investigations": outliers,
            "weather_data_hours": weather_hours,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/outlier-investigations")
async def list_outlier_investigations():
    """Get recent outlier investigations."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT event_id, year, player_key, predicted_rank, actual_finish,
                   delta, root_cause, actionable, ai_explanation, created_at
            FROM outlier_investigations
            ORDER BY created_at DESC LIMIT 30
        """).fetchall()
        return {"investigations": [dict(r) for r in rows]}
    except Exception:
        return {"investigations": []}


# ── HTML Page (everything in one file) ──────────────────────────────

SIMPLE_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Golf Model Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 24px; line-height: 1.5; }
.wrap { max-width: 900px; margin: 0 auto; }
.hero { margin-bottom: 24px; }
.hero h1 { font-size: 1.5rem; margin: 0 0 4px; color: #f8fafc; }
.status-line { color: #94a3b8; font-size: 0.9rem; margin-top: 8px; }
.grid { display: grid; gap: 20px; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 20px; }
.card h2 { font-size: 1.1rem; margin: 0 0 14px; color: #f8fafc; }
button { padding: 10px 18px; border: 0; border-radius: 8px; background: #2563eb; color: white; cursor: pointer; font-weight: 500; }
button:hover { background: #1d4ed8; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
button.promote { background: #059669; }
button.promote:hover { background: #047857; }
.result { margin-top: 14px; padding: 14px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; white-space: pre-wrap; font-size: 0.9rem; }
.card-viewer { min-height: 120px; margin-top: 14px; padding: 16px; background: #0f172a; border-radius: 10px; border: 1px solid #334155; }
.card-viewer h1, .card-viewer h2, .card-viewer h3 { color: #f8fafc; }
.card-viewer p, .card-viewer li { color: #cbd5e1; }
.status { padding: 10px 12px; border-radius: 8px; font-size: 0.9rem; }
.status.info { background: #1e3a5f; color: #93c5fd; }
.status.success { background: #14532d; color: #86efac; }
.status.error { background: #450a0a; color: #fca5a5; }
.candidate-list { display: flex; flex-direction: column; gap: 14px; }
.candidate-item { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 14px; }
.candidate-item h3 { margin: 0 0 8px; font-size: 1rem; color: #f8fafc; }
.tldr { color: #cbd5e1; font-size: 0.9rem; margin: 8px 0; white-space: pre-wrap; }
.metrics { font-size: 0.85rem; color: #94a3b8; margin: 8px 0; }
.candidate-actions { margin-top: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.subtle { color: #94a3b8; font-size: 0.85rem; }
.footer { margin-top: 28px; padding-top: 16px; border-top: 1px solid #334155; }
a { color: #93c5fd; }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>Golf Model</h1>
    <p id="statusLine" class="status-line">Loading…</p>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Run prediction for upcoming tournament</h2>
      <p class="subtle">Uses the current live model and DataGolf to detect this weekend's event. Results appear below.</p>
      <button id="runPredictionBtn" onclick="runPrediction()">Run prediction</button>
      <div id="predResult" class="result" style="display:none;"></div>
      <div id="predCardViewer" class="card-viewer" style="display:none;"></div>
      <button id="downloadCardBtn" type="button" class="secondary" style="display:none; margin-top: 0.75rem;" onclick="downloadCard()" aria-label="Download prediction card as markdown file">Download card (.md)</button>
    </div>

    <div class="card">
      <h2>Run autoresearch</h2>
      <p class="subtle">Generate and evaluate strategy candidates. Best candidates appear below with a TLDR and option to promote to live.</p>
      <button id="runAutoresearchBtn" onclick="runAutoresearch()">Run autoresearch</button>
      <div id="autoresearchResult" class="result" style="display:none;"></div>
      <div id="bestCandidates" class="candidate-list"></div>
    </div>
  </div>

  <div class="footer">
    <a href="/legacy">Legacy dashboard</a> (loop, backtest, rollback, outputs)
  </div>
</div>

<script>
function escapeHtml(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function formatTime(value) {
  if (!value) return 'Never';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

async function loadStatus() {
  try {
    const resp = await fetch('/api/dashboard/state');
    const state = await resp.json();
    const live = state.effective_live_weekly_model || {};
    const research = state.effective_research_champion || {};
    const ar = state.autoresearch || {};
    document.getElementById('statusLine').textContent =
      'Live: ' + (live.name || 'none') + ' | Research champion: ' + (research.name || 'none') + ' | Last autoresearch: ' + formatTime(ar.last_finished_at);
  } catch (_) {
    document.getElementById('statusLine').textContent = 'Could not load status.';
  }
}

async function runPrediction() {
  const btn = document.getElementById('runPredictionBtn');
  const resultEl = document.getElementById('predResult');
  const viewerEl = document.getElementById('predCardViewer');
  btn.disabled = true;
  resultEl.style.display = 'block';
  resultEl.textContent = 'Running prediction…';
  viewerEl.style.display = 'none';
  viewerEl.innerHTML = '';
  try {
    const resp = await fetch('/api/simple/upcoming-prediction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tour: 'pga' })
    });
    const data = await resp.json();
    if (data.error || data.errors?.length) {
      resultEl.textContent = 'Error: ' + (data.error || (data.errors && data.errors.join(' ')) || 'Unknown');
      return;
    }
    resultEl.textContent = 'Done. Event: ' + (data.event_name || '—') + ' | Field: ' + (data.field_size ?? '—');
    let cardMarkdown = data.card_content;
    if (!cardMarkdown && (data.card_content_path || data.output_file || data.card_filepath)) {
      const path = data.card_content_path || data.output_file || data.card_filepath;
      const pathForApi = path.startsWith('output/') ? path : 'output/' + path.replace(/^.*[/]output[/]?/, '');
      const contentResp = await fetch('/api/output/content?path=' + encodeURIComponent(pathForApi));
      const contentData = await contentResp.json();
      cardMarkdown = contentData.error ? null : (contentData.content || null);
    }
    if (cardMarkdown) {
      window.lastCardMarkdown = cardMarkdown;
      window.lastCardEventName = (data.event_name || 'prediction_card').replace(/[^a-zA-Z0-9\\s-]/g, '').replace(/\\s+/g, '_').toLowerCase();
      viewerEl.style.display = 'block';
      viewerEl.innerHTML = (window.marked && window.marked.parse) ? marked.parse(cardMarkdown) : escapeHtml(cardMarkdown);
      document.getElementById('downloadCardBtn').style.display = 'inline-block';
    } else {
      window.lastCardMarkdown = null;
      document.getElementById('downloadCardBtn').style.display = 'none';
    }
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
}

function downloadCard() {
  const md = window.lastCardMarkdown;
  if (!md) return;
  const base = (window.lastCardEventName || 'prediction_card').replace(/[^a-zA-Z0-9_-]/g, '_');
  const now = new Date();
  const ymd = now.getFullYear() + String(now.getMonth() + 1).padStart(2, '0') + String(now.getDate()).padStart(2, '0');
  const filename = base + '_' + ymd + '.md';
  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

async function runAutoresearch() {
  const btn = document.getElementById('runAutoresearchBtn');
  const resultEl = document.getElementById('autoresearchResult');
  btn.disabled = true;
  resultEl.style.display = 'block';
  resultEl.textContent = 'Running autoresearch (this may take a while)…';
  try {
    const resp = await fetch('/api/autoresearch/run-once', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: 'global', max_candidates: 2 })
    });
    const data = await resp.json();
    resultEl.textContent = data.error ? ('Error: ' + data.error) : ('Cycle complete. Proposals evaluated: ' + (data.proposals_evaluated ?? '—'));
    await loadBestCandidates();
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
}

async function loadBestCandidates() {
  const container = document.getElementById('bestCandidates');
  try {
    const resp = await fetch('/api/autoresearch/best-candidates?scope=global&limit=3');
    const data = await resp.json();
    const candidates = data.candidates || [];
    if (!candidates.length) {
      container.innerHTML = '<div class="status info">No evaluated candidates yet. Run autoresearch first.</div>';
      return;
    }
    let html = '';
    for (const c of candidates) {
      const roi = c.summary_metrics && c.summary_metrics.weighted_roi_pct != null ? c.summary_metrics.weighted_roi_pct.toFixed(1) + '%' : '—';
      const clv = c.summary_metrics && c.summary_metrics.weighted_clv_avg != null ? c.summary_metrics.weighted_clv_avg.toFixed(3) : '—';
      const passed = c.guardrail_results && c.guardrail_results.passed ? 'Yes' : 'No';
      const tldr = escapeHtml((c.strategy_tldr || '').slice(0, 400));
      const reportPath = c.artifact_content_path || c.artifact_markdown_path;
      const reportLink = reportPath
        ? '<a href="#" class="report-link" data-path="' + escapeHtml(reportPath) + '">View report</a>'
        : '';
      html += '<div class="candidate-item">' +
        '<h3>' + escapeHtml(c.name || 'Unnamed') + '</h3>' +
        '<div class="tldr">' + tldr + (tldr.length >= 400 ? '…' : '') + '</div>' +
        '<div class="metrics">ROI: ' + roi + ' | CLV: ' + clv + ' | Guardrails: ' + passed + ' ' + reportLink + '</div>' +
        '<div class="candidate-actions">' +
        '<button class="promote" onclick="promoteToLive(' + c.id + ')">Promote to live</button>' +
        '<span id="promoteMsg' + c.id + '" class="subtle"></span>' +
        '</div></div>';
    }
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = '<div class="status error">Failed to load candidates: ' + escapeHtml(err.message) + '</div>';
  }
}

async function viewReport(path) {
  const resp = await fetch('/api/output/content?path=' + encodeURIComponent(path));
  const data = await resp.json();
  if (data.error) { alert(data.error); return; }
  const win = window.open('', '_blank');
  win.document.write('<html><head><title>Report</title></head><body style="background:#0f172a;color:#e2e8f0;padding:20px;font-family:system-ui;">');
  win.document.write((window.marked && window.marked.parse) ? marked.parse(data.content || '') : '<pre>' + escapeHtml(data.content || '') + '</pre>');
  win.document.write('</body></html>');
  win.document.close();
}

document.addEventListener('click', function(e) {
  if (e.target && e.target.classList && e.target.classList.contains('report-link')) {
    e.preventDefault();
    viewReport(e.target.getAttribute('data-path'));
  }
});

async function promoteToLive(proposalId) {
  const msgEl = document.getElementById('promoteMsg' + proposalId);
  if (msgEl) msgEl.textContent = 'Promoting…';
  try {
    const resp = await fetch('/api/model-registry/promote-proposal-to-live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id: proposalId, scope: 'global', reviewer: 'dashboard' })
    });
    const data = await resp.json();
    if (msgEl) {
      if (data.ok) msgEl.textContent = 'Promoted.';
      else msgEl.textContent = data.blocked_reason && data.blocked_reason.length ? ('Blocked: ' + data.blocked_reason.join(', ')) : (data.error || 'Failed');
    }
    loadStatus();
    loadBestCandidates();
  } catch (err) {
    if (msgEl) msgEl.textContent = 'Error: ' + err.message;
  }
}

document.addEventListener('DOMContentLoaded', function() {
  loadStatus();
  loadBestCandidates();
});
</script>
</body>
</html>
"""

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
        <div class="tab" onclick="showTab('backtester')">Backtester</div>
        <div class="tab" onclick="showTab('experiments')">Experiments</div>
        <div class="tab" onclick="showTab('agent')">Agent</div>
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

    <!-- ══ BACKTESTER TAB ═══════════════════════════════ -->
    <div id="tab-backtester" class="tab-content">
        <h2>Run Backtest</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:15px;">
            Simulate a betting strategy against historical data. Requires backfilled data + PIT stats.
        </p>
        <div class="form-row">
            <div><label>Strategy Name</label><input id="btName" type="text" value="manual_test" style="width:100%"></div>
            <div><label>Min EV Threshold</label><input id="btMinEv" type="number" step="0.01" value="0.05" style="width:100%"></div>
        </div>
        <div class="form-row">
            <div><label>Stat Window (rounds)</label><select id="btWindow" style="width:100%"><option value="12">12 (hot form)</option><option value="24" selected>24 (balanced)</option><option value="50">50 (stability)</option></select></div>
            <div><label>Years (comma-separated)</label><input id="btYears" type="text" value="2024,2025" style="width:100%"></div>
        </div>
        <div class="form-row">
            <div><label>Softmax Temperature</label><input id="btTemp" type="number" step="0.1" value="1.0" style="width:100%"></div>
            <div><label>Kelly Fraction</label><input id="btKelly" type="number" step="0.05" value="0.25" style="width:100%"></div>
        </div>
        <button onclick="runBacktest()">Run Backtest</button>
        <div id="backtestResult" style="margin-top:15px;"></div>
    </div>

    <!-- ══ EXPERIMENTS TAB ══════════════════════════════ -->
    <div id="tab-experiments" class="tab-content">
        <h2>Experiment Leaderboard</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:10px;">
            Strategies ranked by backtest ROI. Significant winners get promoted to active.
        </p>
        <div id="experimentsList"><div class="status loading"><span class="spinner"></span>Loading...</div></div>

        <h2>Active Strategy</h2>
        <div id="activeStrategy"><div class="status info">Loading...</div></div>

        <h2>Create Experiment</h2>
        <div class="form-row">
            <div><label>Hypothesis</label><input id="expHypothesis" type="text" placeholder="e.g. Higher approach weight on long courses" style="width:100%"></div>
        </div>
        <button class="secondary" onclick="createExperiment()">Create & Queue</button>
        <div id="createExpResult" style="margin-top:10px;"></div>
    </div>

    <!-- ══ AGENT TAB ═══════════════════════════════════ -->
    <div id="tab-agent" class="tab-content">
        <h2>Research Agent Status</h2>
        <p style="color:#94a3b8;font-size:0.85em;margin-bottom:15px;">
            The autonomous agent runs 5 background threads: data collection, hypothesis generation,
            experiment execution, outlier analysis, and Bayesian optimization.
        </p>
        <div id="agentStatus"><div class="status loading"><span class="spinner"></span>Loading...</div></div>

        <h2>Recent Outlier Investigations</h2>
        <div id="outlierList"><div class="status info">Loading...</div></div>
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
const TAB_NAMES = ['setup','predictions','ai','backtester','experiments','agent','data','dashboard'];
function showTab(name) {
    document.querySelectorAll('.tab').forEach((t, i) => {
        t.classList.toggle('active', TAB_NAMES[i] === name);
    });
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const el = document.getElementById('tab-' + name);
    if (el) el.classList.add('active');

    if (name === 'predictions') loadPredictions();
    if (name === 'ai') { loadAiStatus(); loadTournaments(); }
    if (name === 'backtester') {}
    if (name === 'experiments') { loadExperiments(); loadActiveStrategy(); }
    if (name === 'agent') { loadAgentStatus(); loadOutliers(); }
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

// ══ BACKTESTER ══
async function runBacktest() {
    const el = document.getElementById('backtestResult');
    el.innerHTML = '<div class="status loading"><span class="spinner"></span>Running backtest... this may take a minute</div>';
    const config = {
        name: document.getElementById('btName').value,
        min_ev: parseFloat(document.getElementById('btMinEv').value),
        stat_window: parseInt(document.getElementById('btWindow').value),
        softmax_temp: parseFloat(document.getElementById('btTemp').value),
        kelly_fraction: parseFloat(document.getElementById('btKelly').value),
    };
    const years = document.getElementById('btYears').value;
    try {
        // Create experiment then run it
        const createResp = await fetch('/api/experiments/create', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({name:config.name, hypothesis:'Manual backtest: '+config.name, config:config})
        });
        const createData = await createResp.json();
        if (!createData.id) { el.innerHTML='<div class="status error">Failed to create experiment</div>'; return; }

        const runResp = await fetch('/api/experiments/'+createData.id+'/run', {method:'POST'});
        const runData = await runResp.json();
        if (runData.error) { el.innerHTML='<div class="status error">'+runData.error+'</div>'; return; }

        const r = runData.result || {};
        const s = runData.significance || {};
        let html = '<div class="stats-grid">';
        html += '<div class="stat-box"><div class="number">'+(r.events_simulated||0)+'</div><div class="label">Events</div></div>';
        html += '<div class="stat-box"><div class="number">'+(r.total_bets||0)+'</div><div class="label">Bets</div></div>';
        html += '<div class="stat-box"><div class="number">'+(r.wins||0)+'</div><div class="label">Wins</div></div>';
        html += '<div class="stat-box"><div class="number" style="color:'+((r.roi_pct||0)>=0?'#4ade80':'#ef4444')+'">'+(r.roi_pct||0).toFixed(1)+'%</div><div class="label">ROI</div></div>';
        html += '<div class="stat-box"><div class="number">'+(r.sharpe||0).toFixed(3)+'</div><div class="label">Sharpe</div></div>';
        html += '<div class="stat-box"><div class="number">'+(r.clv_avg||0).toFixed(4)+'</div><div class="label">Avg CLV</div></div>';
        html += '</div>';
        if (s.significant) html += '<div class="status success">Statistically significant improvement (p='+s.p_value+')</div>';
        else if (s.p_value) html += '<div class="status info">Not significant (p='+s.p_value+')</div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

// ══ EXPERIMENTS ══
async function loadExperiments() {
    const el = document.getElementById('experimentsList');
    try {
        const resp = await fetch('/api/experiments');
        const data = await resp.json();
        const exps = data.experiments || [];
        if (!exps.length) { el.innerHTML='<div class="status info">No experiments yet. Run a backtest or start the research agent.</div>'; return; }
        let html = '<table><tr><th>#</th><th>Hypothesis</th><th>Source</th><th>ROI</th><th>Bets</th><th>Sharpe</th><th>Sig?</th><th>Status</th></tr>';
        for (const e of exps) {
            const roiColor = (e.roi_pct||0)>=0?'#4ade80':'#ef4444';
            html += '<tr><td>'+e.id+'</td><td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;">'+e.hypothesis+'</td><td style="font-size:0.8em;">'+e.source+'</td><td class="num" style="color:'+roiColor+'">'+(e.roi_pct||0).toFixed(1)+'%</td><td class="num">'+(e.total_bets||0)+'</td><td class="num">'+(e.sharpe||0).toFixed(2)+'</td><td>'+(e.significant?'Yes':'—')+'</td><td>'+(e.promoted?'<span style="color:#4ade80;">ACTIVE</span>':e.status)+'</td></tr>';
        }
        html += '</table>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error loading experiments</div>'; }
}

async function loadActiveStrategy() {
    const el = document.getElementById('activeStrategy');
    try {
        const resp = await fetch('/api/active-strategy');
        const data = await resp.json();
        const s = data.strategy;
        if (!s) { el.innerHTML='<div class="status info">Using default strategy (no experiments promoted yet)</div>'; return; }
        let html = '<div class="card-section"><div class="stats-grid">';
        const fields = ['w_sg_total','w_sg_app','w_sg_ott','w_sg_arg','w_sg_putt','w_form','w_course_fit'];
        for (const f of fields) html += '<div class="stat-box"><div class="number">'+(s[f]||0).toFixed(2)+'</div><div class="label">'+f.replace('w_','')+'</div></div>';
        html += '</div><p style="margin-top:10px;color:#94a3b8;font-size:0.85em;">Min EV: '+s.min_ev+' · Window: '+s.stat_window+' · Temp: '+s.softmax_temp+' · Kelly: '+s.kelly_fraction+'</p></div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error</div>'; }
}

async function createExperiment() {
    const el = document.getElementById('createExpResult');
    const hyp = document.getElementById('expHypothesis').value;
    if (!hyp) { alert('Enter a hypothesis'); return; }
    try {
        const resp = await fetch('/api/experiments/create', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({hypothesis:hyp, name:'manual', scope:'global', config:{}})
        });
        const data = await resp.json();
        el.innerHTML='<div class="status success">Created experiment #'+data.id+'. Run it from the Backtester tab.</div>';
        loadExperiments();
    } catch(e) { el.innerHTML='<div class="status error">Error: '+e.message+'</div>'; }
}

// ══ AGENT ══
async function loadAgentStatus() {
    const el = document.getElementById('agentStatus');
    try {
        const resp = await fetch('/api/agent-status');
        const data = await resp.json();
        if (data.error) { el.innerHTML='<div class="status error">'+data.error+'</div>'; return; }
        const e = data.experiments || {};
        let html = '<div class="stats-grid">';
        html += '<div class="stat-box"><div class="number">'+(e.pending||0)+'</div><div class="label">Pending</div></div>';
        html += '<div class="stat-box"><div class="number">'+(e.running||0)+'</div><div class="label">Running</div></div>';
        html += '<div class="stat-box"><div class="number">'+(e.completed||0)+'</div><div class="label">Completed</div></div>';
        html += '<div class="stat-box"><div class="number" style="color:#4ade80;">'+(e.promoted||0)+'</div><div class="label">Promoted</div></div>';
        html += '<div class="stat-box"><div class="number">'+(data.outlier_investigations||0)+'</div><div class="label">Outliers</div></div>';
        html += '<div class="stat-box"><div class="number">'+(data.weather_data_hours||0).toLocaleString()+'</div><div class="label">Weather Hrs</div></div>';
        html += '</div>';
        html += '<div style="margin-top:15px;"><p style="color:#94a3b8;font-size:0.85em;">Start the agent: <code style="background:#1e2030;padding:2px 6px;border-radius:3px;">python start.py agent</code></p></div>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error loading agent status</div>'; }
}

async function loadOutliers() {
    const el = document.getElementById('outlierList');
    try {
        const resp = await fetch('/api/outlier-investigations');
        const data = await resp.json();
        const items = data.investigations || [];
        if (!items.length) { el.innerHTML='<div class="status info">No outlier investigations yet. Start the agent or run a backtest first.</div>'; return; }
        let html = '<table><tr><th>Event</th><th>Year</th><th>Player</th><th>Predicted</th><th>Actual</th><th>Delta</th><th>Cause</th><th>Actionable</th></tr>';
        for (const o of items) {
            const color = o.delta > 50 ? '#ef4444' : o.delta > 30 ? '#fbbf24' : '#94a3b8';
            html += '<tr><td>'+o.event_id+'</td><td>'+o.year+'</td><td>'+o.player_key+'</td><td class="num">'+o.predicted_rank+'</td><td class="num">'+o.actual_finish+'</td><td class="num" style="color:'+color+'">'+o.delta+'</td><td>'+o.root_cause+'</td><td>'+(o.actionable?'Yes':'—')+'</td></tr>';
        }
        html += '</table>';
        el.innerHTML = html;
    } catch(e) { el.innerHTML='<div class="status error">Error loading outliers</div>'; }
}

</script>
</body>
</html>"""


if __name__ == "__main__":
    init_db()
    print("\\n  Golf Betting Model — Web UI")
    print("  Open in browser: http://localhost:8000\\n")
    quiet_logs = os.environ.get("QUIET_DEV_ACCESS_LOGS", "0").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
        access_log=not quiet_logs,
    )
