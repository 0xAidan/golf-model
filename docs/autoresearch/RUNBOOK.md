# Autoresearch operator runbook

## Prerequisites

1. **SQLite `data/golf.db`** with historical **`rounds`**, **`pit_rolling_stats`** (run `backtester.pit_stats.build_all_pit_stats` for your years), **`historical_odds`**, and **`historical_matchup_odds`** (backfill scripts / Data Golf pipeline).
2. **`DATAGOLF_API_KEY`** for live runs; OpenAI optional for theory generation (falls back to directed + neighbor search).
3. Understand **operator paths**:
   - **Simple Mode (recommended):** the dashboard’s default **Edge Tuner** flow uses `/api/simple/autoresearch/start|status|stop|run-once`. It always runs **Optuna scalar**, uses **`weighted_roi_pct`** as the main objective, keeps **report-only** behavior, and uses the default scalar study base name **`golf_scalar_simple`**.
   - **Lab Mode:** exposes the advanced controls below if you want to inspect or run the underlying engines manually.
4. Understand **evaluation paths**:
   - **Research-cycle engine (default):** Dashboard “Start Engine” / `POST /api/autoresearch/start` with `engine_mode: "research_cycle"` → `backtester/autoresearch_engine.run_cycle` → weighted walk-forward + `replay_event` → **`research_proposals`**. **Research champion** auto-update runs only if **`AUTORESEARCH_AUTO_APPLY=1`** (default is report-only; see `docs/research/EDGE_TUNER_REPORT.md`).
   - **Optuna MO:** `engine_mode: "optuna"` → multi-objective Pareto trials via `backtester/research_lab/mo_study.py`, storage `output/research/optuna/studies.db`. **Exploration:** tradeoffs between ROI, CLV, calibration, drawdown — not a single “ROI only” optimizer unless you add a selection policy in `docs/research/research_program.md`.
   - **Optuna scalar:** `engine_mode: "optuna_scalar"` → single-objective (`blended_score` or `weighted_roi_pct` per settings). Uses a **different** `study_name` than MO (default `golf_scalar_simple` vs `golf_mo_dashboard`). CLI: `python scripts/run_autoresearch_optuna.py --scalar --scalar-metric blended_score --study-name golf_scalar_simple`.
   - **CLI contract eval (audit):** `scripts/run_autoresearch_eval.py` + **`docs/autoresearch/pilot_contract.json`** — immutable checkpoints for holdout/audit; not the same JSON as the live dashboard cycle unless you align contracts manually.
5. **Ledger:** Every Optuna trial appends to **`output/research/ledger.jsonl`** (append-only). CLI loop (`scripts/run_autoresearch_loop.py`) dual-writes the legacy filename. **State:** `output/research/study_state.json` (heartbeat when the daemon starts/stops).
6. **Trial budget:** `AUTORESEARCH_MAX_TRIAL_SECONDS` (default `3600`) caps wall time per walk-forward evaluation.
7. **Local Mac:** No GPU required. Keep the repo off iCloud/Dropbox for SQLite stability; use fewer trials / shorter years if runs are slow.

## Mutex: dashboard engine vs research worker

Do **not** run **`workers/research_agent.py` autoresearch loop** at the same time as the dashboard autoresearch engine: the worker **skips** its cycle when the optimizer reports `running`, but you should still avoid starting both intentionally — one driver is enough.

## Running a cycle

- **UI Simple Mode:** Autoresearch tab → **Start Edge Tuner** or **Run Once**. This is the recommended path and always uses the safe scalar wrapper.
- **UI Lab Mode:** Autoresearch tab → **Lab Mode** for direct engine selection, Pareto study inspection, theory toggles, and reset controls.
- **Legacy lab run-once:** `POST /api/autoresearch/run-once` still runs the bounded **research** cycle, not Optuna.
- **Start engine:** `POST /api/autoresearch/start` with optional `engine_mode` (`research_cycle` | `optuna` | `optuna_scalar`), `optuna_study_name`, `optuna_scalar_study_name`, `scalar_objective`, `optuna_trials_per_cycle`, `max_candidates`.
- **Study read-only:** `GET /api/autoresearch/study?study_kind=mo|scalar&study_name=...` loads MO Pareto or scalar best-trial summary plus `dashboard` aggregates. The stats bar uses these for **Optuna MO** and **Optuna scalar** so it does not mix in the research-proposal list (ranked by blended score).
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
- `docs/research/research_program.md` — control plane (human program)
- `docs/research/KARPATHY_AGENT_RUNBOOK.md` — LLM/agent workflow
- `program.md` — pointer to the above
