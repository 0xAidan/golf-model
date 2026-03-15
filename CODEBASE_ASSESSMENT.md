# Golf Betting Model - Comprehensive Codebase Assessment

**Date:** February 28, 2026  
**Codebase Location:** `/Users/aidannugent/Documents/golf-model/`

---

## Executive Summary

This is a sophisticated golf betting prediction system that combines:
- **Data Golf API** integration for historical rounds, predictions, and field data
- **Composite scoring model** (Course Fit + Form + Momentum)
- **AI Brain** layer for qualitative analysis and adjustments
- **Market adaptation** system for dynamic betting strategy
- **Backtesting framework** with point-in-time (PIT) stats
- **Autonomous research agent** for continuous improvement

The codebase is well-structured but contains numerous magic numbers, some disabled features, and areas needing refactoring.

---

## 1. Module Dependency Graph

### Core Entry Points
```
run_predictions.py
  ├─> src.services.golf_model_service
  ├─> src.db
  ├─> src.datagolf
  └─> src.config_loader

analyze.py
  └─> src.services.golf_model_service

app.py (FastAPI)
  ├─> src.csv_parser
  ├─> src.db
  ├─> src.models.composite
  ├─> src.odds
  └─> src.value

start.py (Unified Launcher)
  ├─> src.services.golf_model_service
  ├─> workers.research_agent
  ├─> backtester.backfill
  └─> backtester.strategy
```

### Model Components
```
src.models.composite
  ├─> src.models.course_fit
  ├─> src.models.form
  ├─> src.models.momentum
  ├─> src.models.weather
  └─> src.db

src.models.course_fit
  ├─> src.db
  └─> src.course_profile

src.models.form
  └─> src.db

src.models.momentum
  └─> src.db

src.models.weights
  └─> src.db
```

### Data Layer
```
src.db (SQLite)
  └─> (no dependencies - core DB layer)

src.datagolf
  ├─> src.db
  ├─> src.player_normalizer
  └─> requests

src.csv_parser
  ├─> src.db
  ├─> src.player_normalizer
  └─> pandas

src.rolling_stats
  ├─> src.db
  └─> src.player_normalizer
```

### Betting & Value
```
src.value
  ├─> src.odds
  ├─> src.player_normalizer
  ├─> src.db
  └─> src.adaptation

src.matchup_value
  ├─> src.player_normalizer
  └─> src.adaptation

src.matchups
  └─> (standalone)

src.odds
  └─> requests
```

### Learning & Adaptation
```
src.learning
  ├─> src.db
  ├─> src.player_normalizer
  ├─> src.scoring
  ├─> src.datagolf
  ├─> src.adaptation
  ├─> src.models.weights
  └─> src.calibration

src.adaptation
  └─> src.db

src.calibration
  └─> src.db
```

### AI Layer
```
src.ai_brain
  ├─> src.db
  ├─> src.player_normalizer
  ├─> src.prompts
  ├─> src.confidence
  ├─> openai
  ├─> anthropic
  └─> google.generativeai

src.prompts
  └─> (standalone - string constants)
```

### Backtester
```
backtester.strategy
  ├─> src.db
  ├─> src.player_normalizer
  ├─> src.scoring
  └─> backtester.pit_models

backtester.pit_models
  └─> src.db

backtester.pit_stats
  ├─> src.db
  └─> src.datagolf

backtester.backfill
  ├─> src.db
  ├─> src.datagolf
  └─> src.player_normalizer

backtester.experiments
  ├─> src.db
  └─> backtester.strategy

backtester.outlier_investigator
  ├─> src.db
  └─> src.player_normalizer
```

### Workers
```
workers.research_agent
  ├─> backtester.backfill
  ├─> backtester.pit_stats
  ├─> backtester.experiments
  ├─> backtester.outlier_investigator
  └─> src.ai_brain

workers.intel_harvester
  ├─> src.db
  └─> src.player_normalizer
```

---

## 2. Full Data Flow: API Call → Output Card

### Phase 1: Data Collection & Storage

1. **Entry Point** (`run_predictions.py` or `analyze.py`)
   - Loads API keys from `.env`
   - Loads profile config from `profiles.yaml`
   - Calls `GolfModelService.run_analysis()`

2. **Event Detection** (`src.services.golf_model_service.py:run_analysis`)
   - Detects current tournament via Data Golf API
   - Creates/retrieves tournament record in DB

3. **Historical Data Backfill** (if enabled)
   - `src.datagolf.fetch_historical_rounds()` → `src.db.store_rounds()`
   - Stores round-level SG stats in `rounds` table
   - Progress tracked in `backfill_progress` table

4. **Data Golf Sync** (`src.datagolf.sync_tournament`)
   - `fetch_pre_tournament()` → stores predictions as metrics
   - `fetch_decompositions()` → stores SG breakdowns
   - `fetch_field_updates()` → stores field list
   - `fetch_skill_ratings()` → stores player skill data
   - `fetch_approach_skill()` → stores approach-specific data

5. **Rolling Stats Computation** (`src.rolling_stats.compute_rolling_metrics`)
   - Reads from `rounds` table
   - Computes rolling averages for windows: 8, 12, 16, 24, "all"
   - Computes field-relative ranks
   - Stores in `metrics` table (same schema as CSV imports)

### Phase 2: Model Execution

6. **Composite Score Calculation** (`src.models.composite.compute_composite`)
   - Calls `src.models.course_fit.compute_course_fit()`
     - Reads course-specific SG ranks from `metrics` table
     - Applies confidence scaling based on rounds played
     - Blends with DG decomposition/skill data
   - Calls `src.models.form.compute_form()`
     - Auto-discovers available round windows
     - Integrates SG ranks, DG skill ratings, DG rankings
     - Applies sample size confidence adjustment
   - Calls `src.models.momentum.compute_momentum()`
     - Compares SG:TOT ranks across multiple windows
     - Uses percentage-based improvement metric
     - Applies elite stability bonus
   - Combines with configurable weights (default: 40% course_fit, 40% form, 20% momentum)
   - Applies weather adjustments if enabled (`src.models.weather.compute_weather_adjustments`)

7. **AI Analysis** (if enabled, `src.ai_brain.pre_tournament_analysis`)
   - Loads AI memories from `ai_memory` table
   - Generates narrative, key factors, player adjustments
   - Stores analysis in `ai_decisions` table
   - Applies adjustments to composite scores

### Phase 3: Value Bet Identification

8. **Odds Fetching** (`src.odds.fetch_odds_api` or `load_manual_odds`)
   - Fetches live odds from The Odds API
   - Or loads from manual JSON file
   - Stores best odds per player/market

9. **Value Calculation** (`src.value.find_value_bets`)
   - Converts composite scores to probabilities via softmax (`model_score_to_prob`)
   - Blends with Data Golf calibrated probabilities
   - Computes Expected Value (EV) = (model_prob / market_prob) - 1.0
   - Filters by EV threshold (from adaptation state)
   - Filters suspicious odds (very high EV, low market prob)

10. **Matchup Value** (`src.matchup_value.find_matchup_value_bets`)
    - Uses composite scores to predict matchup winners
    - Compares against sportsbook matchup odds
    - Finds EV opportunities

### Phase 4: Output Generation

11. **Card Generation** (`src.card.generate_card`)
    - Formats model rankings
    - Lists value bets by market
    - Includes AI analysis (if enabled)
    - Includes market adaptation status
    - Includes data quality warnings
    - Writes markdown file

12. **Methodology Document** (`src.methodology.generate_methodology`)
    - Generates detailed methodology explanation
    - Documents model version, weights, data sources
    - Writes markdown file

### Phase 5: Post-Tournament Learning (after event completes)

13. **Results Entry** (`results.py` or `app.py:/api/results`)
    - Stores tournament results in `results` table
    - Scores picks using `src.scoring.determine_outcome`

14. **Post-Tournament Learning** (`src.learning.post_tournament_learn`)
    - Scores picks for tournament
    - Logs predictions for calibration (`src.calibration.update_calibration_curve`)
    - Updates course weights (`src.learning.update_course_weights`)
    - Runs AI post-review (`src.ai_brain.post_tournament_review`)
    - Stores learnings in `ai_memory` table

15. **Market Adaptation** (`src.adaptation.get_adaptation_state`)
    - Computes rolling ROI from `market_performance` table
    - Adjusts EV thresholds and stake multipliers
    - States: "normal", "caution", "cold", "frozen"

---

## 3. Ranked Code Quality Issues

### CRITICAL (Must Fix)

1. **Disabled AI Betting Decisions** (`src/ai_brain.py:make_betting_decisions`)
   - **Line:** ~200
   - **Issue:** Major feature explicitly disabled, returns `None`
   - **Impact:** AI brain cannot make betting decisions, only provides adjustments
   - **Fix:** Re-enable or remove if permanently disabled

2. **Magic Numbers Everywhere**
   - **Locations:** Throughout codebase
   - **Examples:**
     - `src/value.py`: EV thresholds (0.05, 0.15), blend weights (0.7, 0.3)
     - `src/adaptation.py`: ROI thresholds (-10%, -20%), EV adjustments
     - `src/models/weather.py`: Wind thresholds (15 km/h), adjustment magnitudes
     - `src/confidence.py`: Confidence weights and thresholds
   - **Impact:** Hard to tune, no single source of truth
   - **Fix:** Move to `profiles.yaml` or `src/config.py`

3. **Duplicate Constants**
   - **Locations:**
     - `MAX_REASONABLE_ODDS` duplicated in `src/datagolf.py` and `src/odds.py`
     - `_american_to_implied_prob` duplicated in `src/matchup_value.py` and `src/odds.py`
   - **Impact:** Inconsistency risk
   - **Fix:** Centralize in `src/odds.py`

4. **Broad Exception Handling**
   - **Location:** `src/db.py` migration blocks
   - **Issue:** `try-except` catches all exceptions, masks real errors
   - **Impact:** Silent failures, hard to debug
   - **Fix:** Catch specific exceptions, log properly

5. **Model Version Discrepancy**
   - **Locations:** `src/card.py` mentions v3.0, `src/methodology.py` mentions v4.0
   - **Impact:** Confusion about actual model version
   - **Fix:** Standardize version number

### HIGH PRIORITY (Should Fix)

6. **Deprecated Function Still Used**
   - **Location:** `src/matchups.py:_suggest_matchups` marked DEPRECATED but still called in `src/card.py`
   - **Impact:** Technical debt, unclear which function to use
   - **Fix:** Remove deprecated function or update callers

7. **Hardcoded Default Weights**
   - **Location:** `src/db.py:DEFAULT_WEIGHTS`
   - **Issue:** Hardcoded dict instead of configurable
   - **Impact:** Cannot change defaults without code change
   - **Fix:** Move to `profiles.yaml`

8. **Inefficient Rate Limiting**
   - **Location:** `src/datagolf.py` uses `time.sleep()` for rate limiting
   - **Issue:** Blocks entire thread, inefficient for large fetches
   - **Impact:** Slow data collection
   - **Fix:** Use async/await or background queue

9. **CSV Parser Brittleness**
   - **Location:** `src/csv_parser.py`
   - **Issue:** Relies on magic strings/keywords for file classification
   - **Impact:** Breaks if CSV format changes
   - **Fix:** Use more robust detection (column presence, data types)

10. **Missing Error Handling**
    - **Locations:** Multiple API calls lack proper error handling
    - **Examples:** `src/odds.py` uses `print()` for warnings instead of logging
    - **Impact:** Errors may go unnoticed
    - **Fix:** Use structured logging throughout

### MEDIUM PRIORITY (Nice to Fix)

11. **Large String Prompts**
    - **Location:** `src/prompts.py`
    - **Issue:** All prompts are hardcoded string literals
    - **Impact:** Hard to version, test, or A/B test prompts
    - **Fix:** Move to separate files or database

12. **Conservative Weight Adjustment**
    - **Location:** `src/models/weights.py:suggest_weight_adjustment`
    - **Issue:** Only adjusts 25% of gap, capped at 5% per cycle
    - **Impact:** Very slow convergence
    - **Fix:** Make adjustment rate configurable

13. **Simplified AI Adjustment Evaluation**
    - **Location:** `src/adaptation.py:evaluate_ai_adjustments`
    - **Issue:** Logic is simplified, may not capture full impact
    - **Impact:** May not accurately assess AI value
    - **Fix:** Implement more sophisticated evaluation

14. **Hardcoded Portfolio Limits**
    - **Location:** `src/portfolio.py`
    - **Issue:** Limits like `MAX_BETS_PER_PLAYER`, `MIN_UNIQUE_PLAYERS` are magic numbers
    - **Impact:** Cannot tune without code change
    - **Fix:** Move to config

15. **Weather Assumptions**
    - **Location:** `src/models/weather.py`
    - **Issue:** Assumes PGA Tour tee time rotation (AM/PM waves)
    - **Impact:** May not work for other tours
    - **Fix:** Make tour-specific or configurable

### LOW PRIORITY (Technical Debt)

16. **Empty `__init__.py` Files**
    - **Locations:** Multiple package `__init__.py` files are empty
    - **Impact:** Minor - could expose package-level utilities
    - **Fix:** Add package-level exports if needed

17. **Inconsistent Naming**
    - **Examples:** `dg_id` vs `player_dg_id`, `fin_text` vs `finish_text`
    - **Impact:** Minor confusion
    - **Fix:** Standardize naming conventions

18. **Missing Type Hints**
    - **Location:** Many functions lack type hints
    - **Impact:** Harder to understand function signatures
    - **Fix:** Add type hints gradually

19. **Dead Code**
    - **Location:** `src/card.py:_suggest_matchups` (deprecated)
    - **Impact:** Clutters codebase
    - **Fix:** Remove unused functions

20. **Documentation Gaps**
    - **Issue:** Some complex functions lack docstrings
    - **Impact:** Harder for new developers
    - **Fix:** Add comprehensive docstrings

---

## 4. Test Coverage Assessment

### Existing Tests

**Test Files Found:**
- `tests/test_value.py` - Tests probability normalization and odds validation
- `tests/test_form.py` - Tests score scaling and weight summing
- `tests/test_momentum.py` - Tests dampened scoring, elite floor, confidence
- `tests/test_calibration.py` - Tests calibration curve logic
- `tests/test_adaptation.py` - Tests market performance aggregation
- `tests/test_db.py` - Tests database deduplication and constraints
- `tests/test_matchup_value.py` - Tests matchup value calculation

### Coverage Gaps

**Critical Missing Tests:**
1. **No integration tests** - No tests for full pipeline (`run_predictions.py` → card generation)
2. **No API tests** - No tests for Data Golf API client (`src/datagolf.py`)
3. **No model tests** - No tests for `src/models/course_fit.py`
4. **No AI tests** - No tests for `src/ai_brain.py` (would require mocking)
5. **No backtester tests** - No tests for `backtester/strategy.py` or PIT models
6. **No CSV parser tests** - No tests for `src/csv_parser.py` edge cases
7. **No scoring tests** - No tests for `src/scoring.py` dead-heat logic
8. **No weather tests** - No tests for `src/models/weather.py`

### Test Quality

**Strengths:**
- Tests use pytest (standard framework)
- Tests cover edge cases (zero values, None handling)
- Tests use temp databases (`test_db.py`)

**Weaknesses:**
- No fixtures for common test data
- No mocking of external APIs
- No performance tests
- No tests for error handling paths

### Recommendations

1. **Add integration tests** for full pipeline
2. **Mock external APIs** (Data Golf, The Odds API, OpenAI)
3. **Add fixtures** for common test data (tournaments, players, rounds)
4. **Test error paths** (API failures, missing data, invalid inputs)
5. **Add performance tests** for large datasets
6. **Test PIT stats** to ensure no data leakage

---

## 5. Configuration Management Assessment

### Current State

**Configuration Files:**
1. **`.env`** - API keys and environment variables
   - `DATAGOLF_API_KEY`
   - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
   - `ODDS_API_KEY`
   - `AI_BRAIN_PROVIDER`, `AI_BRAIN_MODEL`

2. **`profiles.yaml`** - Execution profiles
   - `tour` (pga, euro, kft, alt)
   - `enable_ai` (boolean)
   - `enable_backfill` (boolean)
   - `backfill_years` (list)
   - `output_dir` (string)

**Issues:**
1. **Magic numbers not in config** - Most thresholds, weights, limits are hardcoded
2. **No validation** - No schema validation for `profiles.yaml`
3. **No defaults file** - No `profiles.default.yaml` for reference
4. **Scattered config** - Some config in code, some in YAML, some in DB
5. **No environment-specific configs** - Same config for dev/prod

### Recommendations

1. **Create `src/config.py`** - Centralized configuration module
2. **Move all magic numbers to config** - Thresholds, weights, limits
3. **Add config validation** - Use `pydantic` or `jsonschema`
4. **Create config schema** - Document all available options
5. **Support environment-specific configs** - `profiles.dev.yaml`, `profiles.prod.yaml`
6. **Version config** - Track config changes in git

---

## 6. Database Schema Assessment

### Tables Overview

**Core Tables:**
- `tournaments` - Tournament metadata
- `rounds` - Historical round-level SG data (from Data Golf)
- `metrics` - Computed rolling stats and rankings
- `results` - Tournament finish positions
- `picks` - Model picks/bets
- `pick_outcomes` - Bet results (win/loss)

**AI Tables:**
- `ai_memory` - Persistent AI learnings
- `ai_decisions` - AI analysis outputs
- `ai_adjustments` - AI player adjustments

**Learning Tables:**
- `prediction_log` - Calibration data
- `calibration_curve` - Empirical probability corrections
- `weight_sets` - Historical model weights
- `market_performance` - Rolling ROI tracking

**Backtester Tables:**
- `pit_rolling_stats` - Point-in-time rolling stats
- `pit_course_stats` - Point-in-time course-specific stats
- `historical_predictions` - Archived DG predictions
- `historical_odds` - Archived odds snapshots
- `historical_event_info` - Event metadata
- `tournament_weather` - Hourly weather data
- `tournament_weather_summary` - Per-round weather summaries
- `backfill_progress` - Backfill tracking

**Experiment Tables:**
- `experiments` - Strategy experiments
- `active_strategy` - Currently active strategy
- `outlier_investigations` - Prediction miss analysis
- `equipment_changes` - Player equipment tracking
- `intel_events` - External intelligence

**Support Tables:**
- `csv_imports` - CSV import tracking
- `runs` - Pipeline execution logs
- `course_encyclopedia` - Course metadata

### Schema Issues

1. **No Foreign Key Constraints** (except in `test_db.py`)
   - **Impact:** Data integrity not enforced
   - **Fix:** Add foreign keys, enable `PRAGMA foreign_keys = ON`

2. **Inconsistent Naming**
   - `dg_id` vs `player_dg_id`
   - `fin_text` vs `finish_text`
   - **Fix:** Standardize column names

3. **Missing Indexes**
   - `rounds` table: No index on `(player_key, event_completed)`
   - `metrics` table: No index on `(tournament_id, player_key, metric_category)`
   - **Impact:** Slow queries on large datasets
   - **Fix:** Add strategic indexes

4. **No Data Validation**
   - No CHECK constraints for valid ranges
   - No NOT NULL constraints where appropriate
   - **Fix:** Add constraints

5. **Migration Logic in Code**
   - `src/db.py` has inline migration logic
   - **Impact:** Hard to track schema changes
   - **Fix:** Use migration tool (Alembic) or separate migration files

6. **No Schema Versioning**
   - No `schema_version` table
   - **Impact:** Cannot detect schema mismatches
   - **Fix:** Add version tracking

### Recommendations

1. **Add foreign key constraints** to all relationships
2. **Create indexes** for common query patterns
3. **Add CHECK constraints** for data validation
4. **Use migration tool** (Alembic) for schema changes
5. **Document schema** in `docs/schema.md`
6. **Add schema versioning** table

---

## 7. File-by-File Summary

### Entry Points

**`run_predictions.py`** (Main CLI entry point)
- Orchestrates full pipeline
- Handles API key loading, event detection, data sync, model execution
- **Issues:** Sequential execution, no parallelization
- **Dependencies:** `src.services.golf_model_service`, `src.db`, `src.datagolf`

**`analyze.py`** (Analysis CLI)
- Delegates to `GolfModelService`
- Supports CSV folder, manual odds, AI, backfill
- **Issues:** None major
- **Dependencies:** `src.services.golf_model_service`

**`app.py`** (FastAPI Web UI)
- Comprehensive web interface with 8 tabs
- Handles CSV uploads, Data Golf sync, AI analysis, backtesting
- **Issues:** Large file (1700+ lines), could be split into modules
- **Dependencies:** FastAPI, uvicorn, all core modules

**`start.py`** (Unified Launcher)
- Interactive menu + subcommands
- Routes to appropriate modules
- **Issues:** None major
- **Dependencies:** All major modules

### Core Models

**`src/models/composite.py`**
- Combines course_fit, form, momentum scores
- Applies weather adjustments
- **Issues:** Magic numbers for weight redistribution
- **Dependencies:** `src.models.course_fit`, `src.models.form`, `src.models.momentum`, `src.models.weather`

**`src/models/course_fit.py`**
- Calculates player suitability for course
- Uses course-specific SG ranks, confidence scaling
- **Issues:** Magic numbers for time decay, confidence thresholds
- **Dependencies:** `src.db`, `src.course_profile`

**`src/models/form.py`**
- Measures recent performance
- Auto-discovers round windows
- **Issues:** Magic numbers for weights, sample size thresholds
- **Dependencies:** `src.db`

**`src/models/momentum.py`**
- Assesses trending up/down
- Compares ranks across windows
- **Issues:** Magic numbers for elite threshold, floor values
- **Dependencies:** `src.db`

**`src/models/weights.py`**
- Manages model weights
- Analyzes pick performance, suggests adjustments
- **Issues:** Conservative adjustment rate (25% of gap)
- **Dependencies:** `src.db`

**`src/models/weather.py`**
- Fetches forecasts, computes adjustments
- **Issues:** Many magic numbers, assumes PGA Tour rotation
- **Dependencies:** `requests`, `src.db`

### Data Layer

**`src/db.py`** (Database abstraction)
- SQLite connection management
- Schema definition and migrations
- **Issues:** Broad exception handling, hardcoded defaults, no foreign keys
- **Dependencies:** None (core layer)

**`src/datagolf.py`** (Data Golf API client)
- Fetches historical rounds, predictions, decompositions, field updates
- **Issues:** Uses `time.sleep()` for rate limiting, duplicate constants
- **Dependencies:** `requests`, `src.db`, `src.player_normalizer`

**`src/csv_parser.py`** (Betsperts CSV parser)
- Classifies file types, detects data modes
- **Issues:** Brittle (relies on magic strings)
- **Dependencies:** `pandas`, `src.db`, `src.player_normalizer`

**`src/rolling_stats.py`** (Rolling stats computation)
- Replaces CSV ingestion by computing from rounds table
- **Issues:** None major
- **Dependencies:** `src.db`, `src.player_normalizer`

### Betting & Value

**`src/value.py`** (Value bet detection)
- Converts scores to probabilities, finds EV bets
- **Issues:** Many magic numbers (EV thresholds, blend weights)
- **Dependencies:** `src.odds`, `src.player_normalizer`, `src.db`, `src.adaptation`

**`src/matchup_value.py`** (Matchup value)
- Finds value in real sportsbook matchups
- **Issues:** Duplicates `_american_to_implied_prob`
- **Dependencies:** `src.player_normalizer`, `src.adaptation`

**`src/matchups.py`** (Model-only matchups)
- Enhanced matchup engine
- **Issues:** Deprecated function still present
- **Dependencies:** None

**`src/odds.py`** (Odds fetching)
- Fetches from The Odds API, loads manual odds
- **Issues:** Uses `print()` instead of logging
- **Dependencies:** `requests`

### Learning & Adaptation

**`src/learning.py`** (Post-tournament learning)
- Orchestrates learning cycle
- **Issues:** Magic numbers for thresholds, duplicates calibration logic
- **Dependencies:** `src.db`, `src.player_normalizer`, `src.scoring`, `src.datagolf`, `src.adaptation`, `src.models.weights`, `src.calibration`

**`src/calibration.py`** (Probability calibration)
- Manages empirical calibration curve
- **Issues:** Hardcoded probability buckets
- **Dependencies:** `src.db`

**`src/adaptation.py`** (Market adaptation)
- Tracks performance, adjusts strategy
- **Issues:** Many magic numbers, simplified AI evaluation
- **Dependencies:** `src.db`

### AI Layer

**`src/ai_brain.py`** (AI abstraction)
- Provider abstraction (OpenAI, Anthropic, Gemini)
- Pre-tournament analysis, post-review, adjustments
- **Issues:** `make_betting_decisions` disabled, hardcoded portfolio limits
- **Dependencies:** `src.db`, `src.player_normalizer`, `src.prompts`, `src.confidence`, AI SDKs

**`src/prompts.py`** (AI prompts)
- Large string literals for all prompts
- **Issues:** Hard to version/test prompts
- **Dependencies:** None

### Utilities

**`src/player_normalizer.py`** (Name normalization)
- Consistent player key and display names
- **Issues:** None major
- **Dependencies:** None

**`src/scoring.py`** (Bet outcome determination)
- Unified scoring with dead-heat handling
- **Issues:** Hardcoded `MARKET_THRESHOLDS`
- **Dependencies:** None

**`src/confidence.py`** (Model confidence)
- Calculates confidence from measurable factors
- **Issues:** Many magic numbers
- **Dependencies:** None

**`src/card.py`** (Output generation)
- Generates markdown betting card
- **Issues:** Uses deprecated function, version discrepancy
- **Dependencies:** `src.matchups`, `src.adaptation`

**`src/methodology.py`** (Methodology document)
- Generates detailed methodology
- **Issues:** Version discrepancy with `card.py`
- **Dependencies:** None

**`src/course_profile.py`** (Course profiling)
- Extracts from screenshots (AI vision) or auto-generates
- **Issues:** Requires API keys, large hardcoded prompt
- **Dependencies:** `openai`, `anthropic` (conditional)

### Backtester

**`backtester/strategy.py`** (Strategy simulation)
- Replays historical events with PIT stats
- **Issues:** None major
- **Dependencies:** `src.db`, `src.player_normalizer`, `src.scoring`, `backtester.pit_models`

**`backtester/pit_models.py`** (PIT sub-models)
- Mirrors live models using PIT data
- **Issues:** None major
- **Dependencies:** `src.db`

**`backtester/pit_stats.py`** (PIT stats builder)
- Builds point-in-time stats (no future leakage)
- **Issues:** None major
- **Dependencies:** `src.db`, `src.datagolf`

**`backtester/backfill.py`** (Historical backfill)
- Fetches historical data from multiple sources
- **Issues:** None major
- **Dependencies:** `src.db`, `src.datagolf`, `src.player_normalizer`

**`backtester/experiments.py`** (Experiment tracking)
- Manages strategy experiments, significance testing
- **Issues:** None major
- **Dependencies:** `src.db`, `backtester.strategy`

**`backtester/outlier_investigator.py`** (Outlier analysis)
- Investigates prediction misses
- **Issues:** None major
- **Dependencies:** `src.db`, `src.player_normalizer`

### Workers

**`workers/research_agent.py`** (Autonomous agent)
- 5-thread daemon for continuous improvement
- **Issues:** None major
- **Dependencies:** All backtester modules, `src.ai_brain`

**`workers/intel_harvester.py`** (Intel collection)
- Scrapes external sources for player intelligence
- **Issues:** None major
- **Dependencies:** `src.db`, `src.player_normalizer`

---

## 8. Recommendations Summary

### Immediate Actions

1. **Fix disabled AI betting decisions** - Re-enable or remove
2. **Centralize magic numbers** - Create `src/config.py`
3. **Remove duplicate constants** - Consolidate in `src/odds.py`
4. **Fix model version discrepancy** - Standardize to v4.0
5. **Remove deprecated functions** - Clean up `_suggest_matchups`

### Short-Term Improvements

6. **Add integration tests** - Test full pipeline
7. **Improve error handling** - Use structured logging
8. **Add database indexes** - Improve query performance
9. **Add foreign key constraints** - Enforce data integrity
10. **Create config schema** - Document all options

### Long-Term Enhancements

11. **Refactor large files** - Split `app.py` into modules
12. **Add async support** - Use async/await for API calls
13. **Implement migration tool** - Use Alembic for schema changes
14. **Add performance monitoring** - Track execution times
15. **Create API documentation** - Document all endpoints

---

## Conclusion

This is a well-architected golf betting prediction system with sophisticated features. The main areas for improvement are:

1. **Configuration management** - Too many magic numbers hardcoded
2. **Test coverage** - Missing integration and API tests
3. **Code quality** - Some disabled features, deprecated code, duplicates
4. **Database schema** - Missing constraints, indexes, versioning

The system is functional and production-ready, but would benefit from the improvements outlined above.

---

**Assessment completed:** February 28, 2026
