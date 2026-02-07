"""
SQLite database for storing all parsed data, picks, results, and weights.

Tables:
  tournaments      – one row per tournament
  csv_imports      – one row per imported CSV file
  metrics          – long/narrow: one row per (player, metric_name, source)
  picks            – logged picks with model scores
  results          – actual tournament outcomes
  weight_sets      – stored model weight configurations
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "golf.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            course TEXT,
            date TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS csv_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            filename TEXT NOT NULL,
            file_type TEXT,          -- 'strokes_gained', 'ott', 'approach', etc.
            data_mode TEXT,          -- 'course_specific' or 'recent_form'
            round_window TEXT,       -- 'all', '8', '12', '16', '24', etc.
            row_count INTEGER,
            imported_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            csv_import_id INTEGER REFERENCES csv_imports(id),
            player_key TEXT NOT NULL,
            player_display TEXT,
            metric_category TEXT,    -- matches file_type
            data_mode TEXT,
            round_window TEXT,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            metric_text TEXT         -- for non-numeric values like 'CUT', 'T14'
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_player
            ON metrics(tournament_id, player_key);
        CREATE INDEX IF NOT EXISTS idx_metrics_category
            ON metrics(tournament_id, metric_category, data_mode, round_window);

        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            bet_type TEXT,           -- 'outright', 'top5', 'top10', 'top20', 'matchup', 'group'
            player_key TEXT,
            player_display TEXT,
            opponent_key TEXT,       -- for matchups
            opponent_display TEXT,
            composite_score REAL,
            course_fit_score REAL,
            form_score REAL,
            momentum_score REAL,
            model_prob REAL,
            market_odds TEXT,
            market_implied_prob REAL,
            ev REAL,
            confidence TEXT,         -- 'high', 'medium', 'low'
            reasoning TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            player_key TEXT,
            player_display TEXT,
            finish_position INTEGER,
            finish_text TEXT,        -- 'T14', 'CUT', etc.
            made_cut INTEGER,       -- 1 or 0
            entered_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pick_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_id INTEGER REFERENCES picks(id),
            hit INTEGER,            -- 1 if bet won, 0 if lost
            actual_finish TEXT,
            notes TEXT,
            entered_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS weight_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            weights_json TEXT,       -- JSON blob of all weights
            active INTEGER DEFAULT 0,
            tournament_count INTEGER DEFAULT 0,
            hit_rate REAL,
            roi REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ── Tournament helpers ──────────────────────────────────────────────

def get_or_create_tournament(name: str, course: str = None, date: str = None) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM tournaments WHERE name = ?", (name,)
    ).fetchone()
    if row:
        tid = row["id"]
    else:
        cur = conn.execute(
            "INSERT INTO tournaments (name, course, date) VALUES (?, ?, ?)",
            (name, course, date),
        )
        tid = cur.lastrowid
        conn.commit()
    conn.close()
    return tid


# ── CSV import helpers ──────────────────────────────────────────────

def log_csv_import(tournament_id, filename, file_type, data_mode, round_window, row_count) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO csv_imports
           (tournament_id, filename, file_type, data_mode, round_window, row_count)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (tournament_id, filename, file_type, data_mode, round_window, row_count),
    )
    import_id = cur.lastrowid
    conn.commit()
    conn.close()
    return import_id


def store_metrics(rows: list[dict]):
    """Bulk insert metric rows. Each dict must have the metric table columns."""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT INTO metrics
           (tournament_id, csv_import_id, player_key, player_display,
            metric_category, data_mode, round_window,
            metric_name, metric_value, metric_text)
           VALUES (:tournament_id, :csv_import_id, :player_key, :player_display,
                    :metric_category, :data_mode, :round_window,
                    :metric_name, :metric_value, :metric_text)""",
        rows,
    )
    conn.commit()
    conn.close()


# ── Metrics query helpers ───────────────────────────────────────────

def get_player_metrics(tournament_id: int, player_key: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM metrics
           WHERE tournament_id = ? AND player_key = ?
           ORDER BY metric_category, round_window, metric_name""",
        (tournament_id, player_key),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_players(tournament_id: int) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT player_key FROM metrics WHERE tournament_id = ?",
        (tournament_id,),
    ).fetchall()
    conn.close()
    return [r["player_key"] for r in rows]


def get_metrics_by_category(tournament_id: int, category: str,
                            data_mode: str = None, round_window: str = None) -> list[dict]:
    conn = get_conn()
    sql = "SELECT * FROM metrics WHERE tournament_id = ? AND metric_category = ?"
    params = [tournament_id, category]
    if data_mode:
        sql += " AND data_mode = ?"
        params.append(data_mode)
    if round_window:
        sql += " AND round_window = ?"
        params.append(round_window)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_player_display_names(tournament_id: int) -> dict:
    """Return {player_key: player_display} mapping."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT DISTINCT player_key, player_display FROM metrics
           WHERE tournament_id = ? AND player_display IS NOT NULL""",
        (tournament_id,),
    ).fetchall()
    conn.close()
    return {r["player_key"]: r["player_display"] for r in rows}


# ── Picks / results helpers ─────────────────────────────────────────

def store_picks(picks: list[dict]):
    if not picks:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT INTO picks
           (tournament_id, bet_type, player_key, player_display,
            opponent_key, opponent_display,
            composite_score, course_fit_score, form_score, momentum_score,
            model_prob, market_odds, market_implied_prob, ev,
            confidence, reasoning)
           VALUES (:tournament_id, :bet_type, :player_key, :player_display,
                    :opponent_key, :opponent_display,
                    :composite_score, :course_fit_score, :form_score, :momentum_score,
                    :model_prob, :market_odds, :market_implied_prob, :ev,
                    :confidence, :reasoning)""",
        picks,
    )
    conn.commit()
    conn.close()


def store_results(tournament_id: int, results_list: list[dict]):
    if not results_list:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT INTO results
           (tournament_id, player_key, player_display, finish_position,
            finish_text, made_cut)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (tournament_id, r["player_key"], r["player_display"],
             r.get("finish_position"), r.get("finish_text"), r.get("made_cut"))
            for r in results_list
        ],
    )
    conn.commit()
    conn.close()


# ── Weights helpers ─────────────────────────────────────────────────

DEFAULT_WEIGHTS = {
    # Top-level model weights
    "course_fit": 0.40,
    "form": 0.40,
    "momentum": 0.20,
    # Within course fit
    "course_sg_tot": 0.30,
    "course_sg_app": 0.25,
    "course_sg_ott": 0.20,
    "course_sg_putt": 0.15,
    "course_par_eff": 0.10,
    # Within form (across timeframes)
    "form_16r": 0.35,
    "form_12month": 0.25,
    "form_sim": 0.25,
    "form_rolling": 0.15,
    # Within form (SG sub-categories)
    "form_sg_tot": 0.40,
    "form_sg_app": 0.25,
    "form_sg_ott": 0.15,
    "form_sg_putt": 0.10,
    "form_sg_arg": 0.10,
}


def get_active_weights() -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT weights_json FROM weight_sets WHERE active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["weights_json"])
    return DEFAULT_WEIGHTS.copy()


def save_weights(name: str, weights: dict, active: bool = True):
    conn = get_conn()
    if active:
        conn.execute("UPDATE weight_sets SET active = 0")
    conn.execute(
        "INSERT INTO weight_sets (name, weights_json, active) VALUES (?, ?, ?)",
        (name, json.dumps(weights), 1 if active else 0),
    )
    conn.commit()
    conn.close()


# Initialize on import
init_db()
