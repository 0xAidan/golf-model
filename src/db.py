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
  market_performance      – rolling ROI tracking by market type
  calibration_curve       – probability calibration buckets (keyed by bet_type + bucket)
  ai_adjustments          – tracked AI-driven player adjustments
  live_snapshot_history   – persisted live/upcoming snapshot sections
  market_prediction_rows  – dense per-tick betting lines from live refresh
  shadow_event_simulations – append-only shadow Monte Carlo (prob_engine_v1; offline analytics)
  telegram_alert_sent    – dedupe keys for personal Telegram matchup EV notifications
"""

import logging
import sqlite3
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any

from src import config
from src.player_normalizer import normalize_name

_logger = logging.getLogger("golf.db")

# Project data path (may be overridden when project lives in a cloud-synced folder)
_PROJECT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "golf.db")


def _is_likely_synced(path: str) -> bool:
    """True if path is under a folder commonly synced (iCloud, Dropbox, etc.) where SQLite often hits disk I/O errors."""
    path = os.path.abspath(path)
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    mobile_docs = os.path.join(home, "Library", "Mobile Documents")
    if path.startswith(mobile_docs) or "iCloud" in path or "CloudStorage" in path:
        return True
    if path.startswith(docs):
        return True
    if "Dropbox" in path or "OneDrive" in path or "Google Drive" in path:
        return True
    return False


def _local_db_dir() -> str:
    """Directory for DB when project is in a synced location (avoids disk I/O errors)."""
    return os.path.join(os.path.expanduser("~"), ".golf-model", "data")


def _resolve_db_path() -> str:
    """
    Use project data/golf.db unless the project appears to be in a cloud-synced folder,
    in which case use ~/.golf-model/data/golf.db and copy from project once if needed.

    Explicit overrides (production):
      GOLF_DB_PATH — full SQLite file path
      GOLF_DATA_DIR — directory containing golf.db
    """
    explicit_db = os.environ.get("GOLF_DB_PATH", "").strip()
    if explicit_db:
        return os.path.abspath(explicit_db)
    data_dir = os.environ.get("GOLF_DATA_DIR", "").strip()
    if data_dir:
        return os.path.join(os.path.abspath(data_dir), "golf.db")

    project_path = os.path.abspath(_PROJECT_DB_PATH)
    if not _is_likely_synced(project_path):
        return project_path
    local_dir = _local_db_dir()
    local_path = os.path.join(local_dir, "golf.db")
    _logger.info("DB path redirected from synced folder to %s", local_path)
    os.makedirs(local_dir, exist_ok=True)
    # One-time copy: if project has a DB and local doesn't (or is empty), copy so we don't start empty
    if os.path.exists(project_path) and os.path.getsize(project_path) > 0:
        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            try:
                shutil.copy2(project_path, local_path)
                for suffix in ("-wal", "-shm"):
                    src = project_path + suffix
                    if os.path.exists(src):
                        shutil.copy2(src, local_path + suffix)
            except OSError as exc:
                _logger.warning("Failed to copy DB from project to local path: %s", exc)
    return local_path


DB_PATH = _resolve_db_path()


_DB_INITIALIZED = False


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    # WAL mode for concurrent read/write and deploy lock in run_predictions prevents parallel pipeline runs
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
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
            event_id TEXT,
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
        -- Q4: composite for per-tournament per-player metric fetches (metric_category filter)
        CREATE INDEX IF NOT EXISTS idx_metrics_tourn_player_cat
            ON metrics(tournament_id, player_key, metric_category);

        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            model_variant TEXT DEFAULT 'baseline',
            source TEXT DEFAULT 'ui_display',
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
            market_book TEXT,
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
            model_hit INTEGER,      -- 1 if model directional call was correct, 0 otherwise
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
        -- Q4: composite for per-player completed-events lookups
        CREATE INDEX IF NOT EXISTS idx_rounds_player_event
            ON rounds(player_key, event_completed);

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

        CREATE TABLE IF NOT EXISTS live_snapshot_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            generated_at TEXT,
            tour TEXT,
            cadence_mode TEXT,
            section TEXT NOT NULL, -- live / upcoming
            event_id TEXT,
            event_name TEXT,
            source_event_id TEXT,
            source_event_name TEXT,
            active INTEGER DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_live_snapshot_history_event
            ON live_snapshot_history(source_event_id, generated_at DESC, section);
        CREATE INDEX IF NOT EXISTS idx_live_snapshot_history_event_section
            ON live_snapshot_history(source_event_id, section, generated_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_live_snapshot_history_snapshot
            ON live_snapshot_history(snapshot_id, section);

        CREATE TABLE IF NOT EXISTS market_prediction_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            generated_at TEXT,
            tour TEXT,
            section TEXT NOT NULL, -- live / upcoming
            event_id TEXT,
            event_name TEXT,
            market_family TEXT NOT NULL, -- matchup / placement
            market_type TEXT,
            player_key TEXT,
            player_display TEXT,
            opponent_key TEXT,
            opponent_display TEXT,
            book TEXT,
            odds TEXT,
            model_prob REAL,
            implied_prob REAL,
            ev REAL,
            is_value INTEGER DEFAULT 0,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_market_prediction_rows_event
            ON market_prediction_rows(event_id, generated_at DESC, market_family);
        CREATE INDEX IF NOT EXISTS idx_market_prediction_rows_event_section
            ON market_prediction_rows(event_id, section, generated_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_market_prediction_rows_snapshot
            ON market_prediction_rows(snapshot_id, section, market_family);

        CREATE TABLE IF NOT EXISTS shadow_event_simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT,
            event_id TEXT NOT NULL,
            section TEXT,
            tour TEXT,
            n_sims INTEGER,
            engine_version TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_event_sims_event
            ON shadow_event_simulations(event_id, created_at DESC);

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

        -- ═══ Dynamic blend (EWA) history ═══
        CREATE TABLE IF NOT EXISTS blend_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            bet_type TEXT NOT NULL,
            brier_dg REAL,
            brier_model REAL,
            brier_blended REAL,
            n_predictions INTEGER DEFAULT 0,
            dg_weight REAL NOT NULL,
            model_weight REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_blend_history_bet_type ON blend_history(bet_type);

        -- ═══ Matchup calibration (Platt A,B params) ═══
        CREATE TABLE IF NOT EXISTS matchup_calibration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_param REAL NOT NULL,
            b_param REAL NOT NULL,
            n_samples INTEGER NOT NULL DEFAULT 0,
            brier_score REAL,
            last_updated TEXT DEFAULT (datetime('now'))
        );

        -- ═══ Bankroll (for Kelly sizing) ═══
        CREATE TABLE IF NOT EXISTS bankroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            balance REAL NOT NULL,
            peak_balance REAL NOT NULL,
            kelly_fraction REAL NOT NULL DEFAULT 0.25,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ═══ CLV tracking ═══
        CREATE TABLE IF NOT EXISTS clv_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            player_key TEXT,
            bet_type TEXT,
            market_book TEXT,
            odds_taken_decimal REAL,
            closing_odds_decimal REAL,
            implied_taken REAL,
            implied_closing REAL,
            clv_pct REAL,
            outcome INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_clv_log_tournament ON clv_log(tournament_id);

        -- ═══ Schema version (for migrations) ═══
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 1);

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

        -- ═══ AI adjustment tracking ═══
        CREATE TABLE IF NOT EXISTS ai_adjustment_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            player_key TEXT,
            adjustment REAL,
            direction TEXT,
            actual_finish_pos INTEGER,
            baseline_rank INTEGER,
            correct INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ═══ Historical matchup odds (for backtester matchup replay) ═══
        CREATE TABLE IF NOT EXISTS historical_matchup_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            bet_type TEXT NOT NULL,
            p1_dg_id INTEGER NOT NULL,
            p1_name TEXT NOT NULL,
            p2_dg_id INTEGER NOT NULL,
            p2_name TEXT NOT NULL,
            book TEXT NOT NULL,
            p1_open TEXT,
            p1_close TEXT,
            p2_open TEXT,
            p2_close TEXT,
            p1_outcome REAL,
            p2_outcome REAL,
            p1_outcome_text TEXT,
            p2_outcome_text TEXT,
            tie_rule TEXT,
            open_time TEXT,
            close_time TEXT,
            UNIQUE(event_id, year, p1_dg_id, p2_dg_id, bet_type, book)
        );
        CREATE INDEX IF NOT EXISTS idx_hist_matchup_event
            ON historical_matchup_odds(event_id, year);
        CREATE INDEX IF NOT EXISTS idx_hist_matchup_type
            ON historical_matchup_odds(bet_type);

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

        CREATE TABLE IF NOT EXISTS research_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            source TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'global',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN (
                    'draft', 'evaluated', 'approved',
                    'rejected', 'converted', 'error'
                )),
            cycle_key TEXT NOT NULL,
            strategy_config_json TEXT NOT NULL,
            baseline_strategy_json TEXT,
            program_version TEXT,
            event_weighting_mode TEXT,
            candidate_count_in_cycle INTEGER,
            years_json TEXT,
            filters_json TEXT,
            theory_metadata_json TEXT,
            summary_metrics_json TEXT,
            segmented_metrics_json TEXT,
            guardrail_results_json TEXT,
            repro_metadata_json TEXT,
            artifact_markdown_path TEXT,
            artifact_manifest_path TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            evaluated_at TEXT,
            approved_at TEXT,
            rejected_at TEXT,
            converted_experiment_id INTEGER REFERENCES experiments(id),
            UNIQUE(strategy_config_json, scope, cycle_key)
        );

        CREATE TABLE IF NOT EXISTS proposal_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id INTEGER NOT NULL REFERENCES research_proposals(id) ON DELETE CASCADE,
            decision TEXT NOT NULL
                CHECK (decision IN ('approved', 'rejected', 'comment')),
            reviewer TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
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

        CREATE TABLE IF NOT EXISTS research_model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL DEFAULT 'global',
            strategy_config_json TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            proposal_id INTEGER REFERENCES research_proposals(id),
            theory_metadata_json TEXT,
            notes TEXT,
            is_current INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Engine-scale: one row per active config for each model track (dashboard champion,
        -- lab challenger). Read-only/provenance in Wave 1; the promotion/rollback workflow
        -- (parent_id chain, evidence_json) is wired in a later wave. config_hash gives stable
        -- per-epoch attribution joined from picks.model_config_hash.
        CREATE TABLE IF NOT EXISTS track_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track TEXT NOT NULL,                       -- 'dashboard' | 'lab'
            strategy_bundle_json TEXT NOT NULL,
            model_variant TEXT,
            config_hash TEXT NOT NULL,
            label TEXT,
            status TEXT NOT NULL DEFAULT 'active',     -- 'active' | 'retired'
            parent_id INTEGER REFERENCES track_configs(id),
            evidence_json TEXT,
            activated_by TEXT DEFAULT 'seed',
            activation_reason TEXT,
            activated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS live_model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL DEFAULT 'global',
            strategy_config_json TEXT NOT NULL,
            source_research_registry_id INTEGER REFERENCES research_model_registry(id),
            promoted_by TEXT NOT NULL DEFAULT 'manual',
            action TEXT NOT NULL DEFAULT 'promote',
            notes TEXT,
            replaced_live_registry_id INTEGER REFERENCES live_model_registry(id),
            is_current INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
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
            sg_total_rank INTEGER,
            UNIQUE(event_id, year, player_key, window)
        );

        CREATE TABLE IF NOT EXISTS pit_course_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_key TEXT,
            course_num INTEGER,
            sg_total REAL, sg_ott REAL, sg_app REAL,
            sg_arg REAL, sg_putt REAL, sg_t2g REAL,
            rounds_played INTEGER,
            avg_finish REAL,
            best_finish INTEGER,
            UNIQUE(event_id, year, player_key)
        );

        CREATE INDEX IF NOT EXISTS idx_historical_odds_event
            ON historical_odds(event_id, year);
        -- Q4: composite for odds-history traversal by (event, book, time).
        -- historical_odds has no explicit ts column; year is the available
        -- temporal ordering dimension, so it serves as the traversal key.
        CREATE INDEX IF NOT EXISTS idx_historical_odds_event_book_ts
            ON historical_odds(event_id, book, year);
        CREATE INDEX IF NOT EXISTS idx_pit_stats_event
            ON pit_rolling_stats(event_id, year);
        CREATE INDEX IF NOT EXISTS idx_pit_course_stats_event
            ON pit_course_stats(event_id, year);
        CREATE INDEX IF NOT EXISTS idx_experiments_status
            ON experiments(status, scope);
        CREATE INDEX IF NOT EXISTS idx_research_proposals_status
            ON research_proposals(status, scope, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_research_proposals_cycle
            ON research_proposals(cycle_key, scope);
        CREATE INDEX IF NOT EXISTS idx_research_model_registry_scope
            ON research_model_registry(scope, is_current, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_live_model_registry_scope
            ON live_model_registry(scope, is_current, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_proposal_reviews_proposal
            ON proposal_reviews(proposal_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_intel_player
            ON intel_events(player_key, relevance_score DESC);

        -- ═══ Adaptive ROI / market performance tracking ═══
        CREATE TABLE IF NOT EXISTS market_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_type TEXT NOT NULL,
            tournament_id INTEGER REFERENCES tournaments(id),
            bets_placed INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            pushes INTEGER NOT NULL DEFAULT 0,
            units_wagered REAL NOT NULL DEFAULT 0,
            units_returned REAL NOT NULL DEFAULT 0,
            roi_pct REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_market_perf_type ON market_performance(market_type);
        CREATE INDEX IF NOT EXISTS idx_market_perf_tournament ON market_performance(tournament_id);

        CREATE TABLE IF NOT EXISTS calibration_curve (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_type TEXT NOT NULL DEFAULT '',
            probability_bucket TEXT NOT NULL,
            predicted_avg REAL NOT NULL,
            actual_hit_rate REAL NOT NULL,
            sample_size INTEGER NOT NULL,
            correction_factor REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ai_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER REFERENCES tournaments(id),
            player_key TEXT NOT NULL,
            adjustment_value REAL NOT NULL,
            reasoning TEXT,
            was_helpful INTEGER,
            actual_delta REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ═══ Champion-challenger shadow predictions (defect 3.3.1) ═══
        -- One row per (model, matchup, prediction call). Challenger rows are
        -- recorded alongside the champion's prediction for the same inputs so
        -- Brier / ROI / CLV can be computed offline without touching live
        -- pricing. `market_type` distinguishes matchup vs outright rows.
        CREATE TABLE IF NOT EXISTS challenger_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            model_version TEXT,
            market_type TEXT NOT NULL DEFAULT 'matchup',
            matchup_id TEXT,
            tournament_id INTEGER REFERENCES tournaments(id),
            p1_key TEXT,
            p2_key TEXT,
            predicted_p REAL NOT NULL,
            champion_p REAL,
            book_price_p1 REAL,
            book_price_p2 REAL,
            outcome INTEGER,
            ts TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_challenger_predictions_model_ts
            ON challenger_predictions(model_name, ts);
        CREATE INDEX IF NOT EXISTS idx_challenger_predictions_matchup
            ON challenger_predictions(matchup_id, model_name);

        -- ═══ T6: In-play round matchups (SHADOW MODE ONLY) ═══
        -- Raw book prices pulled during active rounds. No bets are placed
        -- off these rows; they exist purely for evaluation.
        CREATE TABLE IF NOT EXISTS inplay_round_matchup_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            round_num INTEGER NOT NULL,
            player1 TEXT NOT NULL,
            player2 TEXT NOT NULL,
            book TEXT NOT NULL,
            price1 REAL NOT NULL,
            price2 REAL NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_inplay_prices_event
            ON inplay_round_matchup_prices(event_id, round_num);

        -- One row per refresh tick per in-play matchup price.
        -- kelly_fraction_if_hypothetically is recorded for LATER analysis —
        -- it is NEVER used to place a real bet (staking is disabled).
        CREATE TABLE IF NOT EXISTS inplay_round_matchup_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            round_num INTEGER NOT NULL,
            hole_num_at_prediction INTEGER NOT NULL,
            player1 TEXT NOT NULL,
            player2 TEXT NOT NULL,
            book TEXT NOT NULL,
            price1 REAL NOT NULL,
            price2 REAL NOT NULL,
            predicted_p1 REAL NOT NULL,
            kelly_fraction_if_hypothetically REAL NOT NULL,
            ts TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_inplay_preds_event
            ON inplay_round_matchup_predictions(event_id, round_num);

        -- Personal Telegram matchup alerts (dedupe by stable hash per book line)
        CREATE TABLE IF NOT EXISTS telegram_alert_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_hash TEXT NOT NULL UNIQUE,
            sent_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # ── Migrations for existing databases ──
    _run_migrations(conn)

    try:
        from src.data_views import ensure_analytics_views

        ensure_analytics_views(conn)
    except Exception as exc:
        _logger.warning("Analytics views setup failed: %s", exc)

    conn.close()


def _ensure_pick_ledger_tables(conn: sqlite3.Connection) -> None:
    """Append-only pick ledger + grading audit trail (never pruned)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pick_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_key TEXT NOT NULL UNIQUE,
            event_id TEXT NOT NULL,
            event_name TEXT,
            tournament_id INTEGER REFERENCES tournaments(id),
            year INTEGER,
            phase TEXT NOT NULL DEFAULT 'pre_tournament',
            section TEXT NOT NULL DEFAULT 'upcoming',
            lane TEXT NOT NULL DEFAULT 'cockpit',
            lifecycle TEXT NOT NULL DEFAULT 'generated',
            bet_type TEXT,
            market_family TEXT,
            market_type TEXT,
            player_key TEXT NOT NULL,
            player_display TEXT,
            opponent_key TEXT,
            opponent_display TEXT,
            book TEXT,
            odds TEXT,
            model_prob REAL,
            implied_prob REAL,
            ev REAL,
            is_value INTEGER DEFAULT 0,
            model_variant TEXT,
            model_config_hash TEXT,
            snapshot_id TEXT,
            generated_at TEXT NOT NULL,
            source_origin TEXT NOT NULL DEFAULT 'live_refresh',
            payload_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_ledger_event_phase
        ON pick_ledger(event_id, phase, generated_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pick_ledger_tournament
        ON pick_ledger(tournament_id, lifecycle)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grading_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_id INTEGER REFERENCES picks(id),
            pick_key TEXT,
            tournament_id INTEGER REFERENCES tournaments(id),
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            previous_json TEXT,
            new_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    for col, col_type, default in [
        ("pick_key", "TEXT", None),
        ("grading_authority", "TEXT", None),
        ("outcome_locked", "INTEGER", "0"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM pick_outcomes LIMIT 1")
        except sqlite3.OperationalError:
            default_clause = f" DEFAULT {default}" if default is not None else ""
            conn.execute(f"ALTER TABLE pick_outcomes ADD COLUMN {col} {col_type}{default_clause}")
    conn.commit()


def _ensure_pre_teeoff_tables(conn: sqlite3.Connection) -> None:
    """Pre-teeoff candidate + frozen snapshot tables for Completed tab replay."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pre_teeoff_candidates (
            event_id TEXT PRIMARY KEY,
            tour TEXT,
            event_name TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pre_teeoff_frozen (
            event_id TEXT PRIMARY KEY,
            tour TEXT,
            event_name TEXT,
            payload_json TEXT NOT NULL,
            frozen_at TEXT NOT NULL,
            source_snapshot_id TEXT
        )
        """
    )
    conn.commit()


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
        ("model_hit", "INTEGER", None),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM pick_outcomes LIMIT 1")
        except sqlite3.OperationalError:
            default_clause = f" DEFAULT {default}" if default is not None else ""
            conn.execute(f"ALTER TABLE pick_outcomes ADD COLUMN {col} {col_type}{default_clause}")
            conn.commit()
    try:
        conn.execute(
            """
            UPDATE pick_outcomes
            SET model_hit = CASE
                WHEN model_hit IS NOT NULL THEN model_hit
                WHEN COALESCE((SELECT ev FROM picks WHERE picks.id = pick_outcomes.pick_id), 0) < 0
                    THEN CASE WHEN hit = 1 THEN 0 ELSE hit END
                ELSE hit
            END
            WHERE model_hit IS NULL
            """
        )
        conn.commit()
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        # Keep startup resilient if this backfill cannot run on a given DB state.
        # Runtime reads use COALESCE(model_hit, hit), so null model_hit is safe.
        pass

    # Add year column to tournaments if missing
    try:
        conn.execute("SELECT year FROM tournaments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tournaments ADD COLUMN year INTEGER")
        conn.commit()

    # Add model lane/source fields to picks if missing
    try:
        conn.execute("SELECT model_variant FROM picks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE picks ADD COLUMN model_variant TEXT DEFAULT 'baseline'")
        conn.commit()
    try:
        conn.execute("SELECT source FROM picks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE picks ADD COLUMN source TEXT DEFAULT 'ui_display'")
        conn.commit()
    try:
        conn.execute("SELECT market_book FROM picks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE picks ADD COLUMN market_book TEXT")
        conn.commit()
    # Engine-scale: per-pick config provenance (which track config epoch produced it).
    try:
        conn.execute("SELECT model_config_hash FROM picks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE picks ADD COLUMN model_config_hash TEXT")
        conn.commit()
    conn.execute("UPDATE picks SET model_variant = 'baseline' WHERE model_variant IS NULL OR TRIM(model_variant) = ''")
    conn.execute("UPDATE picks SET source = 'ui_display' WHERE source IS NULL OR TRIM(source) = ''")
    try:
        conn.execute("UPDATE picks SET market_book = '' WHERE market_book IS NULL")
    except (sqlite3.OperationalError, sqlite3.IntegrityError):
        # Older/partial schemas can miss this column before migration settles.
        # Also tolerate uniqueness collisions on legacy duplicate rows.
        pass
    conn.execute("UPDATE picks SET opponent_key = '' WHERE opponent_key IS NULL")
    conn.execute("UPDATE picks SET opponent_display = '' WHERE opponent_display IS NULL")
    try:
        conn.execute("SELECT market_type FROM picks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE picks ADD COLUMN market_type TEXT DEFAULT ''")
        conn.execute(
            "UPDATE picks SET market_type = 'tournament_matchups' "
            "WHERE bet_type = 'matchup' AND (market_type IS NULL OR TRIM(market_type) = '')"
        )
        conn.commit()
    # Rebuild legacy unique index to include model lane + opponent key + market_type.
    conn.execute("DROP INDEX IF EXISTS idx_picks_unique")
    conn.commit()
    _migrate_picks_unique_index(conn)

    # Add event_id column to tournaments if missing
    try:
        conn.execute("SELECT event_id FROM tournaments LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE tournaments ADD COLUMN event_id TEXT")
        conn.commit()

    # Add actual_finish column to historical_predictions if missing
    try:
        conn.execute("SELECT actual_finish FROM historical_predictions LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE historical_predictions ADD COLUMN actual_finish TEXT")
        conn.commit()

    # Add sg_total_rank column to pit_rolling_stats if missing
    try:
        conn.execute("SELECT sg_total_rank FROM pit_rolling_stats LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE pit_rolling_stats ADD COLUMN sg_total_rank INTEGER")
        conn.commit()

    # Add theory metadata to research proposals if missing
    try:
        conn.execute("SELECT theory_metadata_json FROM research_proposals LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE research_proposals ADD COLUMN theory_metadata_json TEXT")
        conn.commit()

    # v5 Milestone A: calibration_curve keyed by (bet_type, probability_bucket)
    try:
        conn.execute("SELECT bet_type FROM calibration_curve LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute(
            "ALTER TABLE calibration_curve ADD COLUMN bet_type TEXT NOT NULL DEFAULT ''"
        )
        conn.commit()
    try:
        conn.execute(
            """
            DELETE FROM calibration_curve
            WHERE id NOT IN (
                SELECT MAX(id) FROM calibration_curve
                GROUP BY bet_type, probability_bucket
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_calibration_curve_type_bucket "
            "ON calibration_curve(bet_type, probability_bucket)"
        )
        conn.commit()
    except sqlite3.OperationalError:
        logging.getLogger(__name__).debug(
            "calibration_curve unique index migration skipped", exc_info=True
        )

    # v5 Milestone A: CLV rows optionally tagged with sportsbook
    try:
        conn.execute("SELECT market_book FROM clv_log LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE clv_log ADD COLUMN market_book TEXT")
        conn.commit()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL DEFAULT 'global',
            strategy_config_json TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            proposal_id INTEGER REFERENCES research_proposals(id),
            theory_metadata_json TEXT,
            notes TEXT,
            is_current INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS live_model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL DEFAULT 'global',
            strategy_config_json TEXT NOT NULL,
            source_research_registry_id INTEGER REFERENCES research_model_registry(id),
            promoted_by TEXT NOT NULL DEFAULT 'manual',
            action TEXT NOT NULL DEFAULT 'promote',
            notes TEXT,
            replaced_live_registry_id INTEGER REFERENCES live_model_registry(id),
            is_current INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_research_model_registry_scope
        ON research_model_registry(scope, is_current, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_live_model_registry_scope
        ON live_model_registry(scope, is_current, created_at DESC)
    """)
    conn.commit()

    # Defect 3.3.1: champion-challenger shadow predictions. Defined in
    # init_db() for new databases; re-declared here so older databases pick
    # it up via the migration path.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS challenger_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            model_version TEXT,
            market_type TEXT NOT NULL DEFAULT 'matchup',
            matchup_id TEXT,
            tournament_id INTEGER REFERENCES tournaments(id),
            p1_key TEXT,
            p2_key TEXT,
            predicted_p REAL NOT NULL,
            champion_p REAL,
            book_price_p1 REAL,
            book_price_p2 REAL,
            outcome INTEGER,
            ts TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenger_predictions_model_ts
        ON challenger_predictions(model_name, ts)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_challenger_predictions_matchup
        ON challenger_predictions(matchup_id, model_name)
    """)
    conn.commit()

    _ensure_pre_teeoff_tables(conn)
    _ensure_pick_ledger_tables(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_event_simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT,
            event_id TEXT NOT NULL,
            section TEXT,
            tour TEXT,
            n_sims INTEGER,
            engine_version TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_shadow_event_sims_event
        ON shadow_event_simulations(event_id, created_at DESC)
    """)
    conn.commit()

    # Create pit_course_stats table if missing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_course_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, year INTEGER, player_key TEXT,
            course_num INTEGER,
            sg_total REAL, sg_ott REAL, sg_app REAL,
            sg_arg REAL, sg_putt REAL, sg_t2g REAL,
            rounds_played INTEGER,
            avg_finish REAL,
            best_finish INTEGER,
            UNIQUE(event_id, year, player_key)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pit_course_stats_event
        ON pit_course_stats(event_id, year)
    """)
    conn.commit()

    # Add UNIQUE index on metrics for dedup (prevents duplicate SG:TOT rows per player/window)
    try:
        # First deduplicate: keep the row with the highest id (most recent)
        conn.execute("""
            DELETE FROM metrics
            WHERE id NOT IN (
                SELECT MAX(id) FROM metrics
                GROUP BY tournament_id, player_key, metric_category, data_mode, round_window, metric_name
            )
        """)
        conn.commit()
    except Exception:
        logging.getLogger(__name__).debug("Metrics dedup skipped (table may be empty or not exist yet)", exc_info=True)

    try:
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_metrics_unique'")
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_metrics_unique'"
        ).fetchone()
        if not existing:
            conn.execute("""
                CREATE UNIQUE INDEX idx_metrics_unique
                ON metrics(tournament_id, player_key, metric_category, data_mode, round_window, metric_name)
            """)
            conn.commit()
    except Exception:
        logging.getLogger(__name__).debug("Metrics unique index creation skipped", exc_info=True)

    # Add UNIQUE constraints via indexes (safe to run repeatedly)
    _add_unique_constraints(conn)

    # Q4: composite indexes for hot-path queries. Idempotent, index-only.
    _ensure_hot_path_indexes(conn)

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_alert_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_hash TEXT NOT NULL UNIQUE,
                sent_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    except sqlite3.OperationalError:
        logging.getLogger(__name__).debug(
            "telegram_alert_sent table migration skipped", exc_info=True
        )


def _ensure_hot_path_indexes(conn: sqlite3.Connection) -> None:
    """Create composite indexes for hot-path queries on existing DBs.

    Idempotent: uses CREATE INDEX IF NOT EXISTS. No data is read or modified.
    Covers Q4 defect — full scans on rounds / metrics / historical_odds.
    """
    statements = (
        "CREATE INDEX IF NOT EXISTS idx_rounds_player_event "
        "ON rounds(player_key, event_completed)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_tourn_player_cat "
        "ON metrics(tournament_id, player_key, metric_category)",
        "CREATE INDEX IF NOT EXISTS idx_historical_odds_event_book_ts "
        "ON historical_odds(event_id, book, year)",
        "CREATE INDEX IF NOT EXISTS idx_live_snapshot_history_event_section "
        "ON live_snapshot_history(source_event_id, section, generated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_market_prediction_rows_event_section "
        "ON market_prediction_rows(event_id, section, generated_at DESC, id DESC)",
    )
    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            # Table may not exist yet on a fresh/partial DB; init_db covers that case.
            logging.getLogger(__name__).debug(
                "Skipping hot-path index (table missing): %s", stmt, exc_info=True
            )
    conn.commit()


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
            "(tournament_id, model_variant, source, player_key, bet_type, market_type, opponent_key)",
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
            if table == "picks":
                conn.execute(f"""
                    DELETE FROM pick_outcomes
                    WHERE pick_id IN (
                        SELECT id FROM {table}
                        WHERE id NOT IN (
                            SELECT MAX(id) FROM {table}
                            GROUP BY {cols.strip('()')}
                        )
                    )
                """)
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


def get_player_metrics_by_categories(
    tournament_id: int,
    player_key: str,
    categories: list[str],
) -> list[dict]:
    """Return player metrics filtered to specific metric categories."""
    if not categories:
        return []

    placeholders = ",".join("?" for _ in categories)
    params = [tournament_id, player_key, *categories]
    conn = get_conn()
    rows = conn.execute(
        f"""SELECT * FROM metrics
            WHERE tournament_id = ?
              AND player_key = ?
              AND metric_category IN ({placeholders})
            ORDER BY metric_category, round_window, metric_name""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tournament_metric_values(
    tournament_id: int,
    metric_category: str,
    metric_name: str,
    *,
    data_mode: str | None = None,
    round_window: str | None = None,
) -> list[float]:
    """Return numeric metric values for one tournament-level metric slice."""
    sql = """SELECT metric_value FROM metrics
             WHERE tournament_id = ?
               AND metric_category = ?
               AND metric_name = ?
               AND metric_value IS NOT NULL"""
    params: list = [tournament_id, metric_category, metric_name]
    if data_mode:
        sql += " AND data_mode = ?"
        params.append(data_mode)
    if round_window:
        sql += " AND round_window = ?"
        params.append(round_window)

    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [float(r["metric_value"]) for r in rows if r["metric_value"] is not None]


def get_tournament_field_size(tournament_id: int) -> int:
    """
    Return field size for a tournament.

    Prefers explicit confirmed field rows from Data Golf field updates,
    then falls back to distinct players seen in metrics.
    """
    conn = get_conn()
    try:
        confirmed_row = conn.execute(
            """SELECT COUNT(DISTINCT player_key) AS cnt
               FROM metrics
               WHERE tournament_id = ?
                 AND metric_category = 'meta'
                 AND metric_name = 'field_status'
                 AND metric_text = 'confirmed'""",
            (tournament_id,),
        ).fetchone()
        confirmed_count = int(confirmed_row["cnt"] or 0) if confirmed_row else 0
        if confirmed_count > 0:
            return confirmed_count

        fallback_row = conn.execute(
            """SELECT COUNT(DISTINCT player_key) AS cnt
               FROM metrics
               WHERE tournament_id = ?""",
            (tournament_id,),
        ).fetchone()
        return int(fallback_row["cnt"] or 0) if fallback_row else 0
    finally:
        conn.close()


def get_all_players(tournament_id: int, confirmed_field_only: bool = True) -> list[str]:
    """Return player_key list for this tournament.

    When confirmed_field_only=True (default), only returns players that appear
    in the explicit confirmed field rows from DG field updates
    (`metric_name='field_status'`, `metric_text='confirmed'`).
    Falls back to legacy `metric_category='meta'` rows when older tournaments
    predate the stricter marker. In strict mode, if no confirmed field exists,
    returns an empty list (fail closed) to avoid ranking non-participants.
    """
    conn = get_conn()
    has_explicit_field = conn.execute(
        """SELECT 1 FROM metrics
           WHERE tournament_id = ?
             AND metric_category = 'meta'
             AND metric_name = 'field_status'
             AND metric_text = 'confirmed'
           LIMIT 1""",
        (tournament_id,),
    ).fetchone()
    if confirmed_field_only and has_explicit_field:
        rows = conn.execute(
            """SELECT DISTINCT player_key FROM metrics
               WHERE tournament_id = ?
                 AND metric_category = 'meta'
                 AND metric_name = 'field_status'
                 AND metric_text = 'confirmed'""",
            (tournament_id,),
        ).fetchall()
    else:
        # Fail closed for strict field integrity when no explicit field exists.
        # Any proxy based on stats can include players not actually in the event.
        if confirmed_field_only:
            _logger.warning(
                "No explicit confirmed field rows found for tournament_id=%s; returning empty field list",
                tournament_id,
            )
            rows = []
        else:
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

    def _display_quality(player_key: str, player_display: str) -> tuple[int, int]:
        display = str(player_display or "").strip()
        key_like = display.lower() == str(player_key or "").strip().lower()
        has_space = " " in display
        return (0 if key_like else 1, 1 if has_space else 0)

    best: dict[str, str] = {}
    for row in rows:
        player_key = row["player_key"]
        player_display = row["player_display"]
        current = best.get(player_key)
        if current is None or _display_quality(player_key, player_display) > _display_quality(player_key, current):
            best[player_key] = player_display
    return best


# ── Picks / results helpers ─────────────────────────────────────────

def _migrate_picks_unique_index(conn: sqlite3.Connection) -> None:
    """Ensure picks unique index is one row per play identity (best odds on upsert)."""
    from src.official_pick_record import dedupe_picks_by_grading_identity

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_picks_unique'",
    ).fetchone()
    needs_dedupe = False
    if row and row["sql"]:
        sql = str(row["sql"]).lower()
        if "market_odds" in sql or "market_book" in sql:
            conn.execute("DROP INDEX IF EXISTS idx_picks_unique")
            conn.commit()
            needs_dedupe = True
    else:
        needs_dedupe = True
    if needs_dedupe:
        dedupe_picks_by_grading_identity(conn)
    _add_unique_constraints(conn)


def store_picks(picks: list[dict]):
    if not picks:
        return
    from src.official_pick_record import american_odds_rank

    normalized_rows = []
    for pick in picks:
        normalized_rows.append({
            "tournament_id": pick["tournament_id"],
            "model_variant": (pick.get("model_variant") or "baseline").strip().lower(),
            "source": pick.get("source") or "cockpit",
            "bet_type": pick.get("bet_type"),
            "market_type": pick.get("market_type") or "",
            "player_key": pick.get("player_key"),
            "player_display": pick.get("player_display"),
            "opponent_key": pick.get("opponent_key") or "",
            "opponent_display": pick.get("opponent_display") or "",
            "composite_score": pick.get("composite_score"),
            "course_fit_score": pick.get("course_fit_score"),
            "form_score": pick.get("form_score"),
            "momentum_score": pick.get("momentum_score"),
            "model_prob": pick.get("model_prob"),
            "market_odds": pick.get("market_odds"),
            "market_book": pick.get("market_book") or "",
            "market_implied_prob": pick.get("market_implied_prob"),
            "ev": pick.get("ev"),
            "confidence": pick.get("confidence"),
            "reasoning": pick.get("reasoning"),
            "model_config_hash": pick.get("model_config_hash"),
        })
    conn = get_conn()
    select_sql = """
        SELECT id, market_odds, ev, market_book FROM picks
        WHERE tournament_id = :tournament_id
          AND model_variant = :model_variant
          AND source = :source
          AND player_key = :player_key
          AND bet_type = :bet_type
          AND market_type = :market_type
          AND opponent_key = :opponent_key
        LIMIT 1
    """
    insert_sql = """
        INSERT INTO picks
           (tournament_id, model_variant, source, bet_type, market_type, player_key, player_display,
            opponent_key, opponent_display,
            composite_score, course_fit_score, form_score, momentum_score,
            model_prob, market_odds, market_book, market_implied_prob, ev,
            confidence, reasoning, model_config_hash)
           VALUES (:tournament_id, :model_variant, :source, :bet_type, :market_type, :player_key, :player_display,
                    :opponent_key, :opponent_display,
                    :composite_score, :course_fit_score, :form_score, :momentum_score,
                    :model_prob, :market_odds, :market_book, :market_implied_prob, :ev,
                    :confidence, :reasoning, :model_config_hash)
    """
    update_sql = """
        UPDATE picks SET
            player_display = :player_display,
            opponent_display = :opponent_display,
            composite_score = :composite_score,
            course_fit_score = :course_fit_score,
            form_score = :form_score,
            momentum_score = :momentum_score,
            model_prob = :model_prob,
            market_odds = :market_odds,
            market_book = :market_book,
            market_implied_prob = :market_implied_prob,
            ev = :ev,
            confidence = :confidence,
            reasoning = :reasoning,
            model_config_hash = :model_config_hash
        WHERE id = :existing_id
    """
    for row in normalized_rows:
        existing = conn.execute(select_sql, row).fetchone()
        if existing is None:
            conn.execute(insert_sql, row)
            continue
        better_odds = american_odds_rank(row.get("market_odds")) > american_odds_rank(existing["market_odds"])
        better_ev = float(row.get("ev") or 0) > float(existing["ev"] or 0)
        if better_odds or better_ev:
            conn.execute(update_sql, {**row, "existing_id": existing["id"]})
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
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(tournament_id, player_key) DO UPDATE SET
               player_display = excluded.player_display,
               finish_position = excluded.finish_position,
               finish_text = excluded.finish_text,
               made_cut = excluded.made_cut,
               entered_at = datetime('now')""",
        [
            (tournament_id, r["player_key"], r["player_display"],
             r.get("finish_position"), r.get("finish_text"), r.get("made_cut"))
            for r in results_list
        ],
    )
    conn.commit()
    conn.close()


def try_claim_telegram_alert(alert_hash: str) -> bool:
    """Insert alert_hash if new. Returns True when this hash was claimed (notify once)."""
    if not alert_hash:
        return False
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO telegram_alert_sent (alert_hash) VALUES (?)",
            (alert_hash,),
        )
        conn.commit()
        return cur.rowcount == 1
    except sqlite3.OperationalError as exc:
        _logger.warning("telegram_alert_sent insert failed: %s", exc)
        conn.rollback()
        return False
    finally:
        conn.close()


# ── Weights helpers ─────────────────────────────────────────────────
# Default weights from config (single source of truth)
DEFAULT_WEIGHTS = config.DEFAULT_WEIGHTS


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
    """Store predictions for calibration tracking.

    Uses INSERT OR IGNORE so the first (pre-tournament) snapshot is
    preserved.  A mid-tournament re-run won't silently overwrite
    pre-tournament odds with in-play prices.
    """
    if not predictions:
        return
    conn = get_conn()
    _migrate_prediction_log_timing(conn)
    conn.executemany(
        """INSERT OR IGNORE INTO prediction_log
           (tournament_id, player_key, bet_type, model_prob, dg_prob,
            market_implied_prob, actual_outcome, odds_decimal, profit, odds_timing)
           VALUES (:tournament_id, :player_key, :bet_type, :model_prob, :dg_prob,
                    :market_implied_prob, :actual_outcome, :odds_decimal, :profit,
                    :odds_timing)""",
        predictions,
    )
    conn.commit()
    conn.close()


def has_predictions(tournament_id: int) -> bool:
    """Check if prediction_log already has entries for this tournament."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM prediction_log WHERE tournament_id = ? LIMIT 1",
        (tournament_id,),
    ).fetchone()
    conn.close()
    return row is not None


def _migrate_prediction_log_timing(conn: sqlite3.Connection):
    """Add odds_timing column to prediction_log if missing."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(prediction_log)").fetchall()]
    if "odds_timing" not in cols:
        conn.execute(
            "ALTER TABLE prediction_log ADD COLUMN odds_timing TEXT DEFAULT 'unknown'"
        )
        conn.commit()


def get_calibration_data(min_tournaments: int = 3) -> list[dict]:
    """Get all prediction log entries for calibration analysis."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM prediction_log ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Live snapshot + market row history helpers ─────────────────────

def store_live_snapshot_sections(
    snapshot_id: str,
    *,
    generated_at: str | None,
    tour: str | None,
    cadence_mode: str | None,
    live_section: dict | None,
    upcoming_section: dict | None,
) -> int:
    """Persist immutable live/upcoming snapshot sections for replay and audits."""
    if not snapshot_id:
        return 0

    section_rows: list[dict] = []
    for section_name, section in (("live", live_section), ("upcoming", upcoming_section)):
        if not isinstance(section, dict) or not section:
            continue
        section_rows.append(
            {
                "snapshot_id": snapshot_id,
                "generated_at": generated_at,
                "tour": (tour or "").strip().lower() or None,
                "cadence_mode": cadence_mode,
                "section": section_name,
                "event_id": str(section.get("source_event_id") or section.get("event_id") or "").strip() or None,
                "event_name": str(section.get("event_name") or "").strip() or None,
                "source_event_id": str(section.get("source_event_id") or "").strip() or None,
                "source_event_name": str(section.get("source_event_name") or section.get("event_name") or "").strip() or None,
                "active": 1 if bool(section.get("active")) else 0,
                "payload_json": json.dumps(section),
            }
        )

    if not section_rows:
        return 0

    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO live_snapshot_history
            (snapshot_id, generated_at, tour, cadence_mode, section, event_id, event_name,
             source_event_id, source_event_name, active, payload_json)
        VALUES
            (:snapshot_id, :generated_at, :tour, :cadence_mode, :section, :event_id, :event_name,
             :source_event_id, :source_event_name, :active, :payload_json)
        """,
        section_rows,
    )
    conn.commit()
    conn.close()
    return len(section_rows)


def list_past_snapshot_events(
    limit: int = 40,
    *,
    exclude_event_ids: set[str] | None = None,
) -> list[dict]:
    """List events that have immutable snapshot history for past-event replay.

    `event_name` is resolved to the most recently observed name for that
    event_id (not alphabetical MAX) — events are renamed mid-season (e.g. the
    Cadillac Championship was historically the WGC Cadillac/Miami Championship)
    and replay UIs need the current authoritative name.

    `exclude_event_ids`, if provided, drops any matching event_ids from the
    output. Callers (e.g. the past-events API) use this to keep the currently
    upcoming or live event from leaking into the past-events selector.
    """
    conn = get_conn()
    # Pull a wider candidate window than `limit` so we can post-filter without
    # losing real past events. The correlated subquery for `event_name` picks
    # the name from the row with the most recent generated_at per event_id.
    rows = conn.execute(
        """
        SELECT
            h.source_event_id AS event_id,
            (
                SELECT COALESCE(h2.source_event_name, h2.event_name)
                FROM live_snapshot_history h2
                WHERE h2.source_event_id = h.source_event_id
                  AND h2.section IN ('live', 'upcoming')
                ORDER BY h2.generated_at DESC, h2.id DESC
                LIMIT 1
            ) AS event_name,
            MAX(h.generated_at) AS latest_generated_at,
            COUNT(*) AS snapshot_count
        FROM live_snapshot_history h
        WHERE h.section IN ('live', 'upcoming')
          AND h.source_event_id IS NOT NULL
          AND TRIM(h.source_event_id) != ''
        GROUP BY h.source_event_id
        ORDER BY latest_generated_at DESC, h.source_event_id DESC
        LIMIT ?
        """,
        (max(int(limit) * 3, int(limit) + 5),),
    ).fetchall()
    conn.close()

    excluded = {str(eid).strip() for eid in (exclude_event_ids or set()) if eid}
    out: list[dict] = []
    for row in rows:
        record = dict(row)
        eid = str(record.get("event_id") or "").strip()
        if eid and eid in excluded:
            continue
        out.append(record)
        if len(out) >= int(limit):
            break
    return out


def get_latest_snapshot_section(event_id: str, *, section: str = "live") -> dict | None:
    """Return the latest stored section payload for a given event id."""
    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        return None
    conn = get_conn()
    row = conn.execute(
        """
        SELECT snapshot_id, generated_at, tour, cadence_mode, section, source_event_id,
               source_event_name, active, payload_json
        FROM live_snapshot_history
        WHERE source_event_id = ? AND section = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_event_id, section),
    ).fetchone()
    conn.close()
    if not row:
        return None
    payload = dict(row)
    raw_payload = payload.pop("payload_json", None)
    try:
        payload["snapshot"] = json.loads(raw_payload) if raw_payload else {}
    except json.JSONDecodeError:
        payload["snapshot"] = {}
    return payload


def get_first_snapshot_section(event_id: str, *, section: str = "live") -> dict | None:
    """Return the earliest stored section payload for a given event id."""
    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        return None
    conn = get_conn()
    row = conn.execute(
        """
        SELECT snapshot_id, generated_at, tour, cadence_mode, section, source_event_id,
               source_event_name, active, payload_json
        FROM live_snapshot_history
        WHERE source_event_id = ? AND section = ?
        ORDER BY generated_at ASC, id ASC
        LIMIT 1
        """,
        (normalized_event_id, section),
    ).fetchone()
    conn.close()
    if not row:
        return None
    payload = dict(row)
    raw_payload = payload.pop("payload_json", None)
    try:
        payload["snapshot"] = json.loads(raw_payload) if raw_payload else {}
    except json.JSONDecodeError:
        payload["snapshot"] = {}
    return payload


def list_snapshot_timeline_points(event_id: str, *, section: str = "live", limit: int = 120) -> list[dict]:
    """Return summarized replay timeline points for a stored event section."""
    normalized_event_id = str(event_id or "").strip()
    normalized_section = str(section or "live").strip().lower()
    if not normalized_event_id:
        return []

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT snapshot_id, generated_at, tour, cadence_mode, section, source_event_id, source_event_name, event_name, active, payload_json
        FROM live_snapshot_history
        WHERE source_event_id = ? AND section = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_event_id, normalized_section, int(limit)),
    ).fetchall()
    conn.close()

    points: list[dict] = []
    for row in rows:
        raw_payload = row["payload_json"]
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            payload = {}

        diagnostics = payload.get("diagnostics") if isinstance(payload, dict) else {}
        diagnostics_state = diagnostics.get("state") if isinstance(diagnostics, dict) else None

        leaderboard = payload.get("leaderboard") if isinstance(payload, dict) else None
        leaderboard_count = len(leaderboard) if isinstance(leaderboard, list) else 0

        rankings = payload.get("rankings") if isinstance(payload, dict) else None
        rankings_count = len(rankings) if isinstance(rankings, list) else 0

        matchup_rows = []
        if isinstance(payload, dict):
            matchup_rows = payload.get("matchup_bets_all_books") or payload.get("matchup_bets") or []
        matchup_count = len(matchup_rows) if isinstance(matchup_rows, list) else 0

        value_pick_count = 0
        best_edge: float | None = None
        if isinstance(matchup_rows, list):
            for bet in matchup_rows:
                if not isinstance(bet, dict):
                    continue
                ev_value = bet.get("ev")
                if ev_value is None:
                    continue
                try:
                    candidate = float(ev_value)
                except (TypeError, ValueError):
                    continue
                if best_edge is None or candidate > best_edge:
                    best_edge = candidate

        value_bets = payload.get("value_bets") if isinstance(payload, dict) else None
        if isinstance(value_bets, dict):
            for bets in value_bets.values():
                if not isinstance(bets, list):
                    continue
                value_pick_count += len(bets)
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    ev_value = bet.get("ev")
                    if ev_value is None:
                        continue
                    try:
                        candidate = float(ev_value)
                    except (TypeError, ValueError):
                        continue
                    if best_edge is None or candidate > best_edge:
                        best_edge = candidate

        points.append(
            {
                "snapshot_id": row["snapshot_id"],
                "generated_at": row["generated_at"],
                "tour": row["tour"],
                "cadence_mode": row["cadence_mode"],
                "section": row["section"],
                "event_id": row["source_event_id"],
                "event_name": row["source_event_name"] or row["event_name"],
                "active": bool(row["active"]),
                "diagnostics_state": diagnostics_state,
                "leaderboard_count": leaderboard_count,
                "rankings_count": rankings_count,
                "matchup_count": matchup_count,
                "value_pick_count": value_pick_count,
                "best_edge": best_edge,
            }
        )

    return points


def upsert_pre_teeoff_candidate(
    event_id: str,
    *,
    tour: str | None,
    event_name: str | None,
    section_payload: dict,
) -> None:
    """Store latest verified upcoming section while an event is still pre-teeoff."""
    normalized = str(event_id or "").strip()
    if not normalized or not isinstance(section_payload, dict):
        return
    conn = get_conn()
    _ensure_pre_teeoff_tables(conn)
    conn.execute(
        """
        INSERT INTO pre_teeoff_candidates (event_id, tour, event_name, payload_json, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(event_id) DO UPDATE SET
            tour = excluded.tour,
            event_name = excluded.event_name,
            payload_json = excluded.payload_json,
            updated_at = datetime('now')
        """,
        (normalized, (tour or "").strip().lower() or None, (event_name or "").strip() or None, json.dumps(section_payload)),
    )
    conn.commit()
    conn.close()


def has_pre_teeoff_frozen(event_id: str) -> bool:
    normalized = str(event_id or "").strip()
    if not normalized:
        return False
    conn = get_conn()
    _ensure_pre_teeoff_tables(conn)
    row = conn.execute(
        "SELECT 1 FROM pre_teeoff_frozen WHERE event_id = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    conn.close()
    return row is not None


def get_pre_teeoff_candidate_payload(event_id: str) -> dict | None:
    normalized = str(event_id or "").strip()
    if not normalized:
        return None
    conn = get_conn()
    _ensure_pre_teeoff_tables(conn)
    row = conn.execute(
        "SELECT payload_json FROM pre_teeoff_candidates WHERE event_id = ?",
        (normalized,),
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def get_pre_teeoff_frozen_payload(event_id: str) -> dict | None:
    normalized = str(event_id or "").strip()
    if not normalized:
        return None
    conn = get_conn()
    _ensure_pre_teeoff_tables(conn)
    row = conn.execute(
        "SELECT payload_json FROM pre_teeoff_frozen WHERE event_id = ?",
        (normalized,),
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return None


def build_final_leaderboard_from_results(event_id: str) -> list[dict]:
    """Build final-position leaderboard rows from graded results (preferred for completed replay)."""
    normalized = str(event_id or "").strip()
    if not normalized:
        return []
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT r.player_key, r.player_display, r.finish_position, r.finish_text, r.made_cut
        FROM results r
        JOIN tournaments t ON t.id = r.tournament_id
        WHERE t.event_id = ?
        ORDER BY
            CASE WHEN r.finish_position IS NULL THEN 1 ELSE 0 END,
            r.finish_position ASC,
            r.player_display ASC
        """,
        (normalized,),
    ).fetchall()
    conn.close()
    if not rows:
        return []

    leaderboard: list[dict] = []
    for index, row in enumerate(rows, start=1):
        finish_text = str(row["finish_text"] or "").strip()
        if not finish_text and row["finish_position"] is not None:
            finish_text = str(row["finish_position"])
        leaderboard.append(
            {
                "rank": index,
                "position": finish_text or None,
                "player_key": row["player_key"],
                "player": row["player_display"] or row["player_key"],
                "finish_state": finish_text or None,
            }
        )
    return leaderboard


def build_completed_snapshot_section(event_id: str, *, source: str = "dashboard") -> dict | None:
    """
    Merge frozen pre-teeoff upcoming board with latest live snapshot leaderboard for Completed replay.
    """
    normalized = str(event_id or "").strip()
    if not normalized:
        return None
    normalized_source = str(source or "dashboard").strip().lower()
    frozen = get_pre_teeoff_frozen_payload(normalized) if normalized_source != "lab" else None
    ranking_source = None
    if not frozen:
        pre_teeoff_section = "lab_upcoming" if normalized_source == "lab" else "upcoming"
        earliest_pre = get_first_snapshot_section(normalized, section=pre_teeoff_section)
        if earliest_pre:
            frozen = (earliest_pre or {}).get("snapshot") or None
            ranking_source = f"recovered_earliest_{pre_teeoff_section}"
        if not frozen:
            latest_pre_teeoff = get_latest_snapshot_section(normalized, section=pre_teeoff_section)
            frozen = (latest_pre_teeoff or {}).get("snapshot") or None
            if frozen:
                ranking_source = f"recovered_latest_{pre_teeoff_section}"
    latest_live = get_latest_snapshot_section(normalized, section="live")
    live_snap = (latest_live or {}).get("snapshot") or {}
    if not frozen and not live_snap:
        results_lb = build_final_leaderboard_from_results(normalized)
        if not results_lb:
            return None
        return {
            "leaderboard": results_lb,
            "completed_replay": True,
            "diagnostics": {"state": "completed_replay", "leaderboard_source": "results_table"},
            "ranking_source": "results_table_only",
        }
    base = dict(frozen) if frozen else dict(live_snap)
    results_lb = build_final_leaderboard_from_results(normalized)
    final_lb = results_lb or live_snap.get("leaderboard") or base.get("leaderboard") or []
    out = dict(base)
    out["leaderboard"] = final_lb
    out["completed_replay"] = True
    out.setdefault("diagnostics", {})
    out["diagnostics"]["state"] = "completed_replay"
    if results_lb:
        out["diagnostics"]["leaderboard_source"] = "results_table"
    if frozen:
        out["frozen_pre_teeoff_rankings"] = frozen.get("rankings") or frozen.get("live_rankings")
        out["ranking_source"] = ranking_source or frozen.get("ranking_source") or (
            "frozen_pre_teeoff_lab_upcoming" if normalized_source == "lab" else "frozen_pre_teeoff_upcoming"
        )
    elif live_snap:
        out["ranking_source"] = "completed_replay_live_fallback"
    return out


def insert_pre_teeoff_frozen(
    event_id: str,
    *,
    tour: str | None,
    event_name: str | None,
    section_payload: dict,
    source_snapshot_id: str | None,
) -> bool:
    """Persist immutable pre-teeoff board once per event. Returns True if inserted."""
    normalized = str(event_id or "").strip()
    if not normalized or not isinstance(section_payload, dict):
        return False
    conn = get_conn()
    _ensure_pre_teeoff_tables(conn)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO pre_teeoff_frozen
            (event_id, tour, event_name, payload_json, frozen_at, source_snapshot_id)
        VALUES (?, ?, ?, ?, datetime('now'), ?)
        """,
        (
            normalized,
            (tour or "").strip().lower() or None,
            (event_name or "").strip() or None,
            json.dumps(section_payload),
            (source_snapshot_id or "").strip() or None,
        ),
    )
    conn.commit()
    inserted = cur.rowcount > 0
    conn.close()
    return inserted


def list_completed_snapshot_events(
    limit: int = 40,
    *,
    exclude_event_ids: set[str] | None = None,
) -> list[dict]:
    """Events available for Completed replay (live history + frozen pre-teeoff).

    `exclude_event_ids` are dropped from both the live-snapshot history source
    and the frozen pre-teeoff source, ensuring the currently active live or
    upcoming event never leaks into the past-event selector.
    """
    excluded = {str(eid).strip() for eid in (exclude_event_ids or set()) if eid}
    conn = get_conn()
    _ensure_pre_teeoff_tables(conn)
    live_rows = list_past_snapshot_events(
        limit=max(int(limit) * 3, 120),
        exclude_event_ids=excluded or None,
    )
    frozen_rows = conn.execute(
        """
        SELECT event_id, event_name, frozen_at
        FROM pre_teeoff_frozen
        ORDER BY frozen_at DESC
        LIMIT ?
        """,
        (max(int(limit) * 3, 120),),
    ).fetchall()
    conn.close()
    merged: dict[str, dict[str, Any]] = {}
    frozen_event_ids = {str(fr["event_id"]).strip() for fr in frozen_rows if fr["event_id"]}
    for row in live_rows:
        eid = str(row.get("event_id") or "").strip()
        if not eid or eid in excluded:
            continue
        merged[eid] = {
            "event_id": eid,
            "event_name": row.get("event_name") or "",
            "latest_generated_at": row.get("latest_generated_at"),
            "snapshot_count": int(row.get("snapshot_count") or 0),
            "has_frozen_pre_teeoff": eid in frozen_event_ids,
        }
    for fr in frozen_rows:
        eid = str(fr["event_id"] or "").strip()
        if not eid or eid in excluded:
            continue
        ts = fr["frozen_at"]
        prev = merged.get(eid)
        if prev is None:
            merged[eid] = {
                "event_id": eid,
                "event_name": fr["event_name"] or "",
                "latest_generated_at": ts,
                "snapshot_count": 1,
                "has_frozen_pre_teeoff": True,
            }
        else:
            prev["has_frozen_pre_teeoff"] = True
            if ts and (not prev.get("latest_generated_at") or str(ts) > str(prev.get("latest_generated_at") or "")):
                prev["latest_generated_at"] = ts
    out = sorted(
        merged.values(),
        key=lambda r: (
            1 if r.get("has_frozen_pre_teeoff") else 0,
            int(r.get("snapshot_count") or 0) > 0,
            str(r.get("latest_generated_at") or ""),
            r["event_id"],
        ),
        reverse=True,
    )
    return out[: int(limit)]


def prune_live_snapshot_history(retain_days: int) -> int:
    """Delete ``live_snapshot_history`` rows older than ``retain_days`` (by ``generated_at``).

    Returns the number of rows deleted. When ``retain_days`` is 0 or negative, performs
    no work and returns 0 (callers should treat non-positive retention as disabled).
    """
    days = int(retain_days)
    if days <= 0:
        return 0
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            DELETE FROM live_snapshot_history
            WHERE generated_at IS NOT NULL
              AND generated_at < ?
            """,
            (cutoff,),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def prune_market_prediction_rows(retain_days: int) -> int:
    """Delete ``market_prediction_rows`` older than ``retain_days`` (by ``generated_at``)."""
    days = int(retain_days)
    if days <= 0:
        return 0
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            DELETE FROM market_prediction_rows
            WHERE generated_at IS NOT NULL
              AND generated_at < ?
            """,
            (cutoff,),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def vacuum_database(*, wal_checkpoint: bool = True) -> dict[str, Any]:
    """Reclaim disk after large DELETEs. Use only during maintenance windows."""
    conn = get_conn()
    try:
        if wal_checkpoint:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.OperationalError as exc:
                _logger.warning("wal_checkpoint failed: %s", exc)
        before = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        conn.execute("VACUUM")
        conn.commit()
        after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "ok": True,
            "bytes_before": before,
            "bytes_after": after,
            "bytes_reclaimed": max(0, before - after),
        }
    finally:
        conn.close()


def store_market_prediction_rows(rows: list[dict]) -> int:
    """Persist matchup/placement rows shown in snapshot surfaces."""
    if not rows:
        return 0

    slim = (os.environ.get("MARKET_PREDICTION_SLIM_PAYLOAD") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if slim:
        seen_snapshots: set[str] = set()
        normalized: list[dict] = []
        for row in rows:
            item = dict(row)
            snap = str(item.get("snapshot_id") or "")
            if snap and snap in seen_snapshots:
                item["payload_json"] = "{}"
            elif snap:
                seen_snapshots.add(snap)
                # First row per snapshot keeps payload for snapshot-level replay.
            normalized.append(item)
        rows = normalized

    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO market_prediction_rows
            (snapshot_id, generated_at, tour, section, event_id, event_name, market_family,
             market_type, player_key, player_display, opponent_key, opponent_display, book,
             odds, model_prob, implied_prob, ev, is_value, payload_json)
        VALUES
            (:snapshot_id, :generated_at, :tour, :section, :event_id, :event_name, :market_family,
             :market_type, :player_key, :player_display, :opponent_key, :opponent_display, :book,
             :odds, :model_prob, :implied_prob, :ev, :is_value, :payload_json)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def append_shadow_event_simulation(
    *,
    snapshot_id: str,
    event_id: str,
    section: str,
    tour: str | None,
    n_sims: int,
    engine_version: str,
    payload_json: dict[str, Any],
) -> int:
    """Append one shadow MC result row (append-only; no updates)."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO shadow_event_simulations
            (snapshot_id, event_id, section, tour, n_sims, engine_version, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            event_id,
            section,
            tour,
            n_sims,
            engine_version,
            json.dumps(payload_json),
        ),
    )
    conn.commit()
    conn.close()
    return 1


def get_market_prediction_rows_for_event(
    event_id: str,
    *,
    market_family: str | None = None,
    section: str | None = None,
    limit: int = 2000,
) -> list[dict]:
    """Fetch historical market rows for an event (used by post-event evaluation)."""
    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        return []
    clauses = ["event_id = ?"]
    params: list[Any] = [normalized_event_id]
    if market_family:
        clauses.append("market_family = ?")
        params.append(str(market_family))
    if section:
        clauses.append("section = ?")
        params.append(str(section))
    params.append(int(limit))
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT *
        FROM market_prediction_rows
        WHERE {' AND '.join(clauses)}
        ORDER BY generated_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    result = [dict(row) for row in rows]
    for row in result:
        raw_payload = row.get("payload_json")
        try:
            row["payload"] = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            row["payload"] = {}
    return result


def _count_market_prediction_rows_for_event(
    event_id: str,
    *,
    sections: tuple[str, ...] | None = None,
) -> int:
    """Count durable market rows for an event (optionally filtered by section)."""
    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        return 0
    conn = get_conn()
    try:
        if sections:
            placeholders = ",".join("?" for _ in sections)
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM market_prediction_rows
                WHERE event_id = ? AND section IN ({placeholders})
                """,
                (normalized_event_id, *sections),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM market_prediction_rows WHERE event_id = ?",
                (normalized_event_id,),
            ).fetchone()
    finally:
        conn.close()
    return int(row["c"] or 0) if row else 0


def get_completed_market_prediction_rows_for_event(
    event_id: str,
    *,
    source: str = "dashboard",
    market_family: str | None = None,
    limit: int = 10000,
    prefer_richest_source: bool = False,
) -> list[dict]:
    """
    Fetch the final pre-teeoff market-row inventory for a completed event.

    Ordered fallbacks when primary ``upcoming`` / ``lab_upcoming`` rows are missing:
    1. Frozen pre-teeoff ledger rows
    2. Latest upcoming / lab_upcoming market rows (original behavior)
    3. Earliest upcoming snapshot in live_snapshot_history
    4. Earliest market_prediction_rows for event (any section, pre-completion)
    5. Recovery: earliest live snapshot (mislabeled historical data)
    """
    normalized_event_id = str(event_id or "").strip()
    if not normalized_event_id:
        return []
    normalized_source = str(source or "dashboard").strip().lower()
    section = "lab_upcoming" if normalized_source == "lab" else "upcoming"

    tiers: list[tuple[str, list[dict]]] = []

    ledger_rows = _ledger_rows_for_completed_event(
        normalized_event_id,
        lane="lab" if normalized_source == "lab" else "cockpit",
        limit=limit,
    )
    recovery_section = "lab_live" if normalized_source == "lab" else "live"
    mpr_section_count = _count_market_prediction_rows_for_event(
        normalized_event_id,
        sections=(recovery_section,),
    )
    if ledger_rows and (mpr_section_count == 0 or len(ledger_rows) >= mpr_section_count * 0.5):
        tiers.append(("pick_ledger_frozen", ledger_rows))

    upcoming_rows = _fetch_market_rows_for_section(
        normalized_event_id,
        section=section,
        market_family=market_family,
        limit=limit,
        order="DESC",
    )
    if upcoming_rows:
        tiers.append(("upcoming_latest", upcoming_rows))

    earliest_history = get_first_snapshot_section(normalized_event_id, section=section)
    if earliest_history:
        hist_rows = _market_rows_from_snapshot_payload(
            earliest_history,
            event_id=normalized_event_id,
            section=section,
            limit=limit,
        )
        if hist_rows:
            tiers.append(("earliest_snapshot_history", hist_rows))

    earliest_any = _fetch_earliest_market_rows_any_section(
        normalized_event_id,
        market_family=market_family,
        limit=limit,
    )
    if earliest_any:
        tiers.append(("earliest_market_rows", earliest_any))

    recovery_section = "lab_live" if normalized_source == "lab" else "live"
    recovery_rows = _fetch_all_market_rows_for_section(
        normalized_event_id,
        section=recovery_section,
        market_family=market_family,
        limit=limit,
    )
    if not recovery_rows:
        recovery_rows = _fetch_all_market_rows_for_section(
            normalized_event_id,
            section="live",
            market_family=market_family,
            limit=limit,
        )
    if recovery_rows:
        tiers.append(("recovered_live_mislabeled", recovery_rows))

    ledger_skipped = bool(
        ledger_rows
        and mpr_section_count > 0
        and len(ledger_rows) < mpr_section_count * 0.5
    )

    scored: list[tuple[str, list[dict], int]] = []
    for tier_name, rows in tiers:
        if not rows:
            continue
        scored.append((tier_name, rows, len(_dedupe_completed_market_rows(rows))))

    if not scored:
        return []

    if prefer_richest_source or ledger_skipped:
        tier_name, rows, _ = max(scored, key=lambda item: item[2])
    else:
        tier_name, rows, _ = scored[0]

    for row in rows:
        row["recovery_tier"] = tier_name
    return _dedupe_completed_market_rows(rows)


def _ledger_rows_for_completed_event(
    event_id: str,
    *,
    lane: str,
    limit: int,
) -> list[dict]:
    conn = get_conn()
    try:
        conn.execute("SELECT 1 FROM pick_ledger LIMIT 1")
    except sqlite3.OperationalError:
        conn.close()
        return []
    rows = conn.execute(
        """
        SELECT * FROM pick_ledger
        WHERE event_id = ? AND lane = ?
          AND lifecycle IN ('frozen_pre_teeoff', 'displayed', 'graded', 'recovered')
        ORDER BY
            CASE lifecycle WHEN 'frozen_pre_teeoff' THEN 0 WHEN 'displayed' THEN 1 ELSE 2 END,
            generated_at ASC
        LIMIT ?
        """,
        (event_id, lane, int(limit)),
    ).fetchall()
    conn.close()
    result: list[dict] = []
    for row in rows:
        d = dict(row)
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        d["section"] = d.get("section") or "upcoming"
        result.append(d)
    return result


def _fetch_all_market_rows_for_section(
    event_id: str,
    *,
    section: str,
    market_family: str | None,
    limit: int,
) -> list[dict]:
    """Fetch all rows for a section (across snapshots) for inventory recovery."""
    clauses = ["event_id = ?", "section = ?"]
    params: list[Any] = [event_id, section]
    if market_family:
        clauses.append("market_family = ?")
        params.append(str(market_family))
    params.append(int(limit))

    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT * FROM market_prediction_rows
        WHERE {' AND '.join(clauses)}
        ORDER BY generated_at ASC, id ASC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()

    result = [dict(row) for row in rows]
    for row in result:
        raw_payload = row.get("payload_json")
        try:
            row["payload"] = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            row["payload"] = {}
    return result


def _fetch_market_rows_for_section(
    event_id: str,
    *,
    section: str,
    market_family: str | None,
    limit: int,
    order: str,
) -> list[dict]:
    clauses = ["event_id = ?", "section = ?"]
    params: list[Any] = [event_id, section]
    if market_family:
        clauses.append("market_family = ?")
        params.append(str(market_family))

    sort = "ASC" if str(order).upper() == "ASC" else "DESC"
    conn = get_conn()
    anchor = conn.execute(
        f"""
        SELECT snapshot_id, generated_at
        FROM market_prediction_rows
        WHERE {' AND '.join(clauses)}
        ORDER BY generated_at {sort}, id {sort}
        LIMIT 1
        """,
        params,
    ).fetchone()
    if not anchor:
        conn.close()
        return []

    anchor_clauses = list(clauses)
    anchor_params = list(params)
    if anchor["snapshot_id"]:
        anchor_clauses.append("snapshot_id = ?")
        anchor_params.append(anchor["snapshot_id"])
    else:
        anchor_clauses.append("generated_at = ?")
        anchor_params.append(anchor["generated_at"])
    anchor_params.append(int(limit))

    rows = conn.execute(
        f"""
        SELECT * FROM market_prediction_rows
        WHERE {' AND '.join(anchor_clauses)}
        ORDER BY id ASC
        LIMIT ?
        """,
        anchor_params,
    ).fetchall()
    conn.close()

    result = [dict(row) for row in rows]
    for row in result:
        raw_payload = row.get("payload_json")
        try:
            row["payload"] = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            row["payload"] = {}
    return result


def _fetch_earliest_market_rows_any_section(
    event_id: str,
    *,
    market_family: str | None,
    limit: int,
) -> list[dict]:
    clauses = ["event_id = ?"]
    params: list[Any] = [event_id]
    if market_family:
        clauses.append("market_family = ?")
        params.append(str(market_family))
    conn = get_conn()
    anchor = conn.execute(
        f"""
        SELECT snapshot_id, generated_at, section
        FROM market_prediction_rows
        WHERE {' AND '.join(clauses)}
        ORDER BY generated_at ASC, id ASC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if not anchor:
        conn.close()
        return []
    anchor_clauses = list(clauses)
    anchor_params = list(params)
    if anchor["snapshot_id"]:
        anchor_clauses.append("snapshot_id = ?")
        anchor_params.append(anchor["snapshot_id"])
    else:
        anchor_clauses.append("generated_at = ?")
        anchor_params.append(anchor["generated_at"])
    anchor_params.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT * FROM market_prediction_rows
        WHERE {' AND '.join(anchor_clauses)}
        ORDER BY id ASC
        LIMIT ?
        """,
        anchor_params,
    ).fetchall()
    conn.close()
    result = [dict(row) for row in rows]
    for row in result:
        raw_payload = row.get("payload_json")
        try:
            row["payload"] = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            row["payload"] = {}
    return result


def _market_rows_from_snapshot_payload(
    snapshot_row: dict,
    *,
    event_id: str,
    section: str,
    limit: int,
) -> list[dict]:
    snap = snapshot_row.get("snapshot") if isinstance(snapshot_row.get("snapshot"), dict) else snapshot_row
    if not isinstance(snap, dict):
        return []
    from backtester.dashboard_runtime import _build_market_prediction_rows

    generated_at = str(snapshot_row.get("generated_at") or snap.get("generated_at") or "")
    snapshot_id = str(snapshot_row.get("snapshot_id") or snap.get("snapshot_id") or generated_at or "history")
    rows = _build_market_prediction_rows(
        snapshot_id=snapshot_id,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        tour=str(snap.get("tour") or "pga"),
        section_name=section,
        section_payload=snap,
    )
    for row in rows:
        row.setdefault("event_id", event_id)
    return rows[: int(limit)]


def _dedupe_completed_market_rows(rows: list[dict]) -> list[dict]:
    """Keep only the best available book line for each completed replay pick."""
    best_by_pick: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        key = _completed_market_row_key(row)
        if not key:
            continue
        current = best_by_pick.get(key)
        if current is None or _american_odds_score(row.get("odds")) > _american_odds_score(current.get("odds")):
            best_by_pick[key] = row
    return list(best_by_pick.values())


def _completed_market_row_key(row: dict) -> tuple[str, str, str, str] | None:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    player_key = _row_player_key(row, payload, "player")
    opponent_key = _row_player_key(row, payload, "opponent")
    if not player_key:
        return None
    market_family = str(row.get("market_family") or "").strip().lower()
    market_type = str(row.get("market_type") or market_family).strip().lower()
    return (market_family, market_type, player_key, opponent_key)


def _row_player_key(row: dict, payload: dict, side: str) -> str:
    if side == "player":
        raw_key = row.get("player_key") or payload.get("player_key") or payload.get("pick_key")
        raw_name = row.get("player_display") or payload.get("player_display") or payload.get("player") or payload.get("pick")
    else:
        raw_key = row.get("opponent_key") or payload.get("opponent_key")
        raw_name = row.get("opponent_display") or payload.get("opponent")
    normalized_key = str(raw_key or "").strip().lower()
    return normalized_key or normalize_name(str(raw_name or ""))


def _american_odds_score(raw_odds: Any) -> float:
    """Higher score means better payout for the picked side."""
    try:
        text = str(raw_odds or "").strip().replace("+", "")
        if not text:
            return float("-inf")
        return float(int(float(text)))
    except (TypeError, ValueError):
        return float("-inf")


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


def reclaim_database_disk(
    *,
    min_free_mb: int | None = None,
    wal_checkpoint: bool = True,
) -> dict[str, Any]:
    """Disk-guarded reclaim after large DELETEs. Refuses when free space is insufficient."""
    import shutil

    from src.disk_guard import warn_if_low_disk

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    warn_if_low_disk(repo_root, context="db_reclaim")

    db_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    usage = shutil.disk_usage(repo_root)
    free_mb = int(usage.free // (1024 * 1024))
    required_mb = min_free_mb
    if required_mb is None:
        raw = (os.environ.get("DISK_RECLAIM_MIN_FREE_MB") or "").strip()
        if raw:
            try:
                required_mb = int(raw)
            except ValueError:
                required_mb = None
    if required_mb is None and db_bytes > 0:
        # Need roughly one full DB copy free for VACUUM / VACUUM INTO swap headroom.
        required_mb = max(1024, int((db_bytes * 1.15) // (1024 * 1024)))

    if required_mb and free_mb < required_mb:
        return {
            "ok": False,
            "skipped": True,
            "reason": (
                f"insufficient free disk: {free_mb} MiB free, need >= {required_mb} MiB"
            ),
            "free_mb": free_mb,
            "required_mb": required_mb,
        }

    if db_bytes >= 5 * 1024 ** 3:
        temp_path = DB_PATH + ".vacuum_into"
        conn = get_conn()
        try:
            if wal_checkpoint:
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.OperationalError as exc:
                    _logger.warning("wal_checkpoint failed: %s", exc)
            before = db_bytes
            escaped = temp_path.replace("'", "''")
            conn.execute(f"VACUUM INTO '{escaped}'")
            conn.commit()
        finally:
            conn.close()
        if not os.path.isfile(temp_path):
            return {"ok": False, "skipped": True, "reason": "VACUUM INTO did not produce output"}
        backup_path = DB_PATH + ".pre_reclaim"
        shutil.copy2(DB_PATH, backup_path)
        os.replace(temp_path, DB_PATH)
        after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "ok": True,
            "method": "vacuum_into_swap",
            "bytes_before": before,
            "bytes_after": after,
            "bytes_reclaimed": max(0, before - after),
            "free_mb": free_mb,
        }

    return vacuum_database(wal_checkpoint=wal_checkpoint)


def prune_snapshot_history_tables(
    retain_days: int | None = None,
    *,
    require_archive: bool | None = None,
) -> dict[str, Any]:
    """Delete rows older than ``retain_days`` from append-heavy live-refresh tables.

    Intended for explicit operator/cron use only — not called from HTTP handlers.

    When ``retain_days`` is None, reads ``SNAPSHOT_HISTORY_RETAIN_DAYS``; if unset,
    returns a skipped result without deleting (default no-op until configured).
    """
    days = retain_days
    if days is None:
        raw = (os.environ.get("SNAPSHOT_HISTORY_RETAIN_DAYS") or "").strip()
        if not raw:
            return {
                "skipped": True,
                "reason": "SNAPSHOT_HISTORY_RETAIN_DAYS not set; refusing delete.",
                "live_snapshot_history_deleted": 0,
                "market_prediction_rows_deleted": 0,
            }
        try:
            days = int(raw)
        except ValueError:
            return {
                "skipped": True,
                "reason": "invalid SNAPSHOT_HISTORY_RETAIN_DAYS",
                "live_snapshot_history_deleted": 0,
                "market_prediction_rows_deleted": 0,
            }
    if int(days) <= 0:
        return {
            "skipped": True,
            "reason": "retain_days must be positive",
            "live_snapshot_history_deleted": 0,
            "market_prediction_rows_deleted": 0,
        }

    from src.cold_archive import snapshot_history_cutoff_utc, verified_archive_exists_for_cutoff

    cutoff = snapshot_history_cutoff_utc(int(days))

    if require_archive is None:
        require_archive = (
            os.environ.get("SNAPSHOT_PRUNE_REQUIRE_ARCHIVE", "1").strip().lower()
            not in {"0", "false", "no", "off"}
        )

    conn = get_conn()
    try:
        old_live = conn.execute(
            """
            SELECT COUNT(*) FROM live_snapshot_history
            WHERE generated_at IS NOT NULL AND generated_at < ?
            """,
            (cutoff,),
        ).fetchone()[0]
        old_market = conn.execute(
            """
            SELECT COUNT(*) FROM market_prediction_rows
            WHERE generated_at IS NOT NULL AND generated_at < ?
            """,
            (cutoff,),
        ).fetchone()[0]
    finally:
        conn.close()

    would_delete = int(old_live) + int(old_market)
    if require_archive and would_delete > 0:
        exports_dir = (os.environ.get("SNAPSHOT_ARCHIVE_EXPORTS_DIR") or "").strip() or None
        if not verified_archive_exists_for_cutoff(cutoff, exports_dir=exports_dir):
            return {
                "skipped": True,
                "reason": (
                    "no verified cold archive for cutoff; export tick tables before prune"
                ),
                "retain_days": int(days),
                "cutoff_utc": cutoff,
                "live_snapshot_history_deleted": 0,
                "market_prediction_rows_deleted": 0,
                "require_archive": True,
                "rows_pending_delete": would_delete,
            }

    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM live_snapshot_history WHERE generated_at IS NOT NULL AND generated_at < ?",
            (cutoff,),
        )
        n1 = conn.execute("SELECT changes()").fetchone()[0]
        conn.execute(
            "DELETE FROM market_prediction_rows WHERE generated_at IS NOT NULL AND generated_at < ?",
            (cutoff,),
        )
        n2 = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {
        "skipped": False,
        "retain_days": int(days),
        "cutoff_utc": cutoff,
        "live_snapshot_history_deleted": int(n1),
        "market_prediction_rows_deleted": int(n2),
        "require_archive": bool(require_archive),
    }


def ensure_initialized():
    """Initialize the database if not already done. Call before first use."""
    global _DB_INITIALIZED
    if not _DB_INITIALIZED:
        init_db()
        _DB_INITIALIZED = True


# Lazy initialization: ensure tables exist on first connection use.
# This replaces the old module-level init_db() call so .env can load first.
ensure_initialized()
