# Data contracts

Canonical stores for analytics, grading, backtests, and the dashboard.  
**Rule:** pick the table for your question — do not mix them casually.

| Contract | Table / view | Use when you need… |
|----------|--------------|-------------------|
| **DisplayedPick** | `picks` | What the UI showed or we staked (`source` in `cockpit`, `ui_display`, `lab`) |
| **GradedOutcome** | `v_displayed_picks_graded` | Pick + hit/miss/profit |
| **CalibrationObservation** | `prediction_log` | Model vs market vs outcome time series (first row per key wins) |
| **MarketLineSnapshot** | `market_prediction_rows` | Every book line on every live-refresh tick |
| **PipelineRun** | `runs` | Pipeline metadata (field size, duration, errors) |
| **PITFeatureRow** | `pit_rolling_stats`, `pit_course_stats` | Walk-forward backtests only (no future data) |
| **TrackConfig** | `track_configs` | Which config produced a track's boards/picks (dashboard champion vs lab challenger), with a stable `config_hash` |

## DisplayedPick

- **Keys:** `(tournament_id, model_variant, source, player_key, bet_type, opponent_key, market_book, market_odds)`
- **Writers:** `GolfModelService._store_displayed_picks`, lab persist helpers
- **Note:** Stored even when run-quality gate blocks `prediction_log`
- **Provenance:** `model_config_hash` records which `track_configs.config_hash` epoch produced the pick (joins to TrackConfig). `pick_source`/`source` still distinguishes the lane (`cockpit`/`ui_display` = dashboard, `lab_sandbox*` = lab).

## TrackConfig

- **Writer:** `src/track_registry.py` (`seed_default_tracks`, read-only in Wave 1; promotion/rollback wired later)
- **Rows:** one `active` row per `track` (`dashboard`, `lab`) holding the canonical `strategy_bundle_json`, `model_variant`, and `config_hash`
- **Runtime precedence (unchanged):** env (`COCKPIT_SNAPSHOT_MODEL_VARIANT`) > registry seed > lab champion file > default. The seed mirrors current effective config, so behavior is identical.
- **API:** `GET /api/tracks` (both slots + `effective_config_hash` + activation history). `config_hash` is also stamped into snapshot `strategy_meta.config_hash`.

## CalibrationObservation

- **Writer:** `learning.log_predictions_for_tournament` → `db.log_predictions` (`INSERT OR IGNORE`)
- **Gate:** Placement rows only if `compute_run_quality` passes
- **Timing:** `odds_timing` column (`pre_tournament` vs `in_play`)

## MarketLineSnapshot

- **Writer:** `backtester/dashboard_runtime` → `store_market_prediction_rows`
- **Retention:** pruned via `SNAPSHOT_HISTORY_RETAIN_DAYS` (default 210)

## SQL views

Created by `src/data_views.ensure_analytics_views()`:

- `v_displayed_picks_graded`
- `v_tournament_data_health`
- `v_2026_monthly_coverage`

See also [storage-retention.md](storage-retention.md) for what may be deleted vs kept forever.
