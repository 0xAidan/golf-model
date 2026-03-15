# Golf Model — Agent Knowledge Base

**Purpose:** Single reference for AI agents working in this repo. Attach this doc to new chats so agents can execute tasks without scanning the codebase. Update this file when structure, conventions, or critical paths change.

**Audience:** AI agents (LLM instances). Optimized for programmatic parsing and minimal ambiguity; not optimized for human narrative.

**Last verified:** 2026-03-15. Test count: 138. Model version: 4.2.

---

## 1. Project Summary

- **What it is:** Quantitative golf betting system. Data Golf API → round-level SG data, predictions, odds. Composite model (course fit + form + momentum) scores players; value layer compares model vs market for EV; AI layer does qualitative analysis and persistent memory. Post-tournament: grade picks, calibration, weight nudges, AI learnings. Autoresearch system proposes, backtests, and promotes strategy changes autonomously.
- **Stack:** Python 3.11+, SQLite (`data/golf.db`), FastAPI for web UI. No frontend framework — templates + vanilla JS + CSS (`templates/index.html`, `static/css/main.css`).
- **Key constraints:** Walk-forward backtesting only (no future data). Bootstrap phases (shadow → paper → cautious live → full live). Stopping rules and go-live gates in project charter. See section 8.
- **CI:** GitHub Actions at `.github/workflows/ci.yml`.

---

## 2. Repository Layout (Critical Paths)

```
golf-model/
├── run_predictions.py       # CLI: full prediction pipeline (primary entry point)
├── app.py                   # FastAPI web UI + API (dashboard at :8000, API docs at /docs)
├── start.py                 # Unified launcher (interactive menu + subcommands)
├── setup_wizard.py          # First-time setup: backfill data, init DB
├── analyze.py               # Lightweight CLI (delegates to GolfModelService)
├── results.py               # Results entry / grading CLI
├── dashboard.py             # Performance summary + weight retune CLI (--retune, --dry)
├── course.py                # Course profile extraction from screenshots CLI
├── .env                     # API keys (from .env.example); NEVER commit
├── .env.example             # Template for required keys
├── feature_flags.yaml       # Toggles: kelly_sizing, clv_tracking, exposure_caps, etc.
├── profiles.yaml            # Run profiles: default, quick, full
├── pyproject.toml           # Project metadata
├── requirements.txt         # Python dependencies (pinned)
├── .pre-commit-config.yaml  # Pre-commit hooks
├── .github/workflows/ci.yml # GitHub Actions CI
│
├── src/                     # CORE APPLICATION CODE
│   ├── config.py            # CENTRAL CONFIG: all thresholds, weights, magic numbers
│   ├── config_loader.py     # Loads profiles.yaml + env overrides
│   ├── feature_flags.py     # Reads feature_flags.yaml; is_enabled() helper
│   ├── db.py                # SQLite schema, migrations, connection management
│   ├── datagolf.py          # Data Golf API client (rounds, predictions, field, odds)
│   ├── rolling_stats.py     # Compute rolling SG metrics from rounds → metrics table
│   ├── player_normalizer.py # Consistent player key + display name normalization
│   ├── csv_parser.py        # Legacy Betsperts CSV parser
│   ├── logging_config.py    # Structured logging setup
│   │
│   ├── models/              # SUB-MODELS
│   │   ├── composite.py     # Blends course_fit + form + momentum into single score
│   │   ├── course_fit.py    # Course-specific SG scoring + confidence scaling
│   │   ├── form.py          # Recent performance (rolling windows, DG skill, rankings)
│   │   ├── momentum.py      # Trend detection (window comparisons, elite stability)
│   │   ├── weather.py       # Weather forecast fetch + adjustments
│   │   └── weights.py       # Weight management, analysis, suggest_weight_adjustment
│   │
│   ├── value.py             # EV calculation, value bet detection (model vs market)
│   ├── matchup_value.py     # Matchup EV (Platt-sigmoid calibrated)
│   ├── matchups.py          # Model-only matchup engine (has deprecated _suggest_matchups)
│   ├── odds.py              # Odds fetch (The Odds API) + best odds per player/market
│   ├── odds_utils.py        # Odds conversion utilities (american_to_decimal, etc.)
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
│   │                               #   Used by ALL entry points (CLI, FastAPI, backtester)
│   └── routes/
│       ├── __init__.py
│       ├── model_registry.py  # FastAPI routes for model registry
│       └── research.py        # FastAPI routes for research/autoresearch
│
├── backtester/              # WALK-FORWARD BACKTESTING + AUTORESEARCH
│   ├── strategy.py          # Strategy replay (historical events with PIT stats)
│   ├── pit_models.py        # Point-in-time sub-models (imports src.models + config)
│   ├── pit_stats.py         # PIT stats builder (no future data leakage)
│   ├── backfill.py          # Historical data backfill from DG
│   ├── research_cycle.py    # Research cycle orchestration (proposals, dossier, theory)
│   ├── proposals.py         # Proposal CRUD (create, approve, evaluate)
│   ├── model_registry.py    # Model registry / research champion management
│   ├── theory_engine.py     # Generate candidate theories for testing
│   ├── research_dossier.py  # Write research dossier from evaluation results
│   ├── weighted_walkforward.py  # Weighted walk-forward evaluation (recency-weighted)
│   ├── checkpoint_replay.py # Checkpoint-based strategy replay
│   ├── optimizer_runtime.py # Optimizer runtime utilities
│   ├── outlier_investigator.py  # Investigate prediction misses
│   └── autoresearch_config.py   # Autoresearch configuration
│
├── autoresearch/            # Autoresearch config files
│   ├── cycle_config.json    # Research cycle configuration
│   └── strategy_config.json # Strategy parameter config
│
├── workers/                 # BACKGROUND AGENTS
│   ├── research_agent.py    # 5-thread daemon for continuous research improvement
│   └── intel_harvester.py   # Scrapes external intelligence sources
│
├── scripts/                 # UTILITIES
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
├── tests/                   # PYTEST SUITE (138 tests)
│   ├── conftest.py          # Fixtures: tmp_db, sample_tournament, sample_metrics
│   └── test_*.py            # ~30 test files
│
├── data/                    # DATA
│   ├── golf.db              # SQLite database (auto-created by setup_wizard)
│   ├── courses/*.json       # Course-specific profiles
│   └── correlated_courses.json  # Course similarity mappings
│
├── output/                  # GENERATED OUTPUT
│   ├── {event}_{YYYYMMDD}.md          # Betting cards
│   ├── {event}_methodology_{YYYYMMDD}.md  # Methodology docs
│   ├── archive/             # Older cards moved here by output_manager
│   └── backtests/           # Backtest reports (.md and .json)
│
├── templates/index.html     # Web UI template
├── static/css/main.css      # Web UI styles
│
├── docs/                    # DOCUMENTATION
│   ├── AGENTS_KNOWLEDGE.md  # THIS FILE
│   ├── research/            # Research reports (ML systems, calibration, market efficiency, etc.)
│   ├── plans/               # Implementation plans
│   ├── autoresearch/        # Autoresearch contracts and evaluation docs
│   └── sportsbook_strategy.md  # Sportsbook-specific strategy notes
│
└── .cursor/rules/
    ├── project-charter.mdc  # Stopping rules, bootstrap, go-live gates
    └── agents-knowledge.mdc # Always-apply rule pointing agents here
```

### Config Surface (Where Settings Live)

| Layer | File(s) | What it controls |
|-------|---------|------------------|
| Secrets/API | `.env` | API keys, `AI_BRAIN_PROVIDER`, `EV_THRESHOLD`, `MATCHUP_EV_THRESHOLD`, `PREFERRED_BOOK` |
| Feature toggles | `feature_flags.yaml` | `kelly_sizing`, `clv_tracking`, `exposure_caps`, `dynamic_blend`, `dead_heat_adjustment`, `3ball`, `use_confirmed_field_only` |
| Run profiles | `profiles.yaml` | `tour`, `enable_ai`, `enable_backfill`, `backfill_years`, `output_dir` (profiles: default, quick, full) |
| Model tuning | `src/config.py` | EV thresholds, blend weights, adaptation states, matchup params, default weights, weather/confidence/integrity constants |

- **Model version:** Single source of truth is `src/config.MODEL_VERSION` (currently `"4.2"`). Do not duplicate elsewhere.
- **Adding new tuning:** Put it in `src/config.py`, not as a magic number in the consuming module.

---

## 3. Entry Points and How to Run

| Intent | Command | Notes |
|--------|---------|-------|
| Full prediction pipeline | `python run_predictions.py` | Main path. Detects current event, runs full pipeline. |
| Web UI + API | `python app.py` | http://localhost:8000; API docs at /docs. 8 tabs: predictions, cards, grading, registry, autoresearch, calibration. |
| First-time setup | `python setup_wizard.py` | Backfills data, initializes DB. Run once. |
| Unified launcher | `python start.py` | Interactive menu routing to pipeline, backtester, etc. |
| Lightweight analysis | `python analyze.py` | Delegates to GolfModelService; supports CSV folder, manual odds, AI, backfill. |
| Performance dashboard | `python dashboard.py` | View cumulative performance. `--retune` suggests new weights; `--dry` for preview. |
| Course profile extraction | `python course.py --screenshots data/course_images/ --course "Name"` | AI vision extraction from screenshots. |
| Results grading | `python results.py` | Score/grade tournament results. |
| Run tests | `pytest` or `python -m pytest` | 138 tests. Key fixtures in `tests/conftest.py`: `tmp_db`, `sample_tournament`, `sample_metrics`. |

### Pipeline Flow (High Level)

```
detect event → backfill rounds (if enabled)
→ sync DG (predictions, decompositions, field, skill_ratings, rankings, approach_skill)
→ compute rolling stats (8/12/16/24/all windows)
→ load course profile
→ composite model (course_fit + form + momentum; optional weather)
→ AI pre-tournament analysis (if enabled; adjustments applied to composite)
→ value detection (model vs market EV, blend DG/model) + matchup value (Platt-style)
→ portfolio diversification + exposure caps
→ generate card + methodology → write to output/
```

All orchestration goes through `src.services.golf_model_service.GolfModelService.run_analysis()` for consistency across CLI, web, and backtester.

---

## 4. Configuration Reference

### `.env` (secrets + overrides)

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `DATAGOLF_API_KEY` | Yes | — | Data Golf API (Scratch Plus subscription) |
| `OPENAI_API_KEY` | Recommended | — | AI brain default provider |
| `ANTHROPIC_API_KEY` | Optional | — | Alternative AI provider |
| `ODDS_API_KEY` | Optional | — | The Odds API for live market odds |
| `AI_BRAIN_PROVIDER` | No | `openai` | `openai`, `anthropic`, or `gemini` |
| `OPENAI_MODEL` | No | `gpt-4o` | Model override for OpenAI provider |
| `EV_THRESHOLD` | No | `0.08` | Override default EV threshold |
| `MATCHUP_EV_THRESHOLD` | No | `0.05` | Override matchup EV threshold |
| `PREFERRED_BOOK` | No | `bet365` | Target sportsbook for live card |
| `PREFERRED_BOOK_ONLY` | No | `true` | Only show plays at preferred book |

### `feature_flags.yaml` (booleans, read by `src/feature_flags.py`)

All default to false if missing. Current flags: `dynamic_blend`, `exposure_caps`, `kelly_sizing`, `kelly_stakes`, `clv_tracking`, `dead_heat_adjustment`, `3ball`, `use_confirmed_field_only`.

### `profiles.yaml` (run profiles)

Three profiles: `default` (AI + backfill 2024-2026), `quick` (no AI, no backfill), `full` (AI + backfill 2020-2026). Keys: `tour`, `enable_ai`, `enable_backfill`, `backfill_years`, `output_dir`.

### `src/config.py` (model tuning — single source of truth)

Major sections:
- **Value/EV:** `DEFAULT_EV_THRESHOLD`, `MARKET_EV_THRESHOLDS` (per market type), `MAX_TOTAL_VALUE_BETS` (5), `MAX_CREDIBLE_EV`, `PHANTOM_EV_THRESHOLD`, `MIN_MARKET_PROB`, dead heat discounts, `MAX_REASONABLE_ODDS` (per market)
- **Blend weights:** `BLEND_WEIGHTS` (currently 95% DG / 5% model for all markets — model is minor tiebreaker until calibrated)
- **Softmax temps:** `SOFTMAX_TEMP_BY_TYPE` (per market)
- **Adaptation:** thresholds for normal/caution/cold/frozen states, ROI triggers, stake multipliers
- **Matchup:** Platt A/B, sigmoid divisor, `MATCHUP_EV_THRESHOLD`, `MATCHUP_CAP` (20), `MATCHUP_MAX_PLAYER_EXPOSURE` (3), tier thresholds, DG/model blend (80/20), `REQUIRE_DG_MODEL_AGREEMENT`
- **Default weights:** `DEFAULT_WEIGHTS` dict — course_fit 0.45, form 0.45, momentum 0.10; SG sub-weights (OTT 0.30, APP 0.28, TOT 0.22, PUTT 0.10)
- **Weather:** wind/cold thresholds, adjustment caps
- **Confidence:** factor weights, field strength tiers, weak-field multipliers
- **Data integrity:** `METRIC_FRESHNESS_HOURS`, `FIELD_SIZE_MIN/MAX`, `PROBABILITY_SUM_TOLERANCE`, `ALLOW_MID_TOURNAMENT_RUN` (False)
- **API:** timeout, rate limit, pipeline lock staleness, supported sportsbooks

---

## 5. Data Flow

### Step-by-step

1. **Event detection:** `datagolf.get_current_event_info()` → tournament name, event_id, course, course_key.
2. **Backfill:** `datagolf.fetch_historical_rounds()` → `rounds` table. Progress tracked in `backfill_progress`.
3. **DG sync:** `datagolf` fetches pre_tournament predictions, decompositions, field, skill_ratings, rankings, approach_skill → stored as `metrics`.
4. **Rolling stats:** `rolling_stats.compute_rolling_metrics()` reads `rounds`, computes SG averages for windows 8/12/16/24/all → `metrics`.
5. **Course profile:** `course_profile.load_course_profile()` from `data/courses/*.json` or AI vision extraction.
6. **Composite:** `models.composite.compute_composite()` calls `course_fit`, `form`, `momentum`; blends with weights from config or DB `weight_sets`; optional weather adjustments.
7. **AI pre-tournament:** `ai_brain.pre_tournament_analysis()` → narrative, adjustments → `ai_decisions` table. Adjustments applied to composite scores (capped at `config.AI_ADJUSTMENT_CAP` = ±3).
8. **Value:** `value.find_value_bets()` converts composite → probabilities (softmax), blends with DG calibrated probs (95/5), computes EV vs market odds, filters by threshold. `matchup_value.find_matchup_value_bets()` uses Platt-sigmoid.
9. **Portfolio:** `portfolio.enforce_diversification()` + `exposure` caps.
10. **Output:** `card.generate_card()` → `output/{safe_name}_{date}.md`. `methodology.generate_methodology()` → `output/{safe_name}_methodology_{date}.md`. `output_manager.archive_old_outputs()` moves previous to `output/archive/`.

### Post-tournament (after event completes)

1. `learning.post_tournament_learn()` → score picks, update calibration curve, nudge weights, AI post-review.
2. `adaptation.get_adaptation_state()` → rolling ROI → state: normal/caution/cold/frozen → adjusts EV thresholds + stake multipliers.
3. AI learnings stored in `ai_memory` table for retrieval in future tournaments.

### Database Tables (in `src/db.py`)

**Core:** `tournaments`, `rounds`, `metrics`, `results`, `picks`, `pick_outcomes`, `runs`.
**AI:** `ai_memory`, `ai_decisions`, `ai_adjustments`.
**Learning:** `prediction_log`, `calibration_curve`, `weight_sets`, `market_performance`.
**Backtester:** `pit_rolling_stats`, `pit_course_stats`, `historical_predictions`, `historical_odds`, `historical_event_info`, `tournament_weather`, `tournament_weather_summary`, `backfill_progress`.
**Experiments:** `experiments`, `active_strategy`, `outlier_investigations`, `equipment_changes`, `intel_events`.
**Support:** `csv_imports`, `course_encyclopedia`.

Schema and migrations are inline in `src/db.py` (no Alembic). No foreign key constraints enforced. Minor naming inconsistencies (e.g., `dg_id` vs `player_dg_id`).

---

## 6. Key Conventions and Tech Debt

### Conventions (Follow These)

- **Centralized config:** All tunable numbers go in `src/config.py` or env. Never add new magic numbers in consuming modules.
- **Model version:** Use `config.MODEL_VERSION` only; do not duplicate in card.py, methodology.py, or anywhere else.
- **Walk-forward only:** Backtests must use only data available before each event. PIT stats enforce this.
- **Blend weights (95/5):** Model softmax is uncalibrated; DG probabilities dominate. Model is a minor tiebreaker until calibrated. Do not change ratio without calibration evidence.
- **Max 5 value bets per card:** Quality over quantity. Configurable via `config.MAX_TOTAL_VALUE_BETS`.
- **Matchups first:** Best bets drawn from matchups first; placements are fallback (`config.BEST_BETS_MATCHUP_ONLY = True`).
- **Player normalization:** Always use `player_normalizer.normalize_name()` for keys and `display_name()` for output.
- **Test fixtures:** Use `tmp_db` fixture for any test writing to DB. Defined in `tests/conftest.py`.

### Known Tech Debt (Do Not Assume Broken)

- **AI betting decisions disabled:** `ai_brain.make_betting_decisions` intentionally returns None. AI provides pre-tournament adjustments only.
- **Deprecated but still called:** `src/matchups.py` has deprecated `_suggest_matchups` still called from `card.py`. Do not remove without replacing call sites.
- **Duplicate constants:** `MAX_REASONABLE_ODDS` and `_american_to_implied_prob` exist in more than one module. Centralizing in `src/odds.py`/`src/odds_utils.py` is desired but not done.
- **Large app.py:** ~1700+ lines. Splitting into `src/routes/` is partially done (model_registry, research) but app.py still holds most routes. Long-term goal to split further.
- **No foreign keys in DB:** Desired but not enforced. Adding is a future improvement.
- **No full pipeline integration test:** Add one if touching pipeline flow.
- **Prompts are hardcoded strings:** `src/prompts.py` is all string literals. Moving to external files or DB is desired.

---

## 7. User / Operator Expectations (For Agent Behavior)

- **Changes as PR:** User wants all changes pushed as a branch + PR for iteration, not only saved locally. Workflow: branch → implement → push → open PR.
- **No breakage:** Every addition or change must improve the project and not break existing behavior. Test and reason through changes; ensure the pipeline, UI, and backtester continue to work.
- **Realistic feedback:** Do not affirm every idea. If a request is unrealistic, not technically sound, or not aligned with product/codebase, say so clearly.
- **Explain simply:** User assumes minimal experience. Explain steps and decisions in plain terms, as if talking to a beginner.
- **No guessing:** If you don't know the answer, say so rather than making something up.

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

The backtester includes an autonomous research system that proposes, tests, and promotes strategy changes:

- **Theory engine** (`backtester/theory_engine.py`): Generates candidate theories (weight changes, threshold adjustments, etc.)
- **Proposals** (`backtester/proposals.py`): CRUD for strategy proposals (create → evaluate → approve/reject)
- **Research cycle** (`backtester/research_cycle.py`): Orchestrates proposal → backtest → evaluation → dossier
- **Weighted walk-forward** (`backtester/weighted_walkforward.py`): Recency-weighted evaluation (recent events count more)
- **Model registry** (`backtester/model_registry.py`): Tracks live model vs research champion; promotes when evidence is sufficient
- **Research dossier** (`backtester/research_dossier.py`): Writes human-readable evaluation reports
- **Config:** `autoresearch/cycle_config.json`, `autoresearch/strategy_config.json`
- **Runner scripts:** `scripts/run_autoresearch_loop.py`, `scripts/run_autoresearch_eval.py`, `scripts/run_autoresearch_holdout.py`
- **Workers:** `workers/research_agent.py` (5-thread daemon for continuous improvement)

---

## 10. Output Artifacts

- **Cards:** `output/{tournament_safe_name}_{YYYYMMDD}.md` — rankings, value bets, methodology summary, AI summary.
- **Methodology:** `output/{tournament_safe_name}_methodology_{YYYYMMDD}.md` — model version, weights, data sources, detailed explanation.
- **Archive:** `output_manager` moves older cards/methodology to `output/archive/`.
- **Backtest reports:** `output/backtests/*.md` (and `.json`).

---

## 11. Quick Reference: Where to Change What

| Change | Primary file(s) |
|--------|------------------|
| EV thresholds, blend weights, adaptation thresholds | `src/config.py` |
| Feature toggles (Kelly, CLV, exposure, 3ball) | `feature_flags.yaml` |
| Run profile (AI on/off, backfill years) | `profiles.yaml` |
| API keys, provider, preferred book | `.env` |
| Model weights (course_fit/form/momentum, SG sub-weights) | `src/config.py` `DEFAULT_WEIGHTS`; or DB `weight_sets` |
| Card layout or content | `src/card.py` |
| Methodology doc content | `src/methodology.py` |
| Composite model logic | `src/models/composite.py` + `course_fit.py`, `form.py`, `momentum.py` |
| Value/matchup logic | `src/value.py`, `src/matchup_value.py` |
| Kelly sizing logic | `src/kelly.py` |
| AI prompts | `src/prompts.py` |
| AI analysis logic | `src/ai_brain.py` |
| DB schema/migrations | `src/db.py` |
| Pipeline orchestration | `src/services/golf_model_service.py` |
| Web UI routes (most) | `app.py` |
| Web UI routes (registry, research) | `src/routes/model_registry.py`, `src/routes/research.py` |
| Backtest strategy replay | `backtester/strategy.py`, `backtester/pit_models.py` |
| Research cycle / proposals | `backtester/research_cycle.py`, `backtester/proposals.py` |
| Autoresearch config | `autoresearch/cycle_config.json`, `autoresearch/strategy_config.json` |
| Course profiles | `data/courses/*.json`; extraction via `course.py` or `src/course_profile.py` |
| Rolling stats computation | `src/rolling_stats.py` |
| CI | `.github/workflows/ci.yml` |

---

## 12. Updating This Document

- **When to update:** Adding entry points, config keys, critical modules, new conventions, or deprecating behavior.
- **Section 2 (layout):** Keep the tree accurate. Add new files to the correct section.
- **Section 4 (config):** Add new env vars, feature flags, or config.py sections.
- **Section 6 (conventions/debt):** Document new conventions under "Conventions"; new intentional oddities under "Tech Debt".
- **Section 11 (quick reference):** Keep aligned with actual file locations.
- **Charter changes:** Update section 8 and keep `.cursor/rules/project-charter.mdc` in sync.
- **Last verified date:** Update the date at the top when you verify accuracy.
