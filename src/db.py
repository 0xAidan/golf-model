"""
SQLite database for storing all parsed data, picks, results, and weights.

Tables:
  tournaments             – one row per tournament
  csv_imports             – one row per imported CSV / API import
  metrics                 – long/narrow: one row per (player, metric_name, source)
  picks                   – logged picks with model scores
  results                 – actual tournament outcomes
  pick_outcomes           – hit/miss + profit for each pick
  weight_sets             – stored model weight configurations
  rounds                  – round-level data from Data Golf historical API
  course_weight_profiles  – per-course learned weight overrides
  prediction_log          – calibration tracking (model vs market vs actual)
  ai_memory               – persistent AI brain memory
  ai_decisions            – logged AI analysis/decisions
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
            source TEXT DEFAULT 'betsperts',  -- 'betsperts', 'datagolf', 'computed'
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
            odds_decimal REAL,      -- odds at time of pick
            stake REAL,             -- units wagered
            profit REAL,            -- actual P/L
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

        -- ═══ Data Golf round-level data ═══
        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dg_id INTEGER NOT NULL,
            player_name TEXT,
            player_key TEXT,            -- normalize_name(player_name)
            tour TEXT,
            season INTEGER,
            year INTEGER,
            event_id TEXT,
            event_name TEXT,
            event_completed TEXT,        -- date string YYYY-MM-DD
            course_name TEXT,
            course_num INTEGER,
            course_par INTEGER,
            round_num INTEGER,           -- 1, 2, 3, 4
            score INTEGER,
            sg_total REAL,
            sg_ott REAL,
            sg_app REAL,
            sg_arg REAL,
            sg_putt REAL,
            sg_t2g REAL,
            driving_dist REAL,
            driving_acc REAL,
            gir REAL,
            scrambling REAL,
            prox_fw REAL,
            prox_rgh REAL,
            great_shots REAL,
            poor_shots REAL,
            birdies INTEGER,
            pars INTEGER,
            bogies INTEGER,
            doubles_or_worse INTEGER,
            eagles_or_better INTEGER,
            fin_text TEXT,               -- final finish position for the event
            teetime TEXT,
            start_hole INTEGER,
            UNIQUE(dg_id, event_id, year, round_num)
        );

        CREATE INDEX IF NOT EXISTS idx_rounds_player
            ON rounds(dg_id, event_completed DESC);
        CREATE INDEX IF NOT EXISTS idx_rounds_course
            ON rounds(course_num, dg_id);
        CREATE INDEX IF NOT EXISTS idx_rounds_event
            ON rounds(event_id, year);
        CREATE INDEX IF NOT EXISTS idx_rounds_player_key
            ON rounds(player_key, event_completed DESC);

        -- ═══ Course-specific learned weights ═══
        CREATE TABLE IF NOT EXISTS course_weight_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_num INTEGER,
            course_name TEXT,
            weights_json TEXT,           -- course-specific weight overrides
            tournaments_used INTEGER,    -- how many tournaments of data
            last_updated TEXT DEFAULT (datetime('now')),
            confidence REAL              -- 0-1, based on sample size
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_course_weights_num
            ON course_weight_profiles(course_num);

        -- ═══ Calibration / prediction tracking ═══
        CREATE TABLE IF NOT EXISTS prediction_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            player_key TEXT,
            bet_type TEXT,
            model_prob REAL,             -- our composite probability
            dg_prob REAL,                -- data golf's probability
            market_implied_prob REAL,    -- from odds
            actual_outcome INTEGER,      -- 1=hit, 0=miss
            odds_decimal REAL,
            profit REAL,                 -- actual P/L if bet at those odds
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ═══ AI brain persistent memory ═══
        CREATE TABLE IF NOT EXISTS ai_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,          -- 'pebble_beach', 'top10_strategy', etc.
            insight TEXT NOT NULL,
            source_tournament_id INTEGER,
            confidence REAL,             -- 0-1, decays over time
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT              -- insights fade; recency matters
        );

        CREATE INDEX IF NOT EXISTS idx_ai_memory_topic
            ON ai_memory(topic, confidence DESC);

        CREATE TABLE IF NOT EXISTS ai_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            phase TEXT,                  -- 'pre_analysis', 'betting_decisions', 'post_review'
            input_summary TEXT,          -- abbreviated context sent to AI
            output_json TEXT,            -- full AI response
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            profile_name TEXT,
            inputs_json TEXT,
            status TEXT DEFAULT 'running',
            started_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT,
            sync_metrics INTEGER,
            players_scored INTEGER,
            value_bets INTEGER,
            card_path TEXT,
            ai_enabled INTEGER,
            ai_cost_usd REAL,
            api_spend_usd REAL,
            dg_payload_hash TEXT,
            duration_seconds REAL,
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_runs_started
            ON runs(started_at DESC);
    """)
    conn.commit()

    # ── Migrations for existing databases ──
    _run_migrations(conn)

    conn.close()


def _run_migrations(conn: sqlite3.Connection):
    """Add columns/tables that may be missing in older databases."""
    # Add source column to csv_imports if missing
    try:
        conn.execute("SELECT source FROM csv_imports LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE csv_imports ADD COLUMN source TEXT DEFAULT 'betsperts'")
        conn.commit()

    # Add profit tracking columns to pick_outcomes if missing
    for col, col_type, default in [
        ("odds_decimal", "REAL", None),
        ("stake", "REAL", None),
        ("profit", "REAL", None),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM pick_outcomes LIMIT 1")
        except sqlite3.OperationalError:
            default_clause = f" DEFAULT {default}" if default is not None else ""
            conn.execute(f"ALTER TABLE pick_outcomes ADD COLUMN {col} {col_type}{default_clause}")
            conn.commit()


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

def log_csv_import(tournament_id, filename, file_type, data_mode, round_window,
                   row_count, source="betsperts") -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO csv_imports
           (tournament_id, filename, file_type, data_mode, round_window, row_count, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (tournament_id, filename, file_type, data_mode, round_window, row_count, source),
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


# ── Rounds helpers (Data Golf historical data) ─────────────────────

def store_rounds(rounds_list: list[dict]):
    """Bulk insert round data. Uses INSERT OR IGNORE for dedup on UNIQUE constraint."""
    if not rounds_list:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT OR IGNORE INTO rounds
           (dg_id, player_name, player_key, tour, season, year,
            event_id, event_name, event_completed,
            course_name, course_num, course_par, round_num,
            score, sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g,
            driving_dist, driving_acc, gir, scrambling, prox_fw, prox_rgh,
            great_shots, poor_shots,
            birdies, pars, bogies, doubles_or_worse, eagles_or_better,
            fin_text, teetime, start_hole)
           VALUES (:dg_id, :player_name, :player_key, :tour, :season, :year,
                    :event_id, :event_name, :event_completed,
                    :course_name, :course_num, :course_par, :round_num,
                    :score, :sg_total, :sg_ott, :sg_app, :sg_arg, :sg_putt, :sg_t2g,
                    :driving_dist, :driving_acc, :gir, :scrambling, :prox_fw, :prox_rgh,
                    :great_shots, :poor_shots,
                    :birdies, :pars, :bogies, :doubles_or_worse, :eagles_or_better,
                    :fin_text, :teetime, :start_hole)""",
        rounds_list,
    )
    conn.commit()
    conn.close()


def get_player_recent_rounds(dg_id: int, limit: int = 24) -> list[dict]:
    """Get last N rounds for a player, ordered most recent first."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rounds
           WHERE dg_id = ? AND sg_total IS NOT NULL
           ORDER BY event_completed DESC, round_num DESC
           LIMIT ?""",
        (dg_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_player_recent_rounds_by_key(player_key: str, limit: int = 24) -> list[dict]:
    """Get last N rounds for a player by normalized name key."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rounds
           WHERE player_key = ? AND sg_total IS NOT NULL
           ORDER BY event_completed DESC, round_num DESC
           LIMIT ?""",
        (player_key, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_player_course_rounds(dg_id: int, course_num: int) -> list[dict]:
    """Get all rounds at a specific course for a player."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM rounds
           WHERE dg_id = ? AND course_num = ? AND sg_total IS NOT NULL
           ORDER BY event_completed DESC, round_num DESC""",
        (dg_id, course_num),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_rounds_backfill_status() -> list[dict]:
    """Show which tours/years are stored and how many rounds each has."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT tour, year, COUNT(*) as round_count,
                  COUNT(DISTINCT dg_id) as player_count,
                  COUNT(DISTINCT event_id) as event_count
           FROM rounds
           GROUP BY tour, year
           ORDER BY tour, year"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_rounds_count() -> int:
    """Total rounds stored."""
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM rounds").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_dg_id_for_player(player_key: str) -> int | None:
    """Look up dg_id from rounds table by player_key."""
    conn = get_conn()
    row = conn.execute(
        "SELECT dg_id FROM rounds WHERE player_key = ? LIMIT 1",
        (player_key,),
    ).fetchone()
    conn.close()
    return row["dg_id"] if row else None


def get_event_results(event_id: str, year: int) -> list[dict]:
    """Get finish positions for all players in an event (for auto-results)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT DISTINCT dg_id, player_name, player_key, fin_text
           FROM rounds
           WHERE event_id = ? AND year = ?""",
        (event_id, year),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Course weight profile helpers ──────────────────────────────────

def get_course_weight_profile(course_num: int) -> dict | None:
    """Get learned weight profile for a course."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM course_weight_profiles WHERE course_num = ?",
        (course_num,),
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["weights"] = json.loads(result["weights_json"])
        return result
    return None


def save_course_weight_profile(course_num: int, course_name: str,
                               weights: dict, tournaments_used: int,
                               confidence: float):
    """Save or update course-specific weight profile."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO course_weight_profiles
           (course_num, course_name, weights_json, tournaments_used, confidence, last_updated)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(course_num) DO UPDATE SET
               weights_json = excluded.weights_json,
               tournaments_used = excluded.tournaments_used,
               confidence = excluded.confidence,
               last_updated = datetime('now')""",
        (course_num, course_name, json.dumps(weights), tournaments_used, confidence),
    )
    conn.commit()
    conn.close()


# ── Prediction log helpers ─────────────────────────────────────────

def log_predictions(predictions: list[dict]):
    """Store predictions for calibration tracking."""
    if not predictions:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT INTO prediction_log
           (tournament_id, player_key, bet_type, model_prob, dg_prob,
            market_implied_prob, actual_outcome, odds_decimal, profit)
           VALUES (:tournament_id, :player_key, :bet_type, :model_prob, :dg_prob,
                    :market_implied_prob, :actual_outcome, :odds_decimal, :profit)""",
        predictions,
    )
    conn.commit()
    conn.close()


def get_calibration_data(min_tournaments: int = 3) -> list[dict]:
    """Get all prediction log entries for calibration analysis."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM prediction_log ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AI memory helpers ──────────────────────────────────────────────

def store_ai_memory(topic: str, insight: str, source_tournament_id: int = None,
                    confidence: float = 0.5, expires_days: int = 180):
    """Store an AI brain learning/insight."""
    conn = get_conn()
    expires_at = None
    if expires_days:
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
    conn.execute(
        """INSERT INTO ai_memory (topic, insight, source_tournament_id, confidence, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (topic, insight, source_tournament_id, confidence, expires_at),
    )
    conn.commit()
    conn.close()


def get_ai_memories(topics: list[str] = None, limit: int = 50) -> list[dict]:
    """Retrieve relevant AI memories, filtered by topic. Excludes expired."""
    conn = get_conn()
    sql = """SELECT * FROM ai_memory
             WHERE (expires_at IS NULL OR expires_at > datetime('now'))"""
    params = []
    if topics:
        placeholders = ",".join("?" for _ in topics)
        sql += f" AND topic IN ({placeholders})"
        params.extend(topics)
    sql += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_ai_memory_topics() -> list[str]:
    """Get all distinct memory topics."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT DISTINCT topic FROM ai_memory
           WHERE expires_at IS NULL OR expires_at > datetime('now')
           ORDER BY topic"""
    ).fetchall()
    conn.close()
    return [r["topic"] for r in rows]


# ── AI decisions helpers ───────────────────────────────────────────

def store_ai_decision(tournament_id: int, phase: str,
                      input_summary: str, output_json: str):
    """Log an AI brain decision/analysis."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO ai_decisions (tournament_id, phase, input_summary, output_json)
           VALUES (?, ?, ?, ?)""",
        (tournament_id, phase, input_summary, output_json),
    )
    conn.commit()
    conn.close()


def get_ai_decisions(tournament_id: int = None, phase: str = None) -> list[dict]:
    """Retrieve AI decisions, optionally filtered."""
    conn = get_conn()
    sql = "SELECT * FROM ai_decisions WHERE 1=1"
    params = []
    if tournament_id:
        sql += " AND tournament_id = ?"
        params.append(tournament_id)
    if phase:
        sql += " AND phase = ?"
        params.append(phase)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Run logging helpers ───────────────────────────────────────────

def log_run_start(tournament_id: int, profile_name: str | None, inputs: dict) -> int:
    """Insert a row into the runs table and return its id."""
    conn = get_conn()
    inputs_json = json.dumps(inputs, sort_keys=True, default=str)
    cur = conn.execute(
        """INSERT INTO runs (tournament_id, profile_name, inputs_json)
            VALUES (?, ?, ?)""",
        (tournament_id, profile_name, inputs_json),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_run_finish(run_id: int, status: str, **fields):
    """Update a run row with completion metadata."""
    conn = get_conn()
    updates = ["status = ?", "finished_at = datetime('now')"]
    params = [status]
    for column, value in fields.items():
        if value is None:
            continue
        updates.append(f"{column} = ?")
        params.append(value)
    params.append(run_id)
    sql = f"UPDATE runs SET {', '.join(updates)} WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()


# ── Weights helpers with course-aware lookup ───────────────────────

def get_weights_for_course(course_num: int = None) -> dict:
    """
    Get weights, blending global with course-specific if available.

    If a course_weight_profile exists and has enough confidence,
    blend it with global weights.
    """
    global_weights = get_active_weights()
    if course_num is None:
        return global_weights

    profile = get_course_weight_profile(course_num)
    if profile is None or profile.get("confidence", 0) < 0.3:
        return global_weights

    # Blend: higher confidence = more course-specific influence
    conf = profile["confidence"]
    course_w = profile["weights"]
    blended = {}
    for key in global_weights:
        if key in course_w:
            blended[key] = round(
                global_weights[key] * (1 - conf) + course_w[key] * conf, 4
            )
        else:
            blended[key] = global_weights[key]
    return blended


# Initialize on import
init_db()
