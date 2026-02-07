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
                        vb = find_value_bets(composite, best, bet_type=market.replace("top_", "top"))
                        value_bets[market.replace("top_", "top")] = vb
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
.container { max-width: 1100px; margin: 0 auto; padding: 20px; }
h1 { font-size: 1.6em; margin-bottom: 5px; color: #fff; }
h2 { font-size: 1.2em; margin: 20px 0 10px; color: #4ade80; border-bottom: 1px solid #333; padding-bottom: 5px; }
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
    <p style="color:#94a3b8; font-size:0.85em;">Quantitative picks: course fit + form + momentum</p>

    <div class="tabs">
        <div class="tab active" onclick="showTab('upload')">Upload & Analyze</div>
        <div class="tab" onclick="showTab('card')">Betting Card</div>
        <div class="tab" onclick="showTab('results')">Enter Results</div>
        <div class="tab" onclick="showTab('dashboard')">Dashboard</div>
    </div>

    <!-- ── Upload & Analyze ──────────────────────────────── -->
    <div id="tab-upload" class="tab-content active">
        <h2>1. Set Tournament</h2>
        <div class="form-row">
            <div>
                <label>Tournament Name</label>
                <input id="tournament" type="text" placeholder="e.g. WM Phoenix Open 2026" style="width:100%">
            </div>
            <div>
                <label>Course Name</label>
                <input id="course" type="text" placeholder="e.g. TPC Scottsdale" style="width:100%">
            </div>
        </div>

        <h2>2. Upload Betsperts CSVs</h2>
        <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
            <input type="file" id="fileInput" multiple accept=".csv">
            <p style="font-size:1.1em; margin-bottom:8px;">Drop CSV files here or click to select</p>
            <p style="font-size:0.85em;">Cheat sheets, sim, 12r, 24r, course data, rolling averages — drop them all</p>
        </div>
        <div id="fileList" class="file-list"></div>

        <h2>3. Run Model</h2>
        <button id="analyzeBtn" onclick="runAnalysis()" disabled>Analyze</button>
        <div id="analyzeStatus"></div>
    </div>

    <!-- ── Betting Card ──────────────────────────────────── -->
    <div id="tab-card" class="tab-content">
        <div id="cardContent">
            <div class="status info">No analysis run yet. Go to Upload & Analyze first.</div>
        </div>
    </div>

    <!-- ── Enter Results ─────────────────────────────────── -->
    <div id="tab-results" class="tab-content">
        <h2>Enter Tournament Results</h2>
        <div style="margin-bottom:15px;">
            <label>Tournament</label>
            <select id="resultsTournament" style="width:100%;">
                <option value="">Loading...</option>
            </select>
        </div>
        <label>Results (one per line: Player Name, Finish)</label>
        <textarea id="resultsText" class="results-input" placeholder="Scottie Scheffler, 1&#10;Xander Schauffele, T3&#10;Tom Kim, CUT&#10;..."></textarea>
        <div style="margin-top:10px;">
            <button onclick="submitResults()">Save Results</button>
        </div>
        <div id="resultsStatus"></div>
    </div>

    <!-- ── Dashboard ─────────────────────────────────────── -->
    <div id="tab-dashboard" class="tab-content">
        <div id="dashboardContent">
            <div class="status info">Loading...</div>
        </div>
    </div>
</div>

<script>
// ── Tab switching ──
function showTab(name) {
    document.querySelectorAll('.tab').forEach((t, i) => {
        t.classList.toggle('active', t.textContent.toLowerCase().includes(name.substring(0, 4)));
    });
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');

    if (name === 'card') loadCard();
    if (name === 'results') loadTournaments();
    if (name === 'dashboard') loadDashboard();
}

// ── File upload ──
let selectedFiles = [];
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');

dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', e => addFiles(e.target.files));

function addFiles(fileListObj) {
    for (const f of fileListObj) {
        if (f.name.toLowerCase().endsWith('.csv') && !selectedFiles.some(s => s.name === f.name)) {
            selectedFiles.push(f);
        }
    }
    renderFiles();
}

function renderFiles() {
    fileList.innerHTML = selectedFiles.map(f =>
        '<div class="file-item">' + f.name + '</div>'
    ).join('');
    document.getElementById('analyzeBtn').disabled =
        !selectedFiles.length || !document.getElementById('tournament').value;
}

document.getElementById('tournament').addEventListener('input', renderFiles);
document.getElementById('course').addEventListener('input', renderFiles);

// ── Run analysis ──
async function runAnalysis() {
    const btn = document.getElementById('analyzeBtn');
    const status = document.getElementById('analyzeStatus');
    btn.disabled = true;
    status.innerHTML = '<div class="status loading"><span class="spinner"></span>Running model... this may take 10-20 seconds</div>';

    const form = new FormData();
    form.append('tournament', document.getElementById('tournament').value);
    form.append('course', document.getElementById('course').value);
    for (const f of selectedFiles) form.append('files', f);

    try {
        const resp = await fetch('/api/analyze', { method: 'POST', body: form });
        const data = await resp.json();
        if (data.error) {
            status.innerHTML = '<div class="status error">' + data.error + '</div>';
            btn.disabled = false;
            return;
        }
        let html = '<div class="status success">Analysis complete: ' + data.players_scored + ' players scored from ' + data.files_imported + ' files.</div>';
        if (data.files_skipped && data.files_skipped.length) {
            html += '<div class="status info">Skipped (already imported): ' + data.files_skipped.join(', ') + '</div>';
        }
        html += '<div style="margin-top:10px;"><button onclick="showTab(\'card\')">View Betting Card →</button></div>';
        status.innerHTML = html;
    } catch (e) {
        status.innerHTML = '<div class="status error">Error: ' + e.message + '</div>';
        btn.disabled = false;
    }
}

// ── Betting Card ──
async function loadCard() {
    const el = document.getElementById('cardContent');
    try {
        const resp = await fetch('/api/card');
        const data = await resp.json();
        if (data.error) {
            el.innerHTML = '<div class="status info">' + data.error + '</div>';
            return;
        }
        renderCard(data, el);
    } catch (e) {
        el.innerHTML = '<div class="status error">Error loading card</div>';
    }
}

function trendIcon(dir) {
    const map = { hot: '<span class="trend-hot">↑↑</span>', warming: '<span class="trend-warm">↑</span>',
                  cooling: '<span class="trend-cool">↓</span>', cold: '<span class="trend-cold">↓↓</span>' };
    return map[dir] || '—';
}

function reason(r) {
    let parts = [];
    if (r.course_fit > 65) parts.push('course ' + r.course_fit.toFixed(0));
    if (r.form > 65) parts.push('form ' + r.form.toFixed(0));
    if (r.momentum_direction === 'hot') parts.push('trending hot (+' + (r.momentum_trend||0).toFixed(0) + ')');
    if (r.momentum_direction === 'cold') parts.push('cold (' + (r.momentum_trend||0).toFixed(0) + ')');
    if ((r.course_rounds||0) >= 16) parts.push(Math.round(r.course_rounds) + ' rds');
    return parts.join(' · ') || 'composite edge';
}

function renderCard(data, el) {
    const c = data.composite;
    const vb = data.value_bets || {};
    let html = '<h2>' + data.tournament + ' — ' + (data.course || '') + '</h2>';
    html += '<p style="color:#94a3b8;font-size:0.8em;">Generated: ' + new Date(data.timestamp).toLocaleString() + ' · Weights: course ' + ((data.weights.course_fit||0.4)*100).toFixed(0) + '% / form ' + ((data.weights.form||0.4)*100).toFixed(0) + '% / momentum ' + ((data.weights.momentum||0.2)*100).toFixed(0) + '%</p>';

    // Rankings table
    html += '<h2>Model Rankings (Top 25)</h2><table><tr><th>#</th><th>Player</th><th>Composite</th><th>Course</th><th>Form</th><th>Momentum</th><th>Trend</th></tr>';
    for (let i = 0; i < Math.min(25, c.length); i++) {
        const r = c[i];
        const cls = r.rank === 1 ? 'rank-1' : r.rank <= 5 ? 'rank-top5' : '';
        html += '<tr class="' + cls + '"><td class="num">' + r.rank + '</td><td>' + r.player_display + '</td><td class="num">' + r.composite.toFixed(1) + '</td><td class="num">' + r.course_fit.toFixed(1) + '</td><td class="num">' + r.form.toFixed(1) + '</td><td class="num">' + r.momentum.toFixed(1) + '</td><td>' + trendIcon(r.momentum_direction) + '</td></tr>';
    }
    html += '</table>';

    // Picks sections
    const sections = [
        { title: 'Outright Winner', n: 5 },
        { title: 'Top 5 Finish', n: 6 },
        { title: 'Top 10 Finish', n: 10 },
        { title: 'Top 20 Finish', n: 15 },
    ];
    for (const sec of sections) {
        html += '<h2>' + sec.title + '</h2><div class="card-section">';
        for (let i = 0; i < Math.min(sec.n, c.length); i++) {
            const r = c[i];
            html += '<div class="pick"><span class="name">#' + r.rank + ' ' + r.player_display + '</span><span class="reason">' + reason(r) + '</span></div>';
        }
        html += '</div>';
    }

    // Matchups
    html += '<h2>Matchup Edges</h2><div class="card-section">';
    const matchups = findMatchups(c);
    for (const m of matchups.slice(0, 8)) {
        html += '<div class="pick matchup"><span class="name">' + m.pick + '</span><span class="vs">over</span><span>' + m.opp + '</span><span class="edge">+' + m.edge.toFixed(1) + ' pts · ' + m.reason + '</span></div>';
    }
    html += '</div>';

    // Fades
    html += '<h2>Fades (Avoid)</h2><div class="card-section">';
    for (let i = c.length - 10; i < c.length; i++) {
        if (i < 0) continue;
        const r = c[i];
        if (r.composite < 42 || r.momentum_direction === 'cold') {
            html += '<div class="pick"><span class="name fade">' + r.player_display + '</span><span class="reason">composite ' + r.composite.toFixed(1) + ' · ' + reason(r) + '</span></div>';
        }
    }
    html += '</div>';

    el.innerHTML = html;
}

function findMatchups(composite) {
    let matchups = [];
    const seen = new Set();
    for (let i = 0; i < composite.length; i++) {
        if (seen.has(composite[i].player_key)) continue;
        for (let j = i + 1; j < Math.min(i + 30, composite.length); j++) {
            if (seen.has(composite[j].player_key)) continue;
            const gap = composite[i].composite - composite[j].composite;
            if (gap < 4) continue;
            let reasons = [];
            if (composite[i].course_fit - composite[j].course_fit > 5) reasons.push('course +' + (composite[i].course_fit - composite[j].course_fit).toFixed(0));
            if (composite[i].form - composite[j].form > 5) reasons.push('form +' + (composite[i].form - composite[j].form).toFixed(0));
            matchups.push({ pick: composite[i].player_display, pick_key: composite[i].player_key, opp: composite[j].player_display, opp_key: composite[j].player_key, edge: gap, reason: reasons.join(', ') || 'composite +' + gap.toFixed(0) });
            seen.add(composite[i].player_key);
            break;
        }
    }
    return matchups.sort((a, b) => b.edge - a.edge);
}

// ── Results ──
async function loadTournaments() {
    try {
        const resp = await fetch('/api/tournaments');
        const data = await resp.json();
        const sel = document.getElementById('resultsTournament');
        sel.innerHTML = data.map(t => '<option value="' + t.name + '">' + t.name + (t.course ? ' (' + t.course + ')' : '') + '</option>').join('');
    } catch (e) {}
}

async function submitResults() {
    const tournament = document.getElementById('resultsTournament').value;
    const text = document.getElementById('resultsText').value;
    const status = document.getElementById('resultsStatus');

    if (!tournament || !text.trim()) {
        status.innerHTML = '<div class="status error">Enter a tournament and results</div>';
        return;
    }

    const lines = text.trim().split('\\n').filter(l => l.trim());
    const results = lines.map(l => {
        const parts = l.split(',').map(p => p.trim());
        return { player: parts[0] || '', finish: parts[1] || '' };
    }).filter(r => r.player && r.finish);

    status.innerHTML = '<div class="status loading"><span class="spinner"></span>Saving...</div>';

    try {
        const resp = await fetch('/api/results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tournament, results }),
        });
        const data = await resp.json();
        if (data.error) {
            status.innerHTML = '<div class="status error">' + data.error + '</div>';
        } else {
            status.innerHTML = '<div class="status success">Saved ' + data.results_saved + ' results. Scored ' + data.picks_scored + ' picks: ' + data.hits + ' hits (' + data.hit_rate + ')</div>';
        }
    } catch (e) {
        status.innerHTML = '<div class="status error">Error: ' + e.message + '</div>';
    }
}

// ── Dashboard ──
async function loadDashboard() {
    const el = document.getElementById('dashboardContent');
    try {
        const resp = await fetch('/api/dashboard');
        const data = await resp.json();
        renderDashboard(data, el);
    } catch (e) {
        el.innerHTML = '<div class="status error">Error loading dashboard</div>';
    }
}

function renderDashboard(data, el) {
    const a = data.analysis || {};
    let html = '<h2>Performance</h2>';

    html += '<div class="stats-grid">';
    html += '<div class="stat-box"><div class="number">' + (a.total_picks || 0) + '</div><div class="label">Total Picks</div></div>';
    html += '<div class="stat-box"><div class="number">' + (a.total_hits || 0) + '</div><div class="label">Hits</div></div>';
    html += '<div class="stat-box"><div class="number">' + (a.total_picks ? (a.hit_rate * 100).toFixed(1) + '%' : '—') + '</div><div class="label">Hit Rate</div></div>';
    html += '<div class="stat-box"><div class="number">' + (data.tournaments || []).length + '</div><div class="label">Tournaments</div></div>';
    html += '</div>';

    // Insights (plain English)
    const insights = a.insights || [];
    if (insights.length) {
        html += '<h2>What the Model Has Learned</h2><div class="card-section">';
        for (const ins of insights) {
            html += '<div class="pick" style="padding:5px 0;"><span style="color:#4ade80;margin-right:8px;">→</span>' + ins + '</div>';
        }
        html += '</div>';
    }

    // By bet type
    if (a.by_bet_type && Object.keys(a.by_bet_type).length) {
        html += '<h2>By Bet Type</h2><table><tr><th>Type</th><th>Picks</th><th>Hits</th><th>Rate</th></tr>';
        for (const [bt, s] of Object.entries(a.by_bet_type)) {
            html += '<tr><td>' + bt + '</td><td class="num">' + s.picks + '</td><td class="num">' + s.hits + '</td><td class="num">' + (s.hit_rate * 100).toFixed(1) + '%</td></tr>';
        }
        html += '</table>';
    }

    // Factor analysis
    const fa = a.factor_analysis;
    if (fa && Object.keys(fa).length) {
        html += '<h2>Factor Analysis</h2><p style="color:#94a3b8;font-size:0.85em;">Higher edge = that factor is more predictive of hits. Predictive power shows separation between hits and misses.</p>';
        html += '<table><tr><th>Factor</th><th>Avg Hit</th><th>Avg Miss</th><th>Edge</th><th>Power</th></tr>';
        for (const [f, s] of Object.entries(fa)) {
            const edgeColor = s.edge > 0 ? '#4ade80' : s.edge < 0 ? '#ef4444' : '#94a3b8';
            const pp = s.predictive_power !== undefined ? s.predictive_power.toFixed(2) : '—';
            html += '<tr><td>' + f + '</td><td class="num">' + s.avg_hit.toFixed(1) + '</td><td class="num">' + s.avg_miss.toFixed(1) + '</td><td class="num" style="color:' + edgeColor + '">' + (s.edge > 0 ? '+' : '') + s.edge.toFixed(1) + '</td><td class="num">' + pp + '</td></tr>';
        }
        html += '</table>';
    }

    // Score thresholds
    const th = a.score_thresholds;
    if (th && Object.keys(th).length) {
        html += '<h2>Score Thresholds</h2><p style="color:#94a3b8;font-size:0.85em;">Do higher-ranked picks hit more? This tells us if the composite score is working.</p>';
        html += '<table><tr><th>Group</th><th>Min Composite</th><th>Picks</th><th>Hits</th><th>Rate</th></tr>';
        for (const [label, t] of Object.entries(th)) {
            const rateColor = t.hit_rate > (a.hit_rate || 0) ? '#4ade80' : '#ef4444';
            html += '<tr><td>' + label.replace(/_/g, ' ') + '</td><td class="num">' + t.composite_cutoff + '</td><td class="num">' + t.picks_above + '</td><td class="num">' + t.hits_above + '</td><td class="num" style="color:' + rateColor + '">' + (t.hit_rate * 100).toFixed(1) + '%</td></tr>';
        }
        html += '</table>';
    }

    // Data source insights
    const di = a.data_insights;
    if (di) {
        html += '<h2>Data Quality Impact</h2><p style="color:#94a3b8;font-size:0.85em;">Does uploading more data improve picks?</p>';
        html += '<table><tr><th>Data Available</th><th>Tournaments</th><th>Avg Hit Rate</th></tr>';
        if (di.with_course_data) html += '<tr><td>With course-specific data</td><td class="num">' + di.with_course_data.tournaments + '</td><td class="num">' + (di.with_course_data.avg_hit_rate * 100).toFixed(1) + '%</td></tr>';
        if (di.without_course_data) html += '<tr><td>Without course data</td><td class="num">' + di.without_course_data.tournaments + '</td><td class="num">' + (di.without_course_data.avg_hit_rate * 100).toFixed(1) + '%</td></tr>';
        if (di['5plus_files']) html += '<tr><td>5+ CSV files uploaded</td><td class="num">' + di['5plus_files'].tournaments + '</td><td class="num">' + (di['5plus_files'].avg_hit_rate * 100).toFixed(1) + '%</td></tr>';
        if (di.under_5_files) html += '<tr><td>Under 5 CSV files</td><td class="num">' + di.under_5_files.tournaments + '</td><td class="num">' + (di.under_5_files.avg_hit_rate * 100).toFixed(1) + '%</td></tr>';
        html += '</table>';
    }

    // Weights
    const w = data.weights || {};
    html += '<h2>Current Weights</h2>';
    html += '<div class="stats-grid">';
    html += '<div class="stat-box"><div class="number">' + ((w.course_fit || 0.4) * 100).toFixed(0) + '%</div><div class="label">Course Fit</div></div>';
    html += '<div class="stat-box"><div class="number">' + ((w.form || 0.4) * 100).toFixed(0) + '%</div><div class="label">Form</div></div>';
    html += '<div class="stat-box"><div class="number">' + ((w.momentum || 0.2) * 100).toFixed(0) + '%</div><div class="label">Momentum</div></div>';
    html += '</div>';
    html += '<div style="margin-top:15px;"><button class="secondary" onclick="doRetune()">Retune Weights from Results</button> <span id="retuneStatus" style="margin-left:10px;font-size:0.85em;"></span></div>';

    // Tournaments
    html += '<h2>Tournaments</h2><table><tr><th>Name</th><th>Course</th><th>Picks</th><th>Results</th><th>Hits</th></tr>';
    for (const t of (data.tournaments || [])) {
        html += '<tr><td>' + t.name + '</td><td>' + (t.course || '—') + '</td><td class="num">' + t.picks + '</td><td class="num">' + t.results + '</td><td class="num">' + t.hits + '/' + t.outcomes + '</td></tr>';
    }
    html += '</table>';

    el.innerHTML = html;
}

async function doRetune() {
    const el = document.getElementById('retuneStatus');
    el.innerHTML = '<span class="spinner"></span>Retuning...';
    try {
        const resp = await fetch('/api/retune', { method: 'POST' });
        const data = await resp.json();
        if (data.message) el.innerHTML = data.message;
        else if (data.saved) { el.innerHTML = '<span style="color:#4ade80;">Weights updated!</span>'; loadDashboard(); }
        else el.innerHTML = 'Dry run complete.';
    } catch (e) { el.innerHTML = '<span style="color:#ef4444;">Error</span>'; }
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    init_db()
    print("\\n  Golf Betting Model — Web UI")
    print("  Open in browser: http://localhost:8000\\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
