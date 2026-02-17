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


_DB_INITIALIZED = False


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
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
            year INTEGER,
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

        -- ═══ Pipeline run logging ═══
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            status TEXT,
            result_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ═══ Historical data (backtester) ═══
        CREATE TABLE IF NOT EXISTS historical_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_dg_id INTEGER,
            player_name TEXT, market TEXT, book TEXT,
            open_line REAL, close_line REAL, outcome TEXT,
            UNIQUE(event_id, year, player_dg_id, market, book)
        );

        CREATE TABLE IF NOT EXISTS historical_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_dg_id INTEGER,
            player_name TEXT,
            win_prob REAL, top5_prob REAL, top10_prob REAL,
            top20_prob REAL, make_cut_prob REAL, model_type TEXT,
            actual_finish TEXT,
            UNIQUE(event_id, year, player_dg_id, model_type)
        );

        CREATE TABLE IF NOT EXISTS historical_event_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, event_name TEXT,
            course_id TEXT, course_name TEXT, tour TEXT,
            start_date TEXT, end_date TEXT,
            latitude REAL, longitude REAL,
            UNIQUE(event_id, year)
        );

        CREATE TABLE IF NOT EXISTS backfill_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT, event_id TEXT, year INTEGER,
            status TEXT, fetched_at TEXT DEFAULT (datetime('now')),
            UNIQUE(table_name, event_id, year)
        );

        CREATE TABLE IF NOT EXISTS tournament_weather (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, date TEXT, hour INTEGER,
            temperature_c REAL, wind_speed_kmh REAL, wind_gusts_kmh REAL,
            wind_direction INTEGER, precipitation_mm REAL,
            humidity_pct REAL, cloud_cover_pct REAL, pressure_hpa REAL,
            UNIQUE(event_id, year, date, hour)
        );

        CREATE TABLE IF NOT EXISTS tournament_weather_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, round_num INTEGER,
            avg_wind_kmh REAL, max_gust_kmh REAL,
            total_precip_mm REAL, avg_temp_c REAL,
            am_wave_wind REAL, pm_wave_wind REAL,
            conditions_rating REAL,
            UNIQUE(event_id, year, round_num)
        );

        CREATE TABLE IF NOT EXISTS equipment_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_key TEXT, change_date TEXT, category TEXT,
            old_equipment TEXT, new_equipment TEXT,
            source TEXT, ai_impact_assessment TEXT,
            performance_delta_sg REAL, measured_after_rounds INTEGER,
            UNIQUE(player_key, change_date, category)
        );

        CREATE TABLE IF NOT EXISTS course_encyclopedia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id TEXT, course_name TEXT,
            latitude REAL, longitude REAL, elevation_m REAL,
            grass_type_fairway TEXT, grass_type_greens TEXT,
            green_speed TEXT, fairway_width TEXT,
            yardage INTEGER, par INTEGER,
            prevailing_wind TEXT, course_type TEXT,
            sg_ott_importance REAL, sg_app_importance REAL,
            sg_arg_importance REAL, sg_putt_importance REAL,
            historical_scoring_avg REAL, ai_course_profile TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(course_id)
        );

        CREATE TABLE IF NOT EXISTS hole_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_key TEXT,
            round_num INTEGER, hole_num INTEGER,
            par INTEGER, score INTEGER, score_to_par INTEGER,
            UNIQUE(event_id, year, player_key, round_num, hole_num)
        );

        CREATE TABLE IF NOT EXISTS hole_difficulty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, round_num INTEGER,
            hole_num INTEGER, par INTEGER,
            field_avg_score REAL, birdie_pct REAL,
            bogey_pct REAL, double_pct REAL, difficulty_rank INTEGER,
            UNIQUE(event_id, year, round_num, hole_num)
        );

        CREATE TABLE IF NOT EXISTS player_hole_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_key TEXT, course_id TEXT, hole_num INTEGER,
            rounds_played INTEGER, avg_score_to_par REAL,
            birdie_pct REAL, bogey_pct REAL,
            UNIQUE(player_key, course_id, hole_num)
        );

        CREATE TABLE IF NOT EXISTS intel_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_key TEXT, source TEXT, source_url TEXT,
            title TEXT, snippet TEXT, published_at TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            tournament_id INTEGER, relevance_score REAL,
            category TEXT, ai_summary TEXT, analyzed_at TEXT,
            UNIQUE(player_key, source_url)
        );

        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis TEXT, source TEXT,
            strategy_config_json TEXT, scope TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            started_at TEXT, completed_at TEXT,
            tournaments_tested INTEGER, total_bets INTEGER,
            roi_pct REAL, clv_avg REAL, sharpe REAL, p_value REAL,
            is_significant INTEGER DEFAULT 0,
            vs_current_delta REAL, vs_dg_delta REAL,
            promoted INTEGER DEFAULT 0,
            full_result_json TEXT,
            UNIQUE(strategy_config_json, scope)
        );

        CREATE TABLE IF NOT EXISTS course_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id TEXT, course_name TEXT, cluster TEXT,
            strategy_config_json TEXT, experiment_id INTEGER,
            roi_pct REAL, tournaments_tested INTEGER,
            is_active INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(course_id)
        );

        CREATE TABLE IF NOT EXISTS active_strategy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT, strategy_config_json TEXT,
            experiment_id INTEGER, roi_pct REAL,
            adopted_at TEXT DEFAULT (datetime('now')),
            UNIQUE(scope)
        );

        CREATE TABLE IF NOT EXISTS outlier_investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_key TEXT,
            predicted_rank INTEGER, actual_finish INTEGER,
            delta INTEGER, weather_conditions TEXT,
            equipment_change_nearby INTEGER,
            intel_context TEXT, ai_explanation TEXT,
            root_cause TEXT, actionable INTEGER DEFAULT 0,
            suggested_model_change TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(event_id, year, player_key)
        );

        CREATE TABLE IF NOT EXISTS pit_rolling_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_key TEXT,
            window INTEGER,
            sg_total REAL, sg_ott REAL, sg_app REAL,
            sg_arg REAL, sg_putt REAL, sg_t2g REAL,
            rounds_used INTEGER,
            UNIQUE(event_id, year, player_key, window)
        );

        CREATE INDEX IF NOT EXISTS idx_historical_odds_event
            ON historical_odds(event_id, year);
        CREATE INDEX IF NOT EXISTS idx_pit_stats_event
            ON pit_rolling_stats(event_id, year);
        CREATE INDEX IF NOT EXISTS idx_experiments_status
            ON experiments(status, scope);
        CREATE INDEX IF NOT EXISTS idx_intel_player
            ON intel_events(player_key, relevance_score DESC);
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

    # Add year column to tournaments if missing
    try:
        conn.execute("SELECT year FROM tournaments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tournaments ADD COLUMN year INTEGER")
        conn.commit()

    # Add actual_finish column to historical_predictions if missing
    try:
        conn.execute("SELECT actual_finish FROM historical_predictions LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE historical_predictions ADD COLUMN actual_finish TEXT")
        conn.commit()

    # Add UNIQUE constraints via indexes (safe to run repeatedly)
    _add_unique_constraints(conn)


def _add_unique_constraints(conn: sqlite3.Connection):
    """Add UNIQUE indexes for dedup. Deduplicates existing data first."""
    constraint_defs = [
        (
            "idx_results_unique",
            "results",
            "(tournament_id, player_key)",
        ),
        (
            "idx_picks_unique",
            "picks",
            "(tournament_id, player_key, bet_type)",
        ),
        (
            "idx_prediction_log_unique",
            "prediction_log",
            "(tournament_id, player_key, bet_type)",
        ),
    ]

    for idx_name, table, cols in constraint_defs:
        # Check if index already exists
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (idx_name,),
        ).fetchone()
        if existing:
            continue

        # Deduplicate: keep the row with the highest id (most recent)
        try:
            conn.execute(f"""
                DELETE FROM {table}
                WHERE id NOT IN (
                    SELECT MAX(id) FROM {table}
                    GROUP BY {cols.strip('()')}
                )
            """)
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON {table} {cols}"
            )
            conn.commit()
        except sqlite3.OperationalError:
            # Table might not exist yet or columns might differ
            pass


# ── Tournament helpers ──────────────────────────────────────────────

def get_or_create_tournament(name: str, course: str = None,
                             date: str = None, year: int = None,
                             event_id: str = None) -> int:
    if year is None:
        year = datetime.now().year
    conn = get_conn()

    # Ensure event_id column exists (migration-safe)
    try:
        conn.execute("SELECT event_id FROM tournaments LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tournaments ADD COLUMN event_id TEXT")
        conn.commit()

    row = conn.execute(
        "SELECT id, year, event_id FROM tournaments WHERE name = ? AND (year = ? OR year IS NULL)",
        (name, year),
    ).fetchone()
    if row:
        tid = row["id"]
        # Fix NULL year or missing event_id on existing rows
        updates = []
        params = []
        if row["year"] is None and year is not None:
            updates.append("year = ?")
            params.append(year)
        if row["event_id"] is None and event_id is not None:
            updates.append("event_id = ?")
            params.append(event_id)
        if updates:
            params.append(tid)
            conn.execute(
                f"UPDATE tournaments SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
    else:
        cur = conn.execute(
            "INSERT INTO tournaments (name, course, date, year, event_id) VALUES (?, ?, ?, ?, ?)",
            (name, course, date, year, event_id),
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
    """Bulk insert/update metric rows. Uses INSERT OR REPLACE for dedup."""
    if not rows:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT OR REPLACE INTO metrics
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
        """INSERT OR REPLACE INTO prediction_log
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


def ensure_initialized():
    """Initialize the database if not already done. Call before first use."""
    global _DB_INITIALIZED
    if not _DB_INITIALIZED:
        init_db()
        _DB_INITIALIZED = True


# Lazy initialization: ensure tables exist on first connection use.
# This replaces the old module-level init_db() call so .env can load first.
ensure_initialized()
