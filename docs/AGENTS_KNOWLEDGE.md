# Golf Model — Agent Knowledge Base

**Purpose:** Single reference for AI agents working in this repo. Attach this doc to new chats so agents can execute tasks without scanning the codebase. Update this file when structure, conventions, or critical paths change.

**Audience:** AI agents (LLM instances). Optimized for programmatic parsing and minimal ambiguity; not optimized for human narrative.

---

## 1. Project Summary

- **What it is:** Quantitative golf betting system. Data Golf API → round-level SG data, predictions, odds. Composite model (course fit + form + momentum) scores players; value layer compares model vs market for EV; AI layer does qualitative analysis and persistent memory. Post-tournament: grade picks, calibration, weight nudges, AI learnings.
- **Stack:** Python 3.11+, SQLite, FastAPI for web UI. No frontend framework beyond templates + vanilla JS.
- **Key constraints:** Walk-forward backtesting only (no future data). Bootstrap phases (shadow → paper → cautious live → full live). Stopping rules and go-live gates in project charter. See section 8.

---

## 2. Repository Layout (Critical Paths)

```
golf-model/
├── run_predictions.py       # CLI: full pipeline (main entry for "run predictions")
├── app.py                  # FastAPI web UI + API (dashboard at :8000)
├── start.py                # Unified launcher (menu + subcommands)
├── setup_wizard.py         # First-time: backfill data, init DB
├── analyze.py              # Lightweight CLI (delegates to GolfModelService)
├── results.py              # Results entry / grading
├── dashboard.py           # (if present) dashboard utilities
├── .env                    # API keys (from .env.example); never commit
├── .env.example            # Template for required keys
├── feature_flags.yaml      # Toggles: kelly_sizing, clv_tracking, exposure_caps, etc.
├── profiles.yaml           # Run profiles: default, quick, full (tour, enable_ai, backfill_years, output_dir)
├── src/
│   ├── config.py           # CENTRAL CONFIG: all magic numbers, thresholds, weights (single source of truth)
│   ├── db.py               # SQLite schema, migrations, connection
│   ├── datagolf.py         # Data Golf API client
│   ├── golf_model_service  # (package) orchestration used by ALL entry points
│   │   └── golf_model_service.py  # GolfModelService.run_analysis()
│   ├── models/             # course_fit, form, momentum, weather, composite, weights
│   ├── value.py            # EV, value bet detection
│   ├── matchup_value.py    # Matchup EV (Platt-style)
│   ├── card.py             # Betting card markdown generation
│   ├── methodology.py      # Methodology doc generation
│   ├── ai_brain.py         # AI analysis, adjustments, memory (OpenAI/Anthropic/Gemini)
│   ├── learning.py         # Post-tournament learning
│   ├── adaptation.py       # Market adaptation state (normal/caution/cold/frozen)
│   ├── odds.py             # Odds fetch (The Odds API) + best odds
│   ├── portfolio.py        # Diversification / exposure
│   ├── output_manager.py   # output/ cleanup, archive
│   └── ...                 # scoring, calibration, confidence, prompts, etc.
├── backtester/
│   ├── strategy.py         # Walk-forward strategy replay
│   ├── pit_models.py       # Point-in-time models (imports src.models + config)
│   ├── pit_stats.py        # PIT stats builder
│   ├── research_cycle.py   # Research cycle (proposals, dossier, theory engine)
│   ├── model_registry.py   # Model registry / research champion
│   ├── proposals.py        # Proposals approve/create/update
│   └── ...
├── workers/                # research_agent, intel_harvester
├── scripts/                # grade_tournament, backfill_matchup_odds, backtest_*, run_autoresearch_*
├── tests/                  # pytest; conftest.py has tmp_db, sample_tournament, sample_metrics
├── data/                   # courses/*.json, golf.db (SQLite), correlated_courses.json
├── output/                 # Generated cards + methodology; output/archive/ for older
├── templates/              # index.html (web UI)
├── docs/                   # Research, plans, this file
└── .cursor/rules/
    └── project-charter.mdc # Stopping rules, bootstrap, go-live gates — REFER for deployment
```

- **Config surface:** `.env` (API keys, AI_BRAIN_PROVIDER, EV_THRESHOLD, etc.), `feature_flags.yaml`, `profiles.yaml`, `src/config.py`. New tuning should go in `src/config.py` or env, not magic numbers in code.
- **Model version:** Single source of truth `src/config.MODEL_VERSION` (currently `"4.2"`). Do not duplicate version in card.py/methodology.py.

---

## 3. Entry Points and How to Run

| Intent | Command / entry |
|--------|------------------|
| Full prediction pipeline (CLI) | `python run_predictions.py` |
| Web UI + API | `python app.py` → http://localhost:8000, API at /docs |
| First-time setup | `python setup_wizard.py` |
| Lightweight analysis | `python analyze.py` (uses GolfModelService) |
| Unified launcher | `python start.py` (menu; can route to pipeline, backtester, etc.) |
| Calibration dashboard | `python analyze.py --calibration` (per README) |
| Tests | `pytest` (or `python -m pytest`); ~138 tests. Fixtures: `tmp_db`, `sample_tournament`, `sample_metrics` in `tests/conftest.py`. |

- Pipeline flow (high level): detect event → backfill rounds (if enabled) → sync DG (predictions, decompositions, field) → skill/rankings → rolling stats → course profile → composite (course_fit, form, momentum) → optional AI pre-tournament → value + matchup value → card + methodology → write to `output/`.
- All orchestration goes through `src.services.golf_model_service.GolfModelService.run_analysis()` for consistency.

---

## 4. Configuration Reference

- **`.env`:** `DATAGOLF_API_KEY` (required), `OPENAI_API_KEY` (recommended), `ANTHROPIC_API_KEY` (optional), `ODDS_API_KEY` (optional), `AI_BRAIN_PROVIDER` (openai|anthropic|gemini), `OPENAI_MODEL`, `EV_THRESHOLD`, `MATCHUP_EV_THRESHOLD`, `PREFERRED_BOOK`, etc. See `.env.example`.
- **`feature_flags.yaml`:** Booleans: `dynamic_blend`, `exposure_caps`, `kelly_sizing`, `kelly_stakes`, `clv_tracking`, `dead_heat_adjustment`, `3ball`, `use_confirmed_field_only`. Read via `src/feature_flags.py`.
- **`profiles.yaml`:** `profiles.default`, `profiles.quick`, `profiles.full` with `tour`, `enable_ai`, `enable_backfill`, `backfill_years`, `output_dir`.
- **`src/config.py`:** EV thresholds, blend weights (DG vs model), adaptation thresholds, matchup (Platt, EV threshold, caps), default weights (course_fit/form/momentum, SG sub-weights), weather/confidence/data-integrity constants. Change tuning here; do not add new magic numbers in value.py, adaptation.py, etc.

---

## 5. Data Flow (Abbreviated)

1. **Event:** Data Golf current event or explicit tournament/course/event_id.
2. **DB:** `tournaments`, `rounds`, `metrics`, `results`, `picks`, `pick_outcomes`; AI: `ai_memory`, `ai_decisions`, `ai_adjustments`; learning: `prediction_log`, `calibration_curve`, `weight_sets`, `market_performance`; backtester: `pit_rolling_stats`, `pit_course_stats`, `historical_*`, `backfill_progress`, etc. Schema and migrations live in `src/db.py` (no separate migration tool). No foreign keys enforced; naming has minor inconsistencies (e.g. dg_id vs player_dg_id).
3. **Sync:** `datagolf` fetches rounds, pre_tournament, decompositions, field, skill_ratings, rankings, approach_skill → stored in DB.
4. **Rolling:** `rolling_stats.compute_rolling_metrics` from `rounds` → `metrics` (windows 8/12/16/24/all).
5. **Composite:** `models.composite.compute_composite` → course_fit (course_profile + metrics), form, momentum; weights from config/DB; optional weather.
6. **AI:** `ai_brain.pre_tournament_analysis` → adjustments applied to composite.
7. **Value:** `value.find_value_bets` (model vs market, EV threshold, blend DG/model); `matchup_value.find_matchup_value_bets` (Platt-style). Portfolio/diversification applied.
8. **Output:** `card.generate_card`, `methodology.generate_methodology` → `output/{safe_name}_{date}.md`, `output/{safe_name}_methodology_{date}.md`. `output_manager` archives older files to `output/archive/`.

---

## 6. Key Conventions and Tech Debt (Do Not Assume Broken)

- **Centralized config:** All tunable numbers in `src/config.py` or env. Do not add new magic numbers in value.py, adaptation.py, matchup_value.py, etc.
- **Model version:** Use `config.MODEL_VERSION` only; keep card/methodology in sync.
- **Walk-forward only:** Backtests must use only data available before each event. `backtester/pit_models.py` and `backtester/pit_stats.py` implement PIT; use same model code as live (`src/models/` + config).
- **Deprecated but still used:** `src/matchups.py` has deprecated `_suggest_matchups`; still called from card. Prefer not removing without replacing call sites.
- **AI betting decisions:** `ai_brain.make_betting_decisions` is intentionally disabled (returns None). AI provides adjustments only.
- **Duplicate constants:** `MAX_REASONABLE_ODDS` and `_american_to_implied_prob` exist in more than one module; centralizing in `src/odds.py` is desired but not yet done. When changing, update all call sites.
- **Large app.py:** FastAPI app is large (~1700+ lines); splitting into modules is desired long-term, not a requirement for small changes.
- **Tests:** Use `tmp_db` for any test that writes to DB. No integration test for full pipeline yet; add if touching pipeline flow.

---

## 7. User / Operator Expectations (For Agent Behavior)

- **Changes as PR:** User wants changes pushed as a PR for iteration, not only saved locally. Prefer: branch → implement → push → open PR.
- **No breakage:** Every addition or change should improve the project and not break existing behavior. Test and reason through changes; ensure the bot (pipeline, UI, backtester) continues to work.
- **Realistic feedback:** Do not affirm every idea. If a request is unrealistic, not technically sound, or not aligned with product/codebase, say so clearly.
- **Explain simply:** User assumes minimal experience; explain steps and decisions in plain terms where helpful.

---

## 8. Project Charter (Deployment and Strategy)

**Source:** `.cursor/rules/project-charter.mdc`. Refer for every deployment decision.

- **Stopping rules (SPRT-inspired):** CLV < 0% after 150 bets → full investigation. CLV < 0% and negative ROI after 300 bets → stop live betting until root cause fixed and re-validated.
- **Bootstrap phases:** Shadow (1–5 events, predict only) → Paper (6–15, paper trade) → Cautious Live (16–25, 1/8 Kelly) → Full Live (26+, 1/4 Kelly). Gates: Shadow→Paper (Brier < 0.25, no systematic calibration bias); Paper→Cautious (CLV > 0% over 100+ bets); Cautious→Full (CLV > 1% over 250+ bets, hit rate > 55%, max drawdown < 15%).
- **Go-live hard gates (all required for full live):** 250+ tracked bets; avg CLV > 1%; CLV hit rate > 55%; Brier < 0.22 for matchups; no segment Brier > 0.28; max paper drawdown < 20%.
- **Shadow mode:** Run pipeline in parallel with alternate config/blend; compare cards and Brier/CLV before promoting.
- **Backtesting:** Walk-forward only; train on data before each event, then advance. Use `backtester/pit_models.py` (imports from `src/models/` and config).

---

## 9. Output Artifacts

- **Cards:** `output/{tournament_safe_name}_{YYYYMMDD}.md`. Contains rankings, value bets, methodology summary, AI summary if enabled.
- **Methodology:** `output/{tournament_safe_name}_methodology_{YYYYMMDD}.md`. Detailed model version, weights, data sources.
- **Archive:** `output_manager` moves older cards/methodology to `output/archive/` when managing output dir.
- **Backtest reports:** `output/backtests/*.md` (and sometimes `.json`).

---

## 10. Quick Reference: Where to Change What

| Change | Primary location |
|--------|------------------|
| EV thresholds, blend weights, adaptation thresholds | `src/config.py` |
| Feature toggles (Kelly, CLV, exposure, 3ball) | `feature_flags.yaml` |
| Run profile (AI on/off, backfill years) | `profiles.yaml` |
| API keys, provider, preferred book | `.env` |
| Model weights (course_fit/form/momentum, SG sub-weights) | `src/config.py` DEFAULT_WEIGHTS; or DB weight_sets |
| Card layout or content | `src/card.py` |
| Methodology doc content | `src/methodology.py` |
| Composite model logic | `src/models/composite.py` + course_fit, form, momentum |
| Value/matchup logic | `src/value.py`, `src/matchup_value.py` |
| AI prompts | `src/prompts.py` |
| DB schema/migrations | `src/db.py` |
| Pipeline orchestration | `src/services/golf_model_service.py` |
| Backtest strategy | `backtester/strategy.py`, `backtester/pit_models.py` |
| Research cycle / proposals | `backtester/research_cycle.py`, `backtester/proposals.py` |

---

## 11. Updating This Document

- When adding new entry points, config keys, or critical modules: add them to the relevant sections above.
- When changing bootstrap/charter: update section 8 and keep `.cursor/rules/project-charter.mdc` in sync.
- When establishing new conventions or deprecating behavior: document in section 6.
- Keep section 10 (Quick Reference) aligned with actual code locations.
