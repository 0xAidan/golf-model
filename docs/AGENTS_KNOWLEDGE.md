# Golf Model — Agent Knowledge Base

**Purpose:** Single reference for AI agents working in this repo. Attach this doc to new chats so agents can execute tasks without scanning the codebase. Update this file when structure, conventions, or critical paths change.

**Audience:** AI agents (LLM instances). Optimized for programmatic parsing and minimal ambiguity; not optimized for human narrative.

**Last verified:** 2026-04-06. Model version: 4.2. Test count: 138 (across 35 test files). app.py: 2916 lines. Frontend: React + Vite + TypeScript.

---

## 1. Project Summary

- **What it is:** Quantitative golf betting system. Data Golf API → round-level SG data, predictions, odds. Composite model (course fit + form + momentum) scores players; value layer compares model vs market for EV; AI layer does qualitative analysis and persistent memory. Post-tournament: grade picks, calibration, weight nudges, AI learnings. Autoresearch system proposes, backtests, and promotes strategy changes autonomously.
- **Stack:** Python 3.11+, SQLite (`data/golf.db`, gitignored, auto-created at runtime by `setup_wizard.py` or first pipeline run), FastAPI for API. Frontend: React 19 + Vite + TypeScript + Tailwind CSS + shadcn/ui (`frontend/`). Built to `frontend/dist/` and served by FastAPI at `/` — the React SPA is the sole UI.
- **Key constraints:** Walk-forward backtesting only (no future data). Bootstrap phases (shadow → paper → cautious live → full live). Stopping rules and go-live gates in project charter. See section 8.
- **CI:** GitHub Actions at `.github/workflows/ci.yml`.

---

## 2. Repository Layout (Critical Paths)

```
golf-model/
│
│ ── ENTRY POINTS ──────────────────────────────────────────────
├── run_predictions.py       # CLI: full prediction pipeline (primary entry point)
├── app.py                   # FastAPI web UI + API (2916 lines; dashboard at :8000, docs at /docs)
├── start.py                 # Unified launcher (interactive menu + subcommands)
├── setup_wizard.py          # First-time setup: backfill data, init DB
├── analyze.py               # CLI with own pipeline; --service flag delegates to GolfModelService
├── results.py               # Results entry / grading CLI
├── dashboard.py             # Performance summary + weight retune CLI (--retune, --dry)
├── course.py                # Course profile extraction from screenshots CLI
├── setup.py                 # Older setup wizard (precedes setup_wizard.py; still functional)
│
│ ── CONFIG / PROJECT FILES ────────────────────────────────────
├── .env                     # API keys (from .env.example); NEVER commit; gitignored
├── .env.example             # Template for required keys
├── feature_flags.yaml       # Toggles: kelly_sizing, clv_tracking, exposure_caps, etc.
├── profiles.yaml            # Run profiles: default, quick, full
├── pyproject.toml           # Project metadata
├── requirements.txt         # Python dependencies (pinned)
├── setup.py                 # Legacy setup script
├── deploy.sh                # One-command VPS deployment (--setup, --update, --status)
├── .pre-commit-config.yaml  # Pre-commit hooks
├── .github/workflows/ci.yml # GitHub Actions CI
├── README.md                # Human-readable project overview
├── CODEBASE_ASSESSMENT.md   # Detailed codebase audit (Feb 2026; some findings now stale)
│
│ ── src/ (CORE APPLICATION CODE) ──────────────────────────────
├── src/
│   ├── config.py            # CENTRAL CONFIG: all thresholds, weights, magic numbers
│   ├── config_loader.py     # Loads profiles.yaml + env overrides
│   ├── feature_flags.py     # Reads feature_flags.yaml; is_enabled() helper
│   ├── db.py                # SQLite schema, migrations, connection (PRAGMA foreign_keys=ON)
│   ├── datagolf.py          # Data Golf API client (rounds, predictions, field, odds)
│   ├── rolling_stats.py     # Compute rolling SG metrics from rounds → metrics table
│   ├── player_normalizer.py # Consistent player key + display name normalization
│   ├── csv_parser.py        # Legacy Betsperts CSV parser (still functional)
│   ├── logging_config.py    # Structured logging setup
│   │
│   ├── models/              # SUB-MODELS (6 files)
│   │   ├── composite.py     # Blends course_fit + form + momentum into single score
│   │   ├── course_fit.py    # Course-specific SG scoring + confidence scaling
│   │   ├── form.py          # Recent performance (rolling windows, DG skill, rankings)
│   │   ├── momentum.py      # Trend detection (window comparisons, elite stability)
│   │   ├── weather.py       # Weather forecast fetch + adjustments
│   │   └── weights.py       # Weight management, analysis, suggest_weight_adjustment
│   │
│   ├── value.py             # EV calculation, value bet detection (model vs market)
│   ├── matchup_value.py     # Matchup EV using Platt-sigmoid calibration + DG blend
│   ├── matchups.py          # Standalone matchup engine (compute_matchup_edge, confidence tiers)
│   ├── odds.py              # Odds fetch (The Odds API) + best odds per player/market
│   ├── odds_utils.py        # Odds conversion utilities (american_to_decimal, is_valid_odds)
│   ├── kelly.py             # Kelly criterion sizing (fractional Kelly, unit sizing)
│   ├── portfolio.py         # Diversification / exposure caps
│   ├── exposure.py          # Exposure tracking and limits
│   │
│   ├── card.py              # Betting card markdown generation
│   ├── methodology.py       # Methodology document generation
│   ├── output_manager.py    # output/ cleanup, archive older files
│   │
│   ├── ai_brain.py          # AI analysis: pre-tournament, post-review, adjustments
│   │                        #   Providers: OpenAI, Anthropic, Gemini
│   │                        #   make_betting_decisions() is DISABLED (returns None)
│   ├── prompts.py           # AI prompt templates (hardcoded string literals)
│   ├── confidence.py        # Model confidence from measurable factors
│   │
│   ├── learning.py          # Post-tournament: grade, calibrate, nudge weights, AI review
│   ├── adaptation.py        # Market adaptation state machine (normal/caution/cold/frozen)
│   ├── calibration.py       # Empirical probability calibration curve
│   ├── clv.py               # Closing Line Value tracking
│   ├── dynamic_blend.py     # Dynamic DG/model blend weights
│   ├── scoring.py           # Bet outcome determination (dead-heat handling)
│   ├── course_profile.py    # Course profiling (AI vision extraction or auto-generate)
│   ├── backup.py            # Database backup utilities
│   │
│   ├── services/
│   │   └── golf_model_service.py  # GolfModelService.run_analysis() — orchestration layer
│   │                               #   Used by run_predictions.py, app.py, analyze.py --service
│   └── routes/              # FastAPI route modules (split from app.py)
│       ├── __init__.py
│       ├── model_registry.py  # API routes for model registry
│       └── research.py        # API routes for research/autoresearch
│
│ ── backtester/ (WALK-FORWARD BACKTESTING + AUTORESEARCH) ─────
├── backtester/              # 15 files
│   ├── strategy.py          # Walk-forward strategy replay (StrategyConfig, simulate_strategy)
│   ├── pit_models.py        # Point-in-time sub-models (imports src.models + config)
│   ├── pit_stats.py         # PIT stats builder (no future data leakage)
│   ├── backfill.py          # Historical data backfill from DG
│   ├── experiments.py       # Experiment tracking & strategy promotion pipeline
│   ├── research_cycle.py    # Research cycle orchestration (proposals → backtest → dossier)
│   ├── proposals.py         # Proposal CRUD (create, approve, evaluate, update)
│   ├── model_registry.py    # Model registry / research champion management
│   ├── theory_engine.py     # Generate candidate theories for testing
│   ├── research_dossier.py  # Write research dossier from evaluation results
│   ├── weighted_walkforward.py  # Weighted walk-forward evaluation (recency-weighted)
│   ├── checkpoint_replay.py # Checkpoint-based strategy replay
│   ├── optimizer_runtime.py # Optimizer runtime utilities
│   ├── dashboard_runtime.py     # Live snapshot builder: _extract_rankings, _extract_matchups
│   │                            #   Feeds LiveRefreshSnapshot to frontend via API
│   ├── outlier_investigator.py  # Investigate prediction misses
│   └── autoresearch_config.py   # Autoresearch configuration
│
│ ── autoresearch/ (CONFIG FILES) ──────────────────────────────
├── autoresearch/
│   ├── cycle_config.json    # Research cycle configuration
│   └── strategy_config.json # Strategy parameter config
│
│ ── workers/ (BACKGROUND AGENTS) ──────────────────────────────
├── workers/
│   ├── research_agent.py    # 6-thread daemon: data collector, hypothesis generator,
│   │                        #   experiment runner, outlier analyst, optimizer, autoresearch loop
│   ├── live_refresh_worker.py  # Always-on daemon: fetches DG data, computes live/upcoming
│   │                           #   snapshots, serves via /api/live-refresh/snapshot
│   └── intel_harvester.py   # Scrapes external intelligence sources
│
│ ── scripts/ (UTILITIES, 9 files) ─────────────────────────────
├── scripts/
│   ├── grade_tournament.py
│   ├── backfill_matchup_odds.py
│   ├── backtest_v41_cognizant.py
│   ├── backtest_v42_cognizant.py
│   ├── generate_backtest_report.py
│   ├── compute_historical_clv.py
│   ├── run_autoresearch_eval.py
│   ├── run_autoresearch_loop.py
│   └── run_autoresearch_holdout.py
│
│ ── tests/ (PYTEST SUITE) ─────────────────────────────────────
├── tests/                   # 138 tests across 35 test files
│   ├── conftest.py          # Fixtures: tmp_db, sample_tournament, sample_metrics
│   ├── test_value.py
│   ├── test_form.py
│   ├── test_momentum.py
│   ├── test_calibration.py
│   ├── test_adaptation.py
│   ├── test_db.py
│   ├── test_matchup_value.py
│   ├── test_model_registry.py
│   ├── test_research_cycle.py
│   ├── test_research_proposals.py
│   ├── test_research_dossier.py
│   ├── test_research_api.py
│   ├── test_theory_engine.py
│   ├── test_weighted_walkforward.py
│   ├── test_checkpoint_replay.py
│   ├── test_checkpoint_asof_integrity.py
│   ├── test_optimizer_runtime.py
│   ├── test_optimizer_api.py
│   ├── test_strategy_replay_odds_fallback.py
│   ├── test_pit_temporal_leakage_guards.py
│   ├── test_simple_dashboard.py
│   ├── test_ai_brain_availability.py
│   ├── test_datagolf_throttle.py
│   ├── test_start_research.py
│   ├── test_pilot_contract_schema.py
│   ├── test_autoresearch_config_schema.py
│   ├── test_autoresearch_contract_enforcement.py
│   ├── test_autoresearch_eval_contract.py
│   ├── test_autoresearch_holdout_gate.py
│   ├── test_autoresearch_loop_decisions.py
│   ├── test_autoresearch_loop_reliability.py
│   ├── test_autoresearch_multitournament_mode.py
│   ├── test_autoresearch_promotion_policy.py
│   ├── test_autoresearch_rollback_policy.py
│   └── test_autoresearch_runtime_ops.py
│
│ ── frontend/ (REACT DASHBOARD SPA) ──────────────────────────
├── frontend/
│   ├── package.json          # Dependencies: React 19, Vite, TanStack Query/Table,
│   │                         #   echarts, framer-motion, lucide-react, shadcn/ui
│   ├── tsconfig.json         # TypeScript config
│   ├── vite.config.ts        # Vite config (proxies /api → FastAPI in dev)
│   ├── tailwind.config.ts    # Tailwind CSS config
│   ├── index.html            # Vite entry HTML
│   └── src/
│       ├── main.tsx          # React root mount
│       ├── App.tsx           # Main app: dashboard, players, matchups, track record pages
│       ├── lib/
│       │   ├── api.ts        # API client (fetch wrappers for /api/* endpoints)
│       │   ├── types.ts      # TypeScript types for all API responses and domain models
│       │   ├── utils.ts      # shadcn cn() utility
│       │   ├── format.ts     # Number/date formatting helpers
│       │   └── storage.ts    # useLocalStorageState hook
│       ├── components/
│       │   ├── shell.tsx     # App shell layout (sidebar, header, nav)
│       │   ├── charts.tsx    # Chart components (ECharts wrappers)
│       │   └── ui/           # shadcn/ui primitives (button, etc.)
│       └── data/
│           └── trackRecord.json  # Static fallback for track record (API is primary source)
│
│ ── DATA / OUTPUT / DOCS ──────────────────────────────────────
├── data/
│   ├── golf.db              # SQLite DB (gitignored; auto-created at runtime)
│   ├── courses/             # Course-specific profiles (5 JSON files)
│   │   ├── the_riviera_country_club.json
│   │   ├── pebble_beach_golf_links.json
│   │   ├── tpc_sawgrass_(the_players_stadium_course).json
│   │   ├── arnold_palmers_bay_hill_club_&_lodge.json
│   │   └── pga_national_resort_(the_champion_course).json
│   └── correlated_courses.json  # Course similarity mappings
│
├── output/
│   ├── {event}_{YYYYMMDD}.md              # Betting cards
│   ├── {event}_methodology_{YYYYMMDD}.md  # Methodology docs
│   ├── archive/             # Older cards moved here by output_manager
│   └── backtests/           # Backtest reports (.md and .json)
│
├── frontend/                # React 19 + Vite SPA (sole UI; built to frontend/dist/)
│
├── docs/
│   ├── AGENTS_KNOWLEDGE.md  # THIS FILE
│   ├── research/            # 10 research reports (market efficiency, calibration, ML, etc.)
│   ├── plans/               # 4 implementation plans
│   ├── autoresearch/        # pilot_contract.json, evaluation_contract.md
│   ├── sportsbook_strategy.md
│   ├── card_grading_report.md
│   └── card_grading_report_2026.md
│
└── .cursor/rules/
    ├── project-charter.mdc  # Stopping rules, bootstrap, go-live gates
    └── agents-knowledge.mdc # Always-apply rule pointing agents here
```

### Config Surface (Where Settings Live)

| Layer | File(s) | What it controls |
|-------|---------|------------------|
| Secrets/API | `.env` | API keys, `AI_BRAIN_PROVIDER`, `EV_THRESHOLD`, `MATCHUP_EV_THRESHOLD`, optional `PREFERRED_BOOK` metadata |
| Feature toggles | `feature_flags.yaml` | `kelly_sizing`, `clv_tracking`, `exposure_caps`, `dynamic_blend`, `dead_heat_adjustment`, `3ball`, `use_confirmed_field_only` |
| Run profiles | `profiles.yaml` | `tour`, `enable_ai`, `enable_backfill`, `backfill_years`, `output_dir` (profiles: default, quick, full) |
| Model tuning | `src/config.py` | EV thresholds, blend weights, adaptation states, matchup params, default weights, weather/confidence/integrity constants |

- **Model version:** Single source of truth is `src/config.MODEL_VERSION` (currently `"4.2"`). Do not duplicate elsewhere.
- **Adding new tuning:** Put it in `src/config.py`, not as a magic number in the consuming module.

---

## 3. Entry Points and How to Run

| Intent | Command | Notes |
|--------|---------|-------|
| Full prediction pipeline | `python run_predictions.py` | Primary entry. Auto-detects current DG event, runs full pipeline. Uses GolfModelService. |
| Web UI + API | `python app.py` | http://localhost:8000; API docs at /docs. Main tabs: predictions, autoresearch, grading. **Autoresearch UI:** `Simple Mode` is now the default operator path (one-button scalar edge tuner, report-only); `Lab Mode` contains the old advanced research controls. **Prediction default / full card:** 72-hole (tournament) matchups are the default card mode; **round** H2H is a separate mode (`round-matchups`) because books often do not list every DG pair. |
| First-time setup | `python setup_wizard.py` | Backfills data, initializes DB. Run once. |
| Unified launcher | `python start.py` | Interactive menu routing to pipeline, backtester, etc. |
| CLI analysis | `python analyze.py --tournament "Name" --course "Name" --sync` | Own pipeline by default. Add `--service` to use GolfModelService. `--ai` for AI. `--calibration` for dashboard. |
| Performance dashboard | `python dashboard.py` | View cumulative performance. `--retune` suggests new weights; `--dry` for preview. |
| Course profile extraction | `python course.py --screenshots data/course_images/ --course "Name"` | AI vision extraction from screenshots. Needs `ANTHROPIC_API_KEY`. |
| Results grading | `python results.py` | Score/grade tournament results. |
| Run tests | `pytest` or `python -m pytest` | 138 tests across 35 test files. Key fixtures in `tests/conftest.py`: `tmp_db`, `sample_tournament`, `sample_metrics`. |

### Pipeline Flow (High Level)

```
detect event → backfill rounds (if enabled)
→ sync DG (predictions, decompositions, field, skill_ratings, rankings, approach_skill)
→ compute rolling stats (8/12/16/24/all windows)
→ load course profile
→ composite model (course_fit + form + momentum; optional weather)
→ AI pre-tournament analysis (if enabled; adjustments applied to composite)
→ value detection (model vs market EV, blend DG/model; placement probs corrected by empirical calibration when bucket has 50+ samples) + matchup value (Platt-style)
→ portfolio diversification + exposure caps
→ generate card + methodology → write to output/
```

All orchestration goes through `src.services.golf_model_service.GolfModelService.run_analysis()` for consistency across `run_predictions.py`, `app.py`, and `analyze.py --service`.

### Live matchup diagnostics (operator decision tree)

When matchups appear empty, inspect `GET /api/live-refresh/snapshot` and read `snapshot.<live|upcoming>_tournament.diagnostics.state`:

- `no_market_posted_yet` → sportsbook rows are not posted yet (common early-week).
- `market_available_no_edges` → rows exist, but model/EV filters rejected all.
- `pipeline_error` → ingestion/model step failed; inspect `diagnostics.errors` and reason-code counters.
- `edges_available` → rows exist; empty UI is likely user-side filtering (`book/search/min-edge`) or source selection.

Use these fields to separate causes:
- `diagnostics.market_counts.tournament_matchups.raw_rows` (raw posted rows)
- `diagnostics.selection_counts.all_qualifying_rows` (rows that pass model/EV before card caps)
- `diagnostics.selection_counts.selected_rows` (card-curated rows after exposure/pair caps)
- `diagnostics.reason_codes` (where rows were excluded)

### Cockpit dashboard tabs (React SPA)

- **Live:** Leaderboard prefers Data Golf `preds/in-play` when available (`leaderboard_source: datagolf_in_play`); otherwise aggregates from `rounds`. Power rankings use point-in-time adjustment (`live_rankings`, `live_point_in_time_source` on `live_tournament`).
- **Upcoming:** Pre-tournament model from `upcoming_tournament`.
- **Completed:** `GET /api/live-refresh/past-snapshot?section=completed` merges `pre_teeoff_frozen` with the latest stored `live` leaderboard for that event.

---

## 4. Configuration Reference

### `.env` (secrets + overrides)

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `DATAGOLF_API_KEY` | Yes | — | Data Golf API (Scratch Plus subscription) |
| `OPENAI_API_KEY` | Recommended | — | AI brain default provider |
| `ANTHROPIC_API_KEY` | Optional | — | Alternative AI provider; also used by `course.py` for vision |
| `ODDS_API_KEY` | Optional | — | The Odds API for live market odds |
| `AI_BRAIN_PROVIDER` | No | `openai` | `openai`, `anthropic`, or `gemini` |
| `OPENAI_MODEL` | No | `gpt-4o` | Model override for OpenAI provider |
| `EV_THRESHOLD` | No | `0.08` | Override default EV threshold |
| `MATCHUP_EV_THRESHOLD` | No | `0.05` | Override matchup EV threshold |
| `AUTORESEARCH_GUARDRAIL_MODE` | No | *(empty)* | Env override for guardrail mode. Prefer setting **Guardrail mode** in the dashboard (Autoresearch tab); stored in `data/autoresearch_settings.json`. Set here to override UI for scripts. |
| `AUTORESEARCH_MAX_TRIAL_SECONDS` | No | `3600` | Wall-clock cap per walk-forward trial inside Optuna (thread timeout). Lower on laptops. |
| `AUTORESEARCH_GUARDRAIL_MIN_BETS` | No | `30` | Min bets required for a candidate to pass guardrails (ignored when `AUTORESEARCH_GUARDRAIL_MODE=loose`) |
| `AUTORESEARCH_GUARDRAIL_MAX_CLV_REGRESSION` | No | `0.02` | Max allowed CLV drop vs baseline (ignored when mode=loose) |
| `AUTORESEARCH_GUARDRAIL_MAX_CALIBRATION_REGRESSION` | No | `0.03` | Max allowed calibration error increase vs baseline (ignored when mode=loose) |
| `AUTORESEARCH_GUARDRAIL_MAX_DRAWDOWN_REGRESSION` | No | `10.0` | Max allowed drawdown increase vs baseline (ignored when mode=loose) |
| `PREFERRED_BOOK` | No | `bet365` | Optional preferred-book metadata shown alongside best-line pricing (no filtering) |
| `PREFERRED_BOOK_ONLY` | No | `false` | Deprecated legacy toggle (not used by current pipelines) |

### `feature_flags.yaml` (booleans, read by `src/feature_flags.py`)

All default to false if missing. Current flags: `dynamic_blend`, `exposure_caps`, `kelly_sizing`, `kelly_stakes`, `clv_tracking`, `dead_heat_adjustment`, `3ball`, `use_confirmed_field_only`.

### `profiles.yaml` (run profiles)

Three profiles: `default` (AI + backfill 2024–2026), `quick` (no AI, no backfill), `full` (AI + backfill 2020–2026). Keys: `tour`, `enable_ai`, `enable_backfill`, `backfill_years`, `output_dir`.

### `src/config.py` (model tuning — single source of truth)

Major sections and key values:
- **Value/EV:** `DEFAULT_EV_THRESHOLD` (0.08), `MARKET_EV_THRESHOLDS` (per market: outright 0.15, top5 0.10, top10 0.08, top20 0.08, frl 0.10, make_cut 0.05, 3ball 0.08), `MAX_TOTAL_VALUE_BETS` (5), `MAX_TOTAL_VALUE_BETS_WEAK_FIELD` (6), `MAX_CREDIBLE_EV` (2.0), `PHANTOM_EV_THRESHOLD` (1.0), `MIN_MARKET_PROB` (0.005), dead heat discounts, `MAX_REASONABLE_ODDS` (per market dict)
- **Best bets:** `BEST_BETS_MATCHUP_ONLY` (True), `BEST_BETS_COUNT` (5 — matchup plays shown in card header), `PLACEMENT_CARD_EV_FLOOR` (0.15 — only show placements with EV ≥15%), `PLACEMENT_CARD_MAX` (3 — max placement bets on card), `MAX_CREDIBLE_PLACEMENT_EV` (0.50)
- **Blend weights:** `BLEND_WEIGHTS` (currently 95% DG / 5% model for ALL markets — model is minor tiebreaker until calibrated)
- **Softmax temps:** `SOFTMAX_TEMP_BY_TYPE` (per market: outright 8.0, top5 10.0, top10 12.0, top20 15.0, make_cut 20.0, frl 7.0, 3ball 10.0)
- **Adaptation:** `ADAPTATION_MIN_BETS` (10), states triggered by ROI: normal (>-20%), caution (-20%), cold (-40%), frozen (10 consecutive losses), `ADAPTATION_STAKE_MULTIPLIER_COLD` (0.5)
- **Matchup:** `MATCHUP_PLATT_A` (-0.05), `MATCHUP_PLATT_B` (0.0), `MATCHUP_EV_THRESHOLD` (0.05), `MATCHUP_CAP` (20), `MATCHUP_MAX_PLAYER_EXPOSURE` (3), `MATCHUP_TOURNAMENT_MAX_PLAYER_EXPOSURE` (2 — tighter cap for 72-hole matchups), DG/model blend 80/20, `REQUIRE_DG_MODEL_AGREEMENT` (True), tier thresholds (STRONG ≥15% EV, GOOD ≥8%, else LEAN)
- **Default weights:** `DEFAULT_WEIGHTS` dict — course_fit 0.45, form 0.45, momentum 0.10; SG sub-weights: OTT 0.30, APP 0.28, TOT 0.22, PUTT 0.10; form windows: 16r 0.35, 12month 0.25, sim 0.25, rolling 0.15
- **Other:** `PUTT_SHRINKAGE_FACTOR` (0.5), `MOMENTUM_ENABLED` (True), `AI_ADJUSTMENT_CAP` (±3.0)
- **Weather:** `WIND_THRESHOLD_KMH` (15), `COLD_THRESHOLD_C` (10), max adjustments (wave 3, resilience 5)
- **Confidence:** factor weights (course_profile 0.20, dg_coverage 0.25, course_history 0.15, field_strength 0.10, odds_quality 0.15, model_market_alignment 0.15), weak-field multipliers (EV ×1.5, softmax temp ×1.2)
- **Data integrity:** `METRIC_FRESHNESS_HOURS` (48), `FIELD_SIZE_MIN` (50), `FIELD_SIZE_MAX` (170), `PROBABILITY_SUM_TOLERANCE` (0.05), `ALLOW_MID_TOURNAMENT_RUN` (False)
- **Autoresearch guardrails:** `get_autoresearch_guardrail_params()` in config. Guardrail mode is **configurable in the UI** (Autoresearch tab → "Guardrail mode" dropdown: Strict / Loose), persisted in `data/autoresearch_settings.json`. Env `AUTORESEARCH_GUARDRAIL_MODE` overrides UI when set. Strict: min_bets 30, max_clv_regression 0.02, max_calibration_regression 0.03, max_drawdown_regression 10.0. Loose: 15, 0.05, 0.06, 20.0. Used by `backtester/weighted_walkforward.evaluate_guardrails`. API: `GET/PATCH /api/autoresearch/settings`.
- **API:** `API_TIMEOUT` (120s), `API_RATE_LIMIT_SECONDS` (1.0), `PIPELINE_LOCK_STALE_SECONDS` (7200), `SUPPORTED_BOOKS` (draftkings, fanduel, betmgm, caesars, bet365, pointsbet, betrivers, fanatics)

---

## 5. Data Flow

### Step-by-step

1. **Event detection:** `datagolf.get_current_event_info()` → tournament name, event_id, course, course_key.
2. **Backfill:** `datagolf.fetch_historical_rounds()` → `rounds` table. Progress tracked in `backfill_progress`.
3. **DG sync:** `datagolf` fetches pre_tournament predictions, decompositions, field, skill_ratings, rankings, approach_skill → stored as `metrics`.
4. **Rolling stats:** `rolling_stats.compute_rolling_metrics()` reads `rounds`, computes SG averages for windows 8/12/16/24/all → `metrics`.
5. **Course profile:** `course_profile.load_course_profile()` from `data/courses/*.json` or AI vision extraction.
6. **Composite:** `models.composite.compute_composite()` calls `course_fit`, `form`, `momentum`; blends with weights from config or DB `weight_sets`; optional weather adjustments.
7. **AI pre-tournament:** `ai_brain.pre_tournament_analysis()` → narrative, key factors, player adjustments → `ai_decisions` table. Adjustments applied to composite scores (capped at `config.AI_ADJUSTMENT_CAP` = ±3).
8. **Value:** `value.find_value_bets()` converts composite → probabilities (softmax), blends with DG calibrated probs (95/5), applies empirical calibration correction when bucket has ≥50 samples (`calibration.get_calibration_correction`), computes EV vs market odds, filters by threshold. Value bet dicts include `calibration_applied`. `matchup_value.find_matchup_value_bets()` uses Platt-sigmoid + DG matchup blend (80/20), conviction scoring, and per-market exposure (tournament 2, round 3). Matchup predictions are logged to `prediction_log` for post-tournament scoring and Platt recalibration.
9. **Portfolio:** `portfolio.enforce_diversification()` + `exposure` caps.
10. **Output:** `card.generate_card()` → `output/{safe_name}_{YYYYMMDD}.md`. `methodology.generate_methodology()` → `output/{safe_name}_methodology_{YYYYMMDD}.md`. `output_manager.archive_previous()` moves older versions to `output/archive/`.

### Post-tournament (after event completes)

1. `learning.post_tournament_learn()` → score picks, update calibration curve, nudge weights, AI post-review.
2. `adaptation.get_adaptation_state()` → rolling ROI from `market_performance` → state: normal/caution/cold/frozen → adjusts EV thresholds + stake multipliers.
3. AI learnings stored in `ai_memory` table for retrieval in future tournaments.

### Database Tables (all defined in `src/db.py`)

**Core:** `tournaments`, `rounds`, `metrics`, `results`, `picks`, `pick_outcomes`, `runs`, `csv_imports`.

**AI:** `ai_memory`, `ai_decisions`, `ai_adjustments`, `ai_adjustment_log`.

**Learning / calibration:** `prediction_log`, `calibration_curve`, `weight_sets`, `market_performance`, `blend_history`, `matchup_calibration`, `bankroll`, `clv_log`.

**Course:** `course_weight_profiles`, `course_encyclopedia`, `course_strategies`.

**Hole-level:** `hole_scores`, `hole_difficulty`, `player_hole_history`.

**Backtester / PIT:** `pit_rolling_stats`, `pit_course_stats`, `historical_predictions`, `historical_odds`, `historical_matchup_odds`, `historical_event_info`, `tournament_weather`, `tournament_weather_summary`, `backfill_progress`.

**Experiments / research:** `experiments`, `active_strategy`, `research_proposals`, `proposal_reviews`, `research_model_registry`, `live_model_registry`, `outlier_investigations`.

**External data:** `equipment_changes`, `intel_events`.

**Live dashboard replay:** `pre_teeoff_candidates` (latest pre-teeoff upcoming section per event while still upcoming), `pre_teeoff_frozen` (immutable freeze when the event goes live), in addition to `live_snapshot_history` and `market_prediction_rows`.

**Meta:** `schema_version` (tracks schema version; constraint id=1).

Notes:
- `PRAGMA foreign_keys = ON` is set, but no FOREIGN KEY constraints are defined in CREATE TABLE statements. The pragma has no practical effect currently.
- Schema and migrations are inline in `db.py` (no Alembic or separate migration tool).
- Minor naming inconsistencies exist (e.g., `dg_id` vs `player_dg_id` in different tables).

---

## 6. Key Conventions and Tech Debt

### Conventions (Follow These)

- **Centralized config:** All tunable numbers go in `src/config.py` or env. Never add new magic numbers in consuming modules (value.py, adaptation.py, etc.).
- **Model version:** Use `config.MODEL_VERSION` only. Do not duplicate in card.py, methodology.py, or elsewhere.
- **Walk-forward only:** Backtests must use only data available before each event. PIT stats enforce this.
- **Blend weights (95/5):** Model softmax is uncalibrated; DG probabilities dominate. Model is a minor tiebreaker until calibrated. Do not change ratio without calibration evidence.
- **Max 5 value bets per card:** Quality over quantity. Configurable via `config.MAX_TOTAL_VALUE_BETS`.
- **Matchup-first card:** Top plays are always matchups (up to `BEST_BETS_COUNT`); placements only appear when EV ≥ `PLACEMENT_CARD_EV_FLOOR`. Speculative outrights are not shown on the card. Matchups first (`config.BEST_BETS_MATCHUP_ONLY = True`).
- **Player normalization:** Always use `player_normalizer.normalize_name()` for keys and `display_name()` for output.
- **Test fixtures:** Use `tmp_db` fixture for any test writing to DB. Defined in `tests/conftest.py`.
- **Output naming:** Card: `{safe_name}_{YYYYMMDD}.md`. Methodology: `{safe_name}_methodology_{YYYYMMDD}.md`. `safe_name` = tournament name lowercased, spaces→underscores, apostrophes removed.

### Known Tech Debt (Do Not Assume Broken — These Are Intentional or In Progress)

- **AI betting decisions disabled:** `ai_brain.make_betting_decisions()` intentionally returns None. Disabled due to poor performance (concentrated 87% of units on one player, recommended bets on corrupted odds). AI provides pre-tournament adjustments only.
- **MAX_REASONABLE_ODDS duplicated:** Defined as a market-specific dict in `config.py`, but `odds.py` and `odds_utils.py` also define a global fallback (`50000`). The consuming modules do read from `config`, but the fallback constant creates ambiguity. Centralizing fully is desired.
- **Large app.py:** 2916 lines. Splitting into `src/routes/` is partially done (model_registry, research routes) but app.py still holds most routes/logic. Long-term goal to split further.
- **No FK constraints in DB:** `PRAGMA foreign_keys = ON` is set but tables don't define FOREIGN KEY clauses. Adding FK constraints is a future improvement.
- **No full pipeline integration test:** Unit tests exist; no end-to-end pipeline test. Add one if touching pipeline flow.
- **Prompts are hardcoded strings:** `src/prompts.py` is all string literals. Moving to external files or DB is desired.
- **CODEBASE_ASSESSMENT.md is partially stale:** Written Feb 2026. Some findings (like `_suggest_matchups` deprecated, `_american_to_implied_prob` duplicated) have been fixed since. Use this AGENTS_KNOWLEDGE.md as the authoritative reference.

---

## 7. User / Operator Expectations (For Agent Behavior)

- **Changes as PR:** User wants all changes pushed as a branch + PR for iteration, not only saved locally. Workflow: branch → implement → push → open PR.
- **No breakage:** Every addition or change must improve the project and not break existing behavior. Test and reason through changes; ensure the pipeline, UI, and backtester continue to work.
- **Realistic feedback:** Do not affirm every idea. If a request is unrealistic, not technically sound, or not aligned with product/codebase, say so clearly.
- **Explain simply:** User assumes minimal experience. Explain steps and decisions in plain terms, as if talking to a beginner.
- **No guessing:** If you don't know the answer, say so rather than making something up.

### Anti-Hallucination Rules (CRITICAL)

- **NEVER fabricate IP addresses, hostnames, passwords, API keys, or deployment details.** If a value is not explicitly stored in this document, `.env`, or a config file in the repo, say "I don't have that value on file" and ask the user. The production server IP is `204.168.147.6` — use only this, do not invent alternatives.
- **NEVER fabricate file paths, function names, or API endpoints.** Verify they exist before referencing them. Use `Grep` or `Read` to confirm.
- **NEVER guess at data values** (e.g., field sizes, player names, tournament dates). If unsure, check the Data Golf API response or database.
- **When providing deploy/server commands,** always reference the values in Section 11 of this document. Do not reconstruct them from memory or prior conversations.

---

## 8. Project Charter (Deployment and Strategy)

**Source:** `.cursor/rules/project-charter.mdc`. Refer for every deployment decision.

### Stopping Rules (SPRT-inspired)

1. CLV < 0% after 150 bets → full investigation (review calibration, blend weight, data quality).
2. CLV < 0% AND negative ROI after 300 bets → stop live betting until root cause fixed and re-validated via paper trade.

### 4-Phase Bootstrap

| Phase | Events | Kelly Fraction | Gate to Next |
|-------|--------|---------------|--------------|
| Shadow | 1–5 | 0 (predict only) | Brier < 0.25, no systematic calibration bias |
| Paper | 6–15 | 0 (paper trade) | CLV > 0% over 100+ bets, no segment regressions |
| Cautious Live | 16–25 | 1/8 Kelly | CLV > 1% over 250+ bets, hit rate > 55%, max drawdown < 15% |
| Full Live | 26+ | 1/4 Kelly | All go-live hard gates below |

### Go-Live Hard Gates (All Required for Full Live)

- 250+ tracked bets
- Average CLV > 1%
- CLV hit rate > 55%
- Brier < 0.22 for matchups
- No segment with Brier > 0.28
- Max paper drawdown < 20%

### Shadow Mode

Run pipeline in parallel with alternate config/blend; compare cards and Brier/CLV before promoting changes to production.

---

## 9. Autoresearch System

**Default behavior:** **`AUTORESEARCH_AUTO_APPLY` is off.** Research cycle **does not** auto-call `set_research_champion` / `approve_proposal` unless that env var is set to `1`. Do **not** suggest auto-applying Optuna or walk-forward winners to live or registry without explicit operator approval; point to [`docs/research/EDGE_TUNER_REPORT.md`](../research/EDGE_TUNER_REPORT.md) and manual merge into `autoresearch/strategy_config.json`.

**Dashboard default workflow:** The recommended UI path is the **Simple Mode** edge tuner exposed via `/api/simple/autoresearch/start|status|stop|run-once`. It always runs **Optuna scalar**, uses **`weighted_roi_pct`** as the primary objective, keeps **report-only** behavior, and uses the scalar study base name **`golf_scalar_simple`**. **Lab Mode** still exposes the lower-level `engine_mode`, Pareto/study views, theory toggle, and reset controls.

**Persisted defaults:** `src/autoresearch_settings.DEFAULT_SETTINGS` now boots the advanced settings layer to `engine_mode="optuna_scalar"`, `scalar_objective="weighted_roi_pct"`, `optuna_scalar_study_name="golf_scalar_simple"`, and `optuna_trials_per_cycle=3`.

**Reset behavior:** `POST /api/autoresearch/reset` is now an **archive-first** reset. It exports old `research_proposals`, `proposal_reviews`, and `research_model_registry` rows plus active `output/research/` artifacts and `data/autoresearch_settings.json` into `output/research/archive/<timestamp>/`, then clears the active research lane and resets optimizer runtime state. `live_model_registry` and the live prediction lane stay active. If predictions were currently resolving from the research champion and there is no live row yet, reset snapshots that strategy into the live lane first so prediction behavior stays unchanged.

**Predictions / `GolfModelService`:** `include_methodology` defaults to **true** — each run should emit a `*_methodology_*.md` next to the card unless the caller passes `include_methodology=False` (e.g. fast tests).

**Target v2 design (full spec):** [`docs/autoresearch/SPEC_V2.md`](autoresearch/SPEC_V2.md) — canonical evaluator, Optuna (MO + scalar), append-only **`output/research/ledger.jsonl`**, human program [`docs/research/research_program.md`](../research/research_program.md), [`docs/research/KARPATHY_AGENT_RUNBOOK.md`](../research/KARPATHY_AGENT_RUNBOOK.md) for LLM-driven workflows.

### Single strategy resolution (production)

All prediction entry points use **`src/strategy_resolution.resolve_runtime_strategy(scope)`**: **live weekly model → research champion → active_strategy (experiments) → default** `StrategyConfig`. **`build_pipeline_strategy_config(strategy)`** maps `w_sub_*` weights and EV/markets for `GolfModelService` (aligned with `run_predictions.py` and PIT replay).

- **CLI:** `run_predictions.py` imports resolution from `src/strategy_resolution.py`.
- **Web:** `/api/simple/upcoming-prediction` resolves once, passes `strategy_source="config"` with the built pipeline dict (no double-resolve).
- **GolfModelService:** Default `strategy_source` is **`registry`** so `/api/run-service` matches CLI unless callers pass `strategy_source="config"` with an explicit pipeline dict.

### Two evaluation modes (do not confuse)

| Mode | Entry | What it measures |
|------|--------|------------------|
| **Primary (dashboard/API)** | `backtester/autoresearch_engine.run_cycle` → `run_research_cycle` | Weighted walk-forward over `load_historical_events`, `replay_event`, proposals in DB. Returns `evaluation_mode`, `data_health`, `guardrail_mode`. |
| **Holdout / contract (CLI)** | `scripts/run_autoresearch_eval.py`, `run_autoresearch_loop.py`, `run_autoresearch_holdout.py` | Immutable checkpoint replay + `docs/autoresearch/pilot_contract.json`. Does **not** update `research_proposals` unless wired separately. |

Operator checklist: **`docs/autoresearch/RUNBOOK.md`**.

### Components

- **Theory engine** (`backtester/theory_engine.py`): OpenAI theories with dedup; fallback **directed** `w_sub_*` tilts + **neighbor** search (`fallback_directed`, `fallback_neighbor`).
- **Proposals** (`backtester/proposals.py`): CRUD for strategy proposals. DB: `research_proposals`, `proposal_reviews`.
- **Experiments** (`backtester/experiments.py`): `experiments` table, `active_strategy`, `promote_strategy` (separate lane from research champion).
- **Canonical evaluation (v2 prep)** (`backtester/research_lab/canonical.py`): `evaluate_walk_forward_benchmark`, `evaluate_checkpoint_pilot`, `EvaluationResult` (objective vector, `feasible`, `to_dict`); used by `run_research_cycle` (`canonical_evaluation` on each candidate) and `scripts/run_autoresearch_eval.py`.
- **Optuna studies** (`backtester/research_lab/mo_study.py`, `param_space.py`): **MO** (Pareto) and **scalar** (single objective: `blended_score` or `weighted_roi_pct`); storage `output/research/optuna/studies.db`. Trial rows append to **`output/research/ledger.jsonl`**. CLI MO: `python scripts/run_autoresearch_optuna.py --n-trials 10`; CLI scalar: `... --scalar --scalar-metric blended_score`. Engine modes: `research_cycle` | `optuna` | `optuna_scalar` (`data/autoresearch_settings.json`).
- **Research cycle** (`backtester/research_cycle.py`): Orchestrates proposal → `evaluate_weighted_walkforward` → dossier; includes **`validate_autoresearch_data_health`** preflight in the returned payload.
- **Data health** (`backtester/autoresearch_data_health.py`): Event/PIT/odds row counts and warnings before trusting metrics.
- **Weighted walk-forward** (`backtester/weighted_walkforward.py`): `evaluate_guardrails` uses `get_autoresearch_guardrail_params()` (UI `data/autoresearch_settings.json` or env).
- **Model registry** (`backtester/model_registry.py`): `research_model_registry`, `live_model_registry`; promote research → live via API gates.
- **Research dossier** (`backtester/research_dossier.py`): Markdown artifacts under `output/research/`.
- **Config files:** `autoresearch/cycle_config.json`, `autoresearch/strategy_config.json`
- **Contracts:** `docs/autoresearch/pilot_contract.json`, `docs/autoresearch/evaluation_contract.md`
- **Workers:** `workers/research_agent.py` — autoresearch loop calls `autoresearch_engine.run_cycle`.
- **Dashboard:** Autoresearch tab; **since engine start** snapshot in optimizer runtime state when the daemon starts.

---

## 10. Output Artifacts

- **Cards:** `output/{safe_name}_{YYYYMMDD}.md` — rankings, value bets, matchup bets, AI summary.
- **Methodology:** `output/{safe_name}_methodology_{YYYYMMDD}.md` — model version, weights, data sources, detailed explanation.
- **Archive:** `output_manager.archive_previous()` moves older versions to `output/archive/`.
- **Backtest reports:** `output/backtests/*.md` (and `.json`).
- **Card grading:** `docs/card_grading_report.md`, `docs/card_grading_report_2026.md`.

---

## 11. Deployment Infrastructure

### Production Server

- **Host:** `root@204.168.147.6` (VPS)
- **Remote path:** `/opt/golf-model`
- **Branch:** `main`
- **Deploy command:** `DEPLOY_HOST=root@204.168.147.6 ./deploy.sh --update`
- **First-time setup:** `DEPLOY_HOST=root@204.168.147.6 ./deploy.sh --setup`
- **Status check:** `DEPLOY_HOST=root@204.168.147.6 ./deploy.sh --status`

### What `--update` does

1. Backs up the database
2. `git pull origin main`
3. `pip install -r requirements.txt`
4. `cd frontend && npm ci && npm run build`
5. Runs DB migrations (`init_db()`)
6. `systemctl restart golf-dashboard golf-agent golf-live-refresh`

### Systemd Services

| Service | What it runs | Port |
|---------|-------------|------|
| `golf-dashboard` | `start.py dashboard --port 8000` | 8000 |
| `golf-agent` | `start.py agent` | — |
| `golf-live-refresh` | `workers/live_refresh_worker.py` | — |
| `golf-backup.timer` | Nightly DB backup at 03:00 UTC | — |

Useful commands on the server:
```
systemctl status golf-dashboard
journalctl -u golf-live-refresh -f
systemctl restart golf-live-refresh
```

#### Live Refresh Ownership (single-owner rule)

- The systemd unit `golf-live-refresh` (running `workers/live_refresh_worker.py`) is the **sole authoritative owner** of the live refresh loop in production. Do not start a second loop in-process.
- The FastAPI dashboard (`app.py`) will **not** start an embedded live-refresh loop by default. Embedded autostart is opt-in via `LIVE_REFRESH_EMBEDDED_AUTOSTART=1` (useful only for local/dev environments where the worker is not running). When opt-in is enabled, the dashboard emits a LOUD `WARNING` log on startup.
- **Pidfile coordination:** the worker writes its PID to `/tmp/golf_live_refresh.pid` (override via env var `LIVE_REFRESH_PIDFILE`) and removes it on clean shutdown. If `LIVE_REFRESH_EMBEDDED_AUTOSTART=1` is set but the pidfile points to a live process, the dashboard lifespan hook refuses to start a second loop and logs a WARNING.
- `deploy.sh` sets `LIVE_REFRESH_EMBEDDED_AUTOSTART=0` on `golf-dashboard.service` as defense-in-depth; the repo default is now also `0`.

### Frontend Build

The React frontend builds to `frontend/dist/` and is served by FastAPI at `/`. On deploy, `npm ci && npm run build` runs automatically. For local development:
```
cd frontend && npm run dev   # Vite dev server with API proxy to :8000
```

---

## 12. Quick Reference: Where to Change What

| Change | Primary file(s) |
|--------|------------------|
| EV thresholds, blend weights, adaptation thresholds | `src/config.py` |
| Feature toggles (Kelly, CLV, exposure, 3ball) | `feature_flags.yaml` |
| Run profile (AI on/off, backfill years) | `profiles.yaml` |
| API keys, provider, preferred-book metadata | `.env` |
| Model weights (course_fit/form/momentum, SG sub-weights) | `src/config.py` `DEFAULT_WEIGHTS`; or DB `weight_sets` |
| Card layout or content | `src/card.py` |
| Methodology doc content | `src/methodology.py` |
| Composite model logic | `src/models/composite.py` + `course_fit.py`, `form.py`, `momentum.py` |
| Value detection logic | `src/value.py` |
| Matchup value logic | `src/matchup_value.py` |
| Matchup edge computation | `src/matchups.py` |
| Kelly sizing logic | `src/kelly.py` |
| AI prompts | `src/prompts.py` |
| AI analysis logic | `src/ai_brain.py` |
| DB schema/migrations | `src/db.py` |
| Pipeline orchestration | `src/services/golf_model_service.py` |
| Web API routes (most) | `app.py` |
| Web API routes (registry, research) | `src/routes/model_registry.py`, `src/routes/research.py` |
| Frontend dashboard (React SPA) | `frontend/src/App.tsx` |
| Frontend API client / types | `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts` |
| Frontend UI components | `frontend/src/components/` |
| Frontend build config | `frontend/vite.config.ts`, `frontend/tailwind.config.ts` |
| Backtest strategy replay | `backtester/strategy.py`, `backtester/pit_models.py` |
| Experiment tracking / promotion | `backtester/experiments.py` |
| Research cycle / proposals | `backtester/research_cycle.py`, `backtester/proposals.py` |
| Autoresearch config | `autoresearch/cycle_config.json`, `autoresearch/strategy_config.json` |
| Strategy resolution (CLI/web parity) | `src/strategy_resolution.py` |
| Autoresearch facade + health | `backtester/autoresearch_engine.py`, `backtester/autoresearch_data_health.py` |
| Operator runbook | `docs/autoresearch/RUNBOOK.md` |
| Course profiles | `data/courses/*.json`; extraction via `course.py` or `src/course_profile.py` |
| Rolling stats computation | `src/rolling_stats.py` |
| CI | `.github/workflows/ci.yml` |
| Deployment | `deploy.sh` (see Section 11) |
| Live refresh snapshot logic | `backtester/dashboard_runtime.py`, `workers/live_refresh_worker.py` |
| Frontend (sole UI) | `frontend/` (React 19 + Vite), built to `frontend/dist/` |

---

## 13. Updating This Document

- **When to update:** Adding entry points, config keys, DB tables, critical modules, new conventions, or deprecating behavior.
- **Section 2 (layout):** Keep the tree accurate. Every `.py` file should be listed.
- **Section 4 (config):** Add new env vars, feature flags, or config.py values with their defaults.
- **Section 5 (DB tables):** Add new tables when they're created in `db.py`.
- **Section 6 (conventions/debt):** Document new conventions under "Conventions"; new intentional oddities under "Tech Debt". Remove entries when debt is resolved.
- **Section 11 (deployment):** Keep server IP, deploy commands, and service names current.
- **Section 12 (quick reference):** Keep aligned with actual file locations.
- **Charter changes:** Update section 8 and keep `.cursor/rules/project-charter.mdc` in sync.
- **Last verified line (top):** Update date, model version, test count, and app.py line count when you verify accuracy.
