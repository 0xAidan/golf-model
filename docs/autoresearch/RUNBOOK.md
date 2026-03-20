# Autoresearch operator runbook

## Prerequisites

1. **SQLite `data/golf.db`** with historical **`rounds`**, **`pit_rolling_stats`** (run `backtester.pit_stats.build_all_pit_stats` for your years), **`historical_odds`**, and **`historical_matchup_odds`** (backfill scripts / Data Golf pipeline).
2. **`DATAGOLF_API_KEY`** for live runs; OpenAI optional for theory generation (falls back to directed + neighbor search).
3. Understand **evaluation paths**:
   - **Research-cycle engine (default):** Dashboard “Start Engine” / `POST /api/autoresearch/start` with `engine_mode: "research_cycle"` → `backtester/autoresearch_engine.run_cycle` → weighted walk-forward + `replay_event` → **`research_proposals`** and optional **research champion** update.
   - **Optuna engine:** Same start endpoint with `engine_mode: "optuna"` (or **Autoresearch** tab → Engine = Optuna MO) → multi-objective trials via `backtester/research_lab/mo_study.py`, storage under `output/research/optuna/studies.db`. **Manual trials:** `POST /api/autoresearch/optuna/run` or CLI `python start.py autoresearch-optuna` / `python scripts/run_autoresearch_optuna.py`.
   - **CLI contract eval (audit):** `scripts/run_autoresearch_eval.py` + **`docs/autoresearch/pilot_contract.json`** — immutable checkpoints for holdout/audit; not the same JSON as the live dashboard cycle unless you align contracts manually.

## Mutex: dashboard engine vs research worker

Do **not** run **`workers/research_agent.py` autoresearch loop** at the same time as the dashboard autoresearch engine: the worker **skips** its cycle when the optimizer reports `running`, but you should still avoid starting both intentionally — one driver is enough.

## Running a cycle

- **UI:** Autoresearch tab → **Run once** (calls `POST /api/autoresearch/run-once`) — always the bounded **research** cycle, not Optuna.
- **Start engine:** `POST /api/autoresearch/start` (same as optimizer start) with optional `engine_mode` (`research_cycle` | `optuna`), `optuna_study_name`, `optuna_trials_per_cycle`, `max_candidates`.
- **Pareto read-only:** `GET /api/autoresearch/study?study_name=...` loads SQLite study summary plus `dashboard` aggregates (max ROI/CLV over completed trials, Pareto “promotable” count). The Autoresearch stats bar uses these when **Engine = Optuna MO** so it does not mix in the research-proposal list (which is ranked by blended score, not raw ROI).
- **API (research once):** `{"scope": "global", "max_candidates": 3, "years": [2024, 2025]}`.
- **Response:** Includes `data_health` (row counts, warnings), `guardrail_mode` (strict/loose from UI or env), `promotion_decision`, `winner`.

### Theory / LLM

`use_theory_engine_llm` (settings file / dashboard **LLM theories** checkbox) defaults to **off**; when off, `backtester/theory_engine.py` does not call OpenAI and uses directed + neighbor fallback only.

If `data_health.ok` is false, fix backfill/PIT before trusting ROI/CLV numbers.

## Guardrails

- Configured via **`get_autoresearch_guardrail_params()`** in `src/config.py`, overridden by **`data/autoresearch_settings.json`** (`guardrail_mode`: strict | loose) or env `AUTORESEARCH_GUARDRAIL_*`.
- Typical failure reasons: `insufficient_sample`, `clv_regression`, `calibration_regression`, `drawdown_regression`. See `next_attempt_hint` on evaluated proposals.

## Promotion to production

1. **Research champion** updates automatically when a candidate passes iteration rules (`run_research_cycle`); full auto-approval requires higher bet counts.
2. **Live weekly model** is **separate** — promote via registry API (`/api/model-registry/promote-research-to-live` or dashboard) with charter gates.
3. **Strategy resolution** for predictions: **live → research champion → active_strategy → default** (`src/strategy_resolution.py`).

## Charter

See `.cursor/rules/project-charter.mdc` for bootstrap phases and go-live gates before increasing real stakes.

## Related docs

- `docs/AGENTS_KNOWLEDGE.md` section 9  
- `docs/autoresearch/evaluation_contract.md`  
- `program.md` (control-plane notes for CLI loop scripts)
