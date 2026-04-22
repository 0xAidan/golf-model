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
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

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
    list_completed_snapshot_events,
    build_completed_snapshot_section,
    get_latest_snapshot_section,
    get_market_prediction_rows_for_event,
    list_snapshot_timeline_points,
)
from src.models.composite import compute_composite
from src.models.weights import retune, analyze_pick_performance, get_current_weights
from src.player_normalizer import normalize_name, display_name
from src.odds import fetch_odds_api, load_manual_odds, get_best_odds
from src.value import find_value_bets
from src.scoring import determine_outcome

import pandas as pd
from fastapi.staticfiles import StaticFiles

_logger = logging.getLogger("golf.app")


_DEFAULT_LIVE_REFRESH_PIDFILE = "/tmp/golf_live_refresh.pid"


def _live_refresh_pidfile_path() -> str:
    return os.environ.get("LIVE_REFRESH_PIDFILE", _DEFAULT_LIVE_REFRESH_PIDFILE)


def _live_refresh_worker_is_running(pidfile_path: str) -> bool:
    """Return True if the pidfile points to a live process."""
    try:
        with open(pidfile_path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        if not raw:
            return False
        pid = int(raw)
    except (FileNotFoundError, ValueError, OSError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    from src.autoresearch_settings import get_settings
    from backtester.dashboard_runtime import start_live_refresh, stop_live_refresh

    settings = get_settings().get("live_refresh", {})
    embedded_autostart_enabled = os.environ.get("LIVE_REFRESH_EMBEDDED_AUTOSTART", "0").strip().lower() not in {
        "0", "false", "off", "no", ""
    }
    started_embedded = False
    if embedded_autostart_enabled:
        _logger.warning(
            "LIVE_REFRESH_EMBEDDED_AUTOSTART=1 is set: the in-process live refresh loop will attempt to start. "
            "The systemd worker (golf-live-refresh.service) is the authoritative owner in production; "
            "enabling embedded autostart alongside it will cause duplicate API pulls and snapshot write races."
        )
        pidfile_path = _live_refresh_pidfile_path()
        if _live_refresh_worker_is_running(pidfile_path):
            _logger.warning(
                "Skipping embedded live-refresh autostart: worker pidfile %s points to a live process. "
                "Set LIVE_REFRESH_EMBEDDED_AUTOSTART=0 or stop the worker to silence this warning.",
                pidfile_path,
            )
        elif settings.get("enabled") and settings.get("autostart"):
            start_live_refresh(tour=str(settings.get("tour", "pga")))
            started_embedded = True
    try:
        yield
    finally:
        if started_embedded:
            stop_live_refresh()


app = FastAPI(title="Golf Betting Model", lifespan=_lifespan)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
FRONTEND_DIST_INDEX = FRONTEND_DIST_DIR / "index.html"
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


_PROFILE_CATEGORY_METRIC_ORDER: dict[str, list[str]] = {
    "dg_skill": [
        "sg_total",
        "dg_sg_total",
        "sg_ott",
        "dg_sg_ott",
        "sg_app",
        "dg_sg_app",
        "sg_arg",
        "dg_sg_arg",
        "sg_putt",
        "dg_sg_putt",
        "driving_dist",
        "dg_driving_dist",
        "driving_acc",
        "dg_driving_acc",
    ],
    "dg_ranking": ["dg_rank", "owgr_rank", "dg_skill_estimate"],
    "dg_approach": [
        "approach_sg_composite",
        "50_100_fw_sg_per_shot",
        "50_100_rgh_sg_per_shot",
        "100_150_fw_sg_per_shot",
        "100_150_rgh_sg_per_shot",
        "150_200_fw_sg_per_shot",
        "150_200_rgh_sg_per_shot",
        "200_plus_fw_sg_per_shot",
        "200_plus_rgh_sg_per_shot",
    ],
    "dg_decomposition": [
        "dg_sg_total",
        "dg_baseline_pred",
        "dg_total_fit_adj",
        "dg_total_ch_adj",
        "dg_sg_category_adj",
        "dg_driving_dist_adj",
        "dg_driving_acc_adj",
        "dg_cf_approach",
        "dg_cf_short",
    ],
    "strokes_gained": ["SG:TOT", "SG:OTT", "SG:APP", "SG:ARG", "SG:PUTT"],
    "sim": ["Win %", "Top 5 %", "Top 10 %", "Top 20 %", "Make Cut %"],
    "meta": ["field_status", "teetime", "draftkings", "fanduel", "dg_id"],
}

_PROFILE_METRIC_LABELS: dict[str, str] = {
    "sg_total": "SG Total",
    "dg_sg_total": "DG SG Total",
    "sg_ott": "Off-the-Tee",
    "dg_sg_ott": "DG Off-the-Tee",
    "sg_app": "Approach",
    "dg_sg_app": "DG Approach",
    "sg_arg": "Around Green",
    "dg_sg_arg": "DG Around Green",
    "sg_putt": "Putting",
    "dg_sg_putt": "DG Putting",
    "driving_dist": "Driving Distance",
    "dg_driving_dist": "DG Driving Distance",
    "driving_acc": "Driving Accuracy",
    "dg_driving_acc": "DG Driving Accuracy",
    "dg_rank": "DataGolf Rank",
    "owgr_rank": "OWGR Rank",
    "dg_skill_estimate": "DG Skill Estimate",
    "approach_sg_composite": "Approach Composite",
    "dg_total_fit_adj": "Course-Fit Adjustment",
    "dg_total_ch_adj": "Course-History Adjustment",
    "dg_sg_category_adj": "Category Adjustment",
    "dg_driving_dist_adj": "Distance Adjustment",
    "dg_driving_acc_adj": "Accuracy Adjustment",
    "dg_cf_approach": "Approach Component",
    "dg_cf_short": "Short-Game Component",
    "SG:TOT": "SG Total",
    "SG:OTT": "SG Off-the-Tee",
    "SG:APP": "SG Approach",
    "SG:ARG": "SG Around Green",
    "SG:PUTT": "SG Putting",
    "field_status": "Field Status",
    "teetime": "Tee Time",
}

_PROFILE_ROLLING_WINDOWS = {"10": "8", "25": "24", "50": "all"}
_CUT_LIKE_STATES = {"CUT", "MC", "MDF", "WD", "DQ", "DNS"}


def _profile_metric_value(metric: dict) -> float | str | None:
    if metric.get("metric_value") is not None:
        return float(metric["metric_value"])
    value = metric.get("metric_text")
    return str(value) if value is not None else None


def _profile_numeric_value(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _profile_average(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    return round(mean(clean), 3)


def _profile_label(metric_name: str) -> str:
    if metric_name in _PROFILE_METRIC_LABELS:
        return _PROFILE_METRIC_LABELS[metric_name]
    return metric_name.replace("_", " ").replace(":", " ").title()


def _group_profile_metrics(metrics: list[dict]) -> tuple[
    dict[str, dict[str, float | str | None]],
    dict[str, dict[str, dict[str, float | str | None]]],
]:
    by_category: dict[str, dict[str, float | str | None]] = {}
    by_category_window: dict[str, dict[str, dict[str, float | str | None]]] = {}

    for metric in metrics:
        category = str(metric.get("metric_category") or "other")
        window = str(metric.get("round_window") or "all")
        metric_name = str(metric.get("metric_name") or "value")
        value = _profile_metric_value(metric)
        if value is None:
            continue

        bucket = by_category_window.setdefault(category, {}).setdefault(window, {})
        bucket[metric_name] = value

        flat_key = metric_name if window == "all" else f"{metric_name} [{window}]"
        by_category.setdefault(category, {})[flat_key] = value

    ordered_categories: dict[str, dict[str, float | str | None]] = {}
    for category in sorted(by_category):
        values = by_category[category]
        preferred = _PROFILE_CATEGORY_METRIC_ORDER.get(category, [])
        preferred_index = {name: idx for idx, name in enumerate(preferred)}
        sorted_keys = sorted(
            values.keys(),
            key=lambda key: (
                preferred_index.get(key.split(" [", 1)[0], len(preferred) + 50),
                key,
            ),
        )
        ordered_categories[category] = {key: values[key] for key in sorted_keys}
    return ordered_categories, by_category_window


def _build_skill_breakdown(
    metrics_by_category_window: dict[str, dict[str, dict[str, float | str | None]]],
) -> dict:
    skill_metrics = metrics_by_category_window.get("dg_skill", {}).get("all", {})
    ranking_metrics = metrics_by_category_window.get("dg_ranking", {}).get("all", {})
    approach_metrics = metrics_by_category_window.get("dg_approach", {}).get("all", {})
    decomposition_metrics = metrics_by_category_window.get("dg_decomposition", {}).get("all", {})

    primary_pairs = [
        ("dg_sg_total", "sg_total"),
        ("dg_sg_ott", "sg_ott"),
        ("dg_sg_app", "sg_app"),
        ("dg_sg_arg", "sg_arg"),
        ("dg_sg_putt", "sg_putt"),
    ]
    primary = []
    for preferred_key, fallback_key in primary_pairs:
        key = preferred_key if preferred_key in skill_metrics else fallback_key
        value = _profile_numeric_value(skill_metrics.get(key))
        if value is None:
            continue
        primary.append({"key": key, "label": _profile_label(key), "value": round(value, 3)})
    approach_composite = _profile_numeric_value(approach_metrics.get("approach_sg_composite"))
    if approach_composite is not None:
        primary.append(
            {
                "key": "approach_sg_composite",
                "label": _profile_label("approach_sg_composite"),
                "value": round(approach_composite, 3),
            }
        )

    approach_buckets = []
    for key, value in approach_metrics.items():
        if not key.endswith("_sg_per_shot"):
            continue
        numeric = _profile_numeric_value(value)
        if numeric is None:
            continue
        approach_buckets.append({"key": key, "label": _profile_label(key), "value": round(numeric, 3)})
    approach_buckets.sort(key=lambda row: row["value"], reverse=True)

    component_delta_keys = [
        "dg_total_fit_adj",
        "dg_total_ch_adj",
        "dg_sg_category_adj",
        "dg_driving_dist_adj",
        "dg_driving_acc_adj",
        "dg_cf_approach",
        "dg_cf_short",
    ]
    component_deltas = []
    for key in component_delta_keys:
        numeric = _profile_numeric_value(decomposition_metrics.get(key))
        if numeric is None:
            continue
        component_deltas.append({"key": key, "label": _profile_label(key), "value": round(numeric, 3)})

    sorted_primary = sorted(primary, key=lambda row: row["value"], reverse=True)
    best_area = sorted_primary[0] if sorted_primary else None
    weakest_area = sorted_primary[-1] if sorted_primary else None
    return {
        "primary": primary,
        "approach_buckets": approach_buckets[:12],
        "component_deltas": component_deltas,
        "summary": {
            "best_area": best_area,
            "weakest_area": weakest_area,
            "dg_rank": _profile_numeric_value(ranking_metrics.get("dg_rank")),
            "owgr_rank": _profile_numeric_value(ranking_metrics.get("owgr_rank")),
            "dg_skill_estimate": _profile_numeric_value(ranking_metrics.get("dg_skill_estimate")),
        },
    }


def _build_rolling_form_section(
    db_module,
    tournament_id: int,
    metrics_by_category_window: dict[str, dict[str, dict[str, float | str | None]]],
    recent_rounds: list[dict],
) -> dict:
    sg_metrics = metrics_by_category_window.get("strokes_gained", {})
    recent_sg = [
        float(round_row["sg_total"])
        for round_row in recent_rounds
        if round_row.get("sg_total") is not None
    ]

    window_values: dict[str, float | None] = {}
    benchmark_values: dict[str, dict[str, float | None]] = {
        "tour_avg": {},
        "top50": {},
        "top10": {},
    }
    source_window_map: dict[str, str] = {}
    for ui_window, source_window in _PROFILE_ROLLING_WINDOWS.items():
        source_window_map[ui_window] = source_window
        player_value = _profile_numeric_value(
            sg_metrics.get(source_window, {}).get("SG:TOT")
        )
        if player_value is None and recent_sg:
            fallback_window = min(int(ui_window), len(recent_sg))
            player_value = _profile_average(recent_sg[:fallback_window])
        window_values[ui_window] = round(player_value, 3) if player_value is not None else None

        sample = db_module.get_tournament_metric_values(
            tournament_id,
            "strokes_gained",
            "SG:TOT",
            data_mode="recent_form",
            round_window=source_window,
        )
        if not sample and source_window == "all":
            sample = db_module.get_tournament_metric_values(
                tournament_id,
                "strokes_gained",
                "SG:TOT",
                round_window=source_window,
            )
        ordered = sorted(sample, reverse=True)
        half_count = max(1, len(ordered) // 2) if ordered else 0
        top_count = min(10, len(ordered))
        benchmark_values["tour_avg"][ui_window] = _profile_average(ordered) if ordered else None
        benchmark_values["top50"][ui_window] = _profile_average(ordered[:half_count]) if half_count else None
        benchmark_values["top10"][ui_window] = _profile_average(ordered[:top_count]) if top_count else None

    short_value = window_values.get("10")
    medium_value = window_values.get("25")
    delta_short_vs_medium = (
        round(short_value - medium_value, 3)
        if short_value is not None and medium_value is not None
        else None
    )
    return {
        "windows": window_values,
        "window_source_map": source_window_map,
        "benchmarks": benchmark_values,
        "trend_series": list(reversed(recent_sg[:50])),
        "summary": {
            "delta_short_vs_medium": delta_short_vs_medium,
            "rounds_in_sample": len(recent_sg),
        },
    }


def _summarize_recent_events(recent_rounds: list[dict], limit: int = 8) -> list[dict]:
    event_map: dict[str, dict] = {}
    ordered_keys: list[str] = []
    for round_row in recent_rounds:
        event_key = (
            str(round_row.get("event_id") or "").strip()
            or str(round_row.get("event_name") or "").strip()
            or str(round_row.get("event_completed") or "").strip()
        )
        if not event_key:
            continue
        if event_key not in event_map:
            event_map[event_key] = {
                "event_name": round_row.get("event_name"),
                "event_completed": round_row.get("event_completed"),
                "fin_text": round_row.get("fin_text"),
                "sg_total_values": [],
                "rounds_recorded": 0,
            }
            ordered_keys.append(event_key)
        event_row = event_map[event_key]
        sg_total = round_row.get("sg_total")
        if sg_total is not None:
            event_row["sg_total_values"].append(float(sg_total))
        event_row["rounds_recorded"] += 1
        if not event_row.get("fin_text") and round_row.get("fin_text"):
            event_row["fin_text"] = round_row.get("fin_text")

    summarized = []
    for key in ordered_keys[:limit]:
        event_row = event_map[key]
        summarized.append(
            {
                "event_name": event_row.get("event_name"),
                "event_completed": event_row.get("event_completed"),
                "fin_text": event_row.get("fin_text"),
                "rounds_recorded": event_row.get("rounds_recorded"),
                "avg_sg_total": _profile_average(event_row.get("sg_total_values") or []),
            }
        )
    return summarized


def _build_course_event_context(recent_rounds: list[dict], course_history: list[dict]) -> dict:
    recent_events = _summarize_recent_events(recent_rounds, limit=8)
    recent_sg = [
        event["avg_sg_total"]
        for event in recent_events
        if event.get("avg_sg_total") is not None
    ]
    made_cut_count = sum(
        1
        for event in recent_events
        if str(event.get("fin_text") or "").strip().upper() not in _CUT_LIKE_STATES
    )

    course_sg = [
        float(round_row["sg_total"])
        for round_row in course_history
        if round_row.get("sg_total") is not None
    ]
    return {
        "recent_starts": recent_events,
        "recent_summary": {
            "events_tracked": len(recent_events),
            "made_cuts": made_cut_count,
            "avg_sg_total": _profile_average(recent_sg),
        },
        "course_summary": {
            "rounds_tracked": len(course_history),
            "avg_sg_total": _profile_average(course_sg),
            "best_round_sg": round(max(course_sg), 3) if course_sg else None,
            "worst_round_sg": round(min(course_sg), 3) if course_sg else None,
        },
    }


def _build_betting_context(linked_bets: list[dict]) -> dict:
    ev_values = [
        float(bet["ev"])
        for bet in linked_bets
        if bet.get("ev") is not None
    ]
    high_confidence = [
        bet
        for bet in linked_bets
        if str(bet.get("confidence") or "").strip().lower() in {"high", "strong"}
    ]
    strongest_bet = linked_bets[0] if linked_bets else None
    return {
        "summary": {
            "linked_bet_count": len(linked_bets),
            "average_ev": _profile_average(ev_values),
            "high_confidence_count": len(high_confidence),
        },
        "strongest_linked_bet": strongest_bet,
    }


def _build_profile_header(
    metrics_by_category_window: dict[str, dict[str, dict[str, float | str | None]]],
    field_size: int,
    recent_rounds: list[dict],
    course_history: list[dict],
) -> dict:
    ranking_metrics = metrics_by_category_window.get("dg_ranking", {}).get("all", {})
    meta_metrics = metrics_by_category_window.get("meta", {}).get("all", {})
    latest_round = recent_rounds[0] if recent_rounds else {}
    return {
        "dg_rank": _profile_numeric_value(ranking_metrics.get("dg_rank")),
        "owgr_rank": _profile_numeric_value(ranking_metrics.get("owgr_rank")),
        "dg_skill_estimate": _profile_numeric_value(ranking_metrics.get("dg_skill_estimate")),
        "field_size": field_size,
        "tee_time": meta_metrics.get("teetime"),
        "field_status": meta_metrics.get("field_status"),
        "recent_rounds_tracked": len(recent_rounds),
        "course_rounds_tracked": len(course_history),
        "latest_event_name": latest_round.get("event_name"),
        "latest_event_completed": latest_round.get("event_completed"),
    }


@app.get("/api/players/{player_key}/profile")
async def get_player_profile(player_key: str, tournament_id: int, course_num: int | None = None):
    """Return rich profile data for one player in the current tournament context."""
    from src import db

    profile_categories = [
        "dg_skill",
        "dg_ranking",
        "dg_approach",
        "dg_decomposition",
        "strokes_gained",
        "sim",
        "meta",
    ]
    metrics = db.get_player_metrics_by_categories(tournament_id, player_key, profile_categories)
    if not metrics:
        metrics = db.get_player_metrics(tournament_id, player_key)
    recent_rounds = db.get_player_recent_rounds_by_key(player_key, limit=24)

    metrics_by_category, metrics_by_category_window = _group_profile_metrics(metrics)

    dg_id = _profile_numeric_value(
        metrics_by_category_window.get("meta", {}).get("all", {}).get("dg_id")
    )
    if dg_id is None and recent_rounds:
        dg_id = _profile_numeric_value(recent_rounds[0].get("dg_id"))

    course_history = []
    if dg_id and course_num is not None:
        course_history = db.get_player_course_rounds(int(dg_id), course_num)[:36]

    field_size = db.get_tournament_field_size(tournament_id)

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
    linked_bets_payload = [dict(row) for row in linked_bets][:20]

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
        "linked_bets": linked_bets_payload,
        "header": _build_profile_header(
            metrics_by_category_window,
            field_size,
            recent_rounds,
            course_history,
        ),
        "skill_breakdown": _build_skill_breakdown(metrics_by_category_window),
        "rolling_form": _build_rolling_form_section(
            db,
            tournament_id,
            metrics_by_category_window,
            recent_rounds,
        ),
        "course_event_context": _build_course_event_context(recent_rounds, course_history),
        "betting_context": _build_betting_context(linked_bets_payload),
        "metric_labels": _PROFILE_METRIC_LABELS,
        "sections_version": 1,
    }


# ── API Endpoints ───────────────────────────────────────────────────

def _render_dashboard_html():
    """Serve the built React dashboard. The React SPA is the sole UI."""
    if FRONTEND_DIST_INDEX.is_file():
        return FRONTEND_DIST_INDEX.read_text(encoding="utf-8")
    return (
        "<!doctype html><html><body>"
        "<h1>Frontend not built</h1>"
        "<p>Run <code>npm run build</code> in <code>frontend/</code> to produce <code>frontend/dist/</code>.</p>"
        "</body></html>"
    )


@app.get("/", response_class=HTMLResponse)
async def home():
    return _render_dashboard_html()


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


@app.get("/api/live-refresh/past-events")
async def get_live_refresh_past_events(limit: int = Query(default=40, ge=1, le=200)):
    """List events available for Completed replay (frozen pre-teeoff + live history)."""
    from src.db import ensure_initialized

    ensure_initialized()
    events = list_completed_snapshot_events(limit=limit)
    return {"events": events}


_LIVE_REFRESH_REPLAY_SECTIONS = {"live", "upcoming"}


def _invalid_replay_section_response() -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": "section must be one of: live, upcoming"},
        status_code=400,
    )


def _normalize_replay_section(section: str | None, *, allow_none: bool = False) -> str | None:
    if section is None:
        return None if allow_none else "live"
    section_value = section.strip().lower()
    if not section_value:
        return "live"
    if section_value not in _LIVE_REFRESH_REPLAY_SECTIONS:
        return None
    return section_value


@app.get("/api/live-refresh/past-snapshot")
async def get_live_refresh_past_snapshot(
    event_id: str = Query(..., min_length=1),
    section: str = Query(default="completed"),
):
    """Return snapshot for a past event: completed (default), live, or upcoming section."""
    from src.db import ensure_initialized

    ensure_initialized()
    raw_section = (section or "").strip().lower() or "completed"
    if raw_section == "completed":
        merged = build_completed_snapshot_section(event_id)
        if not merged:
            return JSONResponse(
                {"ok": False, "error": "No completed snapshot available for this event."},
                status_code=404,
            )
        return {
            "ok": True,
            "event_id": event_id,
            "section": "completed",
            "snapshot": merged,
        }
    section_value = _normalize_replay_section(raw_section)
    if section_value is None:
        return JSONResponse(
            {"ok": False, "error": "section must be 'completed', 'live', or 'upcoming'"},
            status_code=400,
        )

    payload = get_latest_snapshot_section(event_id=event_id, section=section_value)
    if not payload:
        return JSONResponse(
            {"ok": False, "error": "No snapshot history found for this event."},
            status_code=404,
        )
    return {
        "ok": True,
        "event_id": event_id,
        "snapshot_id": payload.get("snapshot_id"),
        "generated_at": payload.get("generated_at"),
        "tour": payload.get("tour"),
        "section": payload.get("section"),
        "snapshot": payload.get("snapshot") or {},
    }


@app.get("/api/live-refresh/past-timeline")
async def get_live_refresh_past_timeline(
    event_id: str = Query(..., min_length=1),
    section: str = Query(default="live"),
    limit: int = Query(default=120, ge=1, le=1000),
):
    """Return ordered replay timeline points for a past event section."""
    from src.db import ensure_initialized

    ensure_initialized()
    section_value = _normalize_replay_section(section)
    if section_value is None:
        return _invalid_replay_section_response()

    points = list_snapshot_timeline_points(event_id=event_id, section=section_value, limit=limit)
    return {
        "ok": True,
        "event_id": event_id,
        "section": section_value,
        "point_count": len(points),
        "points": points,
    }


@app.get("/api/live-refresh/past-market-rows")
async def get_live_refresh_past_market_rows(
    event_id: str = Query(..., min_length=1),
    market_family: str | None = Query(default=None),
    section: str | None = Query(default="live"),
    limit: int = Query(default=2000, ge=1, le=10000),
):
    """Return persisted matchup/placement rows for post-event analysis."""
    from src.db import ensure_initialized

    ensure_initialized()
    section_value = _normalize_replay_section(section)
    if section_value is None:
        return _invalid_replay_section_response()
    rows = get_market_prediction_rows_for_event(
        event_id=event_id,
        market_family=market_family,
        section=section_value,
        limit=limit,
    )
    normalized_rows = []
    for row in rows:
        normalized_rows.append(
            {
                **row,
                "is_value": row.get("is_value"),
                "is_value_bool": bool(row.get("is_value")),
            }
        )
    return {
        "ok": True,
        "event_id": event_id,
        "market_family": market_family,
        "section": section_value,
        "row_count": len(normalized_rows),
        "rows": normalized_rows,
    }


@app.get("/api/live-refresh/snapshot")
async def get_live_refresh_snapshot():
    """Return latest always-on snapshot for Live/Upcoming dashboard tabs."""
    from src.db import ensure_initialized
    ensure_initialized()
    from src.autoresearch_settings import get_settings
    from src.live_refresh_policy import resolve_cadence
    from backtester.dashboard_runtime import (
        generate_snapshot_once,
        get_live_refresh_status,
        read_snapshot,
        start_live_refresh,
    )
    settings = (get_settings().get("live_refresh") or {})
    cadence = resolve_cadence(settings)
    stale_after_seconds = max(900, int(cadence.recompute_seconds) + 120)

    def _attempt_fresh_snapshot() -> dict:
        tour = str(settings.get("tour", "pga"))
        status = get_live_refresh_status()
        if not status.get("running") and settings.get("enabled", True) and settings.get("autostart", True):
            start_live_refresh(tour=tour)
        return generate_snapshot_once(tour=tour)

    snapshot = read_snapshot()
    if not snapshot:
        try:
            snapshot = _attempt_fresh_snapshot()
        except Exception as exc:
            _logger.warning("On-demand live snapshot generation failed: %s", exc)
            snapshot = {}
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
    if age_seconds is not None and age_seconds > stale_after_seconds:
        try:
            refreshed = _attempt_fresh_snapshot()
        except Exception as exc:
            _logger.warning("Stale snapshot refresh failed: %s", exc)
            refreshed = {}
        if refreshed:
            snapshot = refreshed
            generated_at = snapshot.get("generated_at")
            age_seconds = None
            if generated_at:
                try:
                    age_seconds = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(generated_at)).total_seconds()))
                except ValueError:
                    age_seconds = None
        if age_seconds is not None and age_seconds > stale_after_seconds:
            return {
                "ok": False,
                "snapshot": None,
                "generated_at": generated_at,
                "age_seconds": age_seconds,
                "stale_after_seconds": stale_after_seconds,
                "stale_reason": (
                    f"Snapshot is stale (>{stale_after_seconds // 60} minutes); "
                    "waiting for a fresh recompute."
                ),
                "fallback_reason": None,
            }
    live_section = snapshot.get("live_tournament", {}) if isinstance(snapshot, dict) else {}
    upcoming_section = snapshot.get("upcoming_tournament", {}) if isinstance(snapshot, dict) else {}
    verification_messages: list[str] = []
    for label, section in (("Live", live_section), ("Upcoming", upcoming_section)):
        eligibility = (section or {}).get("eligibility") or {}
        if eligibility.get("verified") is False:
            summary = str(eligibility.get("summary") or "Field verification failed").strip()
            action = str(eligibility.get("action") or "").strip()
            verification_messages.append(f"{label}: {summary}{' ' + action if action else ''}")

    live_state = (live_section.get("diagnostics") or {}).get("state")
    upcoming_state = (upcoming_section.get("diagnostics") or {}).get("state")
    has_pipeline_degradation = live_state in {"pipeline_error", "eligibility_failed"} or upcoming_state in {"pipeline_error", "eligibility_failed"}
    fallback_sources = {
        "live_fallback",
        "verified_snapshot_fallback",
    }
    active_section = live_section if live_section.get("active") else upcoming_section
    fallback_active = active_section.get("ranking_source") in fallback_sources
    return {
        "ok": True,
        "snapshot": snapshot,
        "generated_at": generated_at,
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "stale_reason": (
            " | ".join(verification_messages)
            if verification_messages
            else (
                "Live snapshot indicates a degraded pipeline state."
                if has_pipeline_degradation
                else None
            )
        ),
        "fallback_reason": (
            "Showing fallback rankings source."
            if fallback_active
            else None
        ),
    }


@app.post("/api/live-refresh/refresh")
async def refresh_live_refresh_snapshot():
    """Force an immediate ingest + recompute cycle."""
    from src.db import ensure_initialized
    ensure_initialized()
    from src.autoresearch_settings import get_settings
    from backtester.dashboard_runtime import generate_snapshot_once, get_live_refresh_status, start_live_refresh

    settings = (get_settings().get("live_refresh") or {})
    tour = str(settings.get("tour", "pga"))
    status = get_live_refresh_status()
    if not status.get("running") and settings.get("enabled", True) and settings.get("autostart", True):
        start_live_refresh(tour=tour)
    try:
        snapshot = generate_snapshot_once(tour=tour)
    except Exception as exc:
        _logger.warning("Manual live snapshot refresh failed: %s", exc)
        return {
            "ok": False,
            "snapshot": None,
            "stale_reason": "Manual refresh failed. Check live-refresh worker logs.",
            "fallback_reason": None,
        }

    generated_at = snapshot.get("generated_at")
    age_seconds = None
    if generated_at:
        try:
            age_seconds = max(0, int((datetime.now(timezone.utc) - datetime.fromisoformat(generated_at)).total_seconds()))
        except ValueError:
            age_seconds = None
    return {
        "ok": True,
        "snapshot": snapshot,
        "generated_at": generated_at,
        "age_seconds": age_seconds,
        "stale_reason": None,
        "fallback_reason": None,
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

# ── Standalone Player Profile (no tournament_id required) ───────────────

@app.get("/api/players/{player_key}/standalone-profile")
async def get_player_standalone_profile(player_key: str):
    """
    Rich player profile that doesn't require an active tournament context.
    Pulls live skill data from DataGolf API + stored round history from DB.
    """
    def _safe_float(v):
        """Convert a value to float, returning None on failure."""
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    from src import db as src_db
    from src.datagolf import (
        fetch_skill_ratings,
        fetch_dg_rankings,
        fetch_approach_skill,
        normalize_name,
    )
    from src.player_normalizer import display_name

    # ── 1. Recent rounds from DB ────────────────────────────────────────
    recent_rounds = src_db.get_player_recent_rounds_by_key(player_key, limit=50)

    # Resolve dg_id from rounds if available
    dg_id = None
    player_display_name = None
    for r in recent_rounds:
        if r.get("dg_id"):
            dg_id = int(r["dg_id"])
        if r.get("player_name") and not player_display_name:
            player_display_name = r["player_name"]
        if dg_id and player_display_name:
            break

    if not player_display_name:
        player_display_name = " ".join(p.capitalize() for p in player_key.split("_") if p)

    # ── 2. Live DG skill ratings ────────────────────────────────────────
    skill_data = None
    try:
        skill_players = fetch_skill_ratings()
        for p in skill_players:
            pkey = normalize_name(p.get("player_name", ""))
            if pkey == player_key:
                skill_data = p
                if not player_display_name:
                    player_display_name = display_name(p.get("player_name", ""))
                break
    except Exception:
        skill_data = None

    # ── 3. DG rankings ──────────────────────────────────────────────────
    ranking_data = None
    try:
        rankings = fetch_dg_rankings()
        for r in rankings:
            pkey = normalize_name(r.get("player_name", ""))
            if pkey == player_key:
                ranking_data = r
                break
    except Exception:
        ranking_data = None

    # ── 4. Approach skill breakdown ─────────────────────────────────────
    approach_data = None
    try:
        approach_players = fetch_approach_skill("l24")
        for p in approach_players:
            pkey = normalize_name(p.get("player_name", ""))
            if pkey == player_key:
                approach_data = p
                break
    except Exception:
        approach_data = None

    # ── 5. Build SG rolling windows from stored rounds ──────────────────
    sg_totals = [r["sg_total"] for r in recent_rounds if r.get("sg_total") is not None]
    sg_rounds_with_meta = []
    event_seen = {}
    for r in recent_rounds:
        if r.get("sg_total") is None:
            continue
        evt = r.get("event_name") or r.get("event_id") or "unknown"
        ev_key = f"{evt}-{r.get('event_completed', '')}"
        if ev_key not in event_seen:
            event_seen[ev_key] = {
                "event_name": r.get("event_name") or evt,
                "event_completed": r.get("event_completed"),
                "fin_text": r.get("fin_text"),
                "sg_values": [],
                "score_values": [],
            }
        event_seen[ev_key]["sg_values"].append(float(r["sg_total"]))
        if r.get("score") is not None:
            event_seen[ev_key]["score_values"].append(int(r["score"]))

    recent_events = []
    for ev_key, ev in list(event_seen.items())[:20]:
        avg_sg = sum(ev["sg_values"]) / len(ev["sg_values"]) if ev["sg_values"] else None
        recent_events.append({
            "event_name": ev["event_name"],
            "event_completed": ev["event_completed"],
            "fin_text": ev["fin_text"],
            "avg_sg_total": round(avg_sg, 3) if avg_sg is not None else None,
            "rounds_played": len(ev["sg_values"]),
        })

    def _avg(vals):
        return round(sum(vals) / len(vals), 3) if vals else None

    windows = {
        "10": _avg(sg_totals[:10]),
        "25": _avg(sg_totals[:25]),
        "50": _avg(sg_totals[:50]),
    }

    # Rolling trend: per-round SG for sparkline (most recent last for L→R chart)
    trend_series = list(reversed(sg_totals[:50]))

    # ── 6. Build approach buckets ───────────────────────────────────────
    approach_buckets = []
    if approach_data:
        bucket_map = {
            "sg_50_100_fw": "50–100 yd (FW)",
            "sg_100_150_fw": "100–150 yd (FW)",
            "sg_150_200_fw": "150–200 yd (FW)",
            "sg_200_fw": "200+ yd (FW)",
            "sg_50_100_rgh": "50–100 yd (Rough)",
            "sg_100_150_rgh": "100–150 yd (Rough)",
            "sg_150_200_rgh": "150–200 yd (Rough)",
            "sg_200_rgh": "200+ yd (Rough)",
        }
        alt_bucket_map = {
            "sg_fw_50_100": "50–100 yd (FW)",
            "sg_fw_100_150": "100–150 yd (FW)",
            "sg_fw_150_200": "150–200 yd (FW)",
            "sg_fw_200": "200+ yd (FW)",
            "sg_rgh_50_100": "50–100 yd (Rough)",
            "sg_rgh_100_150": "100–150 yd (Rough)",
            "sg_rgh_150_200": "150–200 yd (Rough)",
            "sg_rgh_200": "200+ yd (Rough)",
        }
        for key, label in {**bucket_map, **alt_bucket_map}.items():
            val = approach_data.get(key)
            if val is not None:
                fval = _safe_float(val)
                if fval is not None:
                    approach_buckets.append({"key": key, "label": label, "value": round(fval, 3)})

    # ── 7. Assemble skill profile ────────────────────────────────────────
    sg_skills = {}
    if skill_data:
        sg_skills = {
            "sg_total":      _safe_float(skill_data.get("sg_total")),
            "sg_ott":        _safe_float(skill_data.get("sg_ott")),
            "sg_app":        _safe_float(skill_data.get("sg_app")),
            "sg_arg":        _safe_float(skill_data.get("sg_arg")),
            "sg_putt":       _safe_float(skill_data.get("sg_putt")),
            "driving_dist":  _safe_float(skill_data.get("driving_dist")),
            "driving_acc":   _safe_float(skill_data.get("driving_acc")),
        }

    header = {
        "player_display": player_display_name,
        "dg_rank":         int(ranking_data["datagolf_rank"]) if ranking_data and ranking_data.get("datagolf_rank") else None,
        "owgr_rank":       int(ranking_data["owgr_rank"]) if ranking_data and ranking_data.get("owgr_rank") else None,
        "dg_skill_estimate": _safe_float(ranking_data.get("dg_skill_estimate")) if ranking_data else None,
        "primary_tour":    ranking_data.get("primary_tour") if ranking_data else None,
        "rounds_in_db":    len(recent_rounds),
        "events_tracked":  len(recent_events),
    }

    return {
        "player_key": player_key,
        "player_display": player_display_name,
        "header": header,
        "sg_skills": sg_skills,
        "approach_buckets": approach_buckets,
        "rolling_windows": windows,
        "trend_series": trend_series,
        "recent_events": recent_events,
        "ranking_data": ranking_data,
        "has_skill_data": skill_data is not None,
        "has_ranking_data": ranking_data is not None,
        "has_approach_data": approach_data is not None,
    }


@app.get("/api/players/search")
async def search_players(q: str = ""):
    """Search players by name from the rounds database."""
    from src import db as src_db
    conn = src_db.get_conn()
    if q.strip():
        rows = conn.execute(
            """
            SELECT DISTINCT player_key, player_name as player_display
            FROM rounds
            WHERE lower(player_name) LIKE lower(?)
               OR lower(player_key) LIKE lower(?)
            ORDER BY player_name
            LIMIT 40
            """,
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT player_key, player_name as player_display
            FROM rounds
            ORDER BY player_name
            LIMIT 200
            """,
        ).fetchall()
    conn.close()
    return {"players": [dict(r) for r in rows]}

