# Autoresearch v2 — Full Product & Technical Specification

**Status:** Draft for implementation  
**Replaces as design authority:** Ad-hoc autoresearch behavior described only across `AGENTS_KNOWLEDGE.md`, `RUNBOOK.md`, and inline code.  
**Related plan:** `.cursor/plans/autoresearch_v2_rebuild_21771518.plan.md` (high-level roadmap; this document is the binding spec).

---

## 1. Executive summary

Autoresearch v2 is an **automated, bounded search** over `StrategyConfig` parameters that:

1. **Evaluates** candidates with a **single, versioned, immutable backtest harness** (walk-forward + `replay_event`, point-in-time data).
2. **Optimizes** multiple competing metrics (**Pareto / multi-objective**) instead of a single brittle blended score for search—while **hard guardrails** still gate **promotion** to research champion / live.
3. Exposes a **Karpathy-style control plane**: human-authored **program** document, **append-only ledger**, **state** for the active study and Pareto archive, and **fixed budgets** per trial (wall-clock and/or replay scope).
4. **Unifies** today’s fragmented entry points (dashboard, `/api/research/run`, CLI, two daemons) behind one implementation.

This spec is written so engineers can implement without re-deriving requirements from chat history.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
|----|------|
| G1 | **Search** improves or maintains a **Pareto frontier** of (ROI, CLV, risk/calibration) rather than chasing one noisy scalar. |
| G2 | **One canonical evaluator**; pilot checkpoint eval and dashboard eval share core logic or a documented, versioned difference. |
| G3 | **Promotion** remains conservative: guardrails + holdout + model-registry gates (charter-aligned). |
| G4 | **Operators** can see: study health, Pareto trials vs promotable trials, data coverage, last error. |
| G5 | **Reproducibility**: trial params, benchmark spec version, git commit, strategy hash, ledger row. |

### 2.2 Non-goals (v2)

- Replacing the **live weekly model** pipeline or **manual** registry actions.
- **Distributed** multi-machine training (Karpathy’s multi-GPU is irrelevant).
- Guaranteeing **positive live ROI**; only disciplined search and validation.
- Real-time **in-trial pruning** inside walk-forward (see §7.4; Optuna MO + pruners limitations).

---

## 3. Expert background (how systems like this are built)

### 3.1 Karpathy “autoresearch” pattern

The [karpathy/autoresearch](https://github.com/karpathy/autoresearch) repository encodes a **workflow**, not a reusable library:

- **Immutable harness** (`prepare.py`): data, tokenizer, evaluation.
- **Single mutable artifact** (`train.py`): everything the agent may change.
- **Human program** (`program.md`): instructions and constraints.
- **Fixed wall-clock budget** per experiment so trials are comparable.
- **One primary metric** (`val_bpb`, lower is better); keep if improved.

**Mapping to golf:** `prepare.py` → PIT DB + replay infrastructure; `train.py` → `StrategyConfig` / JSON overrides; `program.md` → `docs/research/research_program.md`; metric → **vector** of objectives (user chose Pareto over a single scalar).

### 3.2 Financial ML: walk-forward and overfitting

Industry and academic practice stresses that **optimizing on the same data you score** inflates performance. Mitigations include:

- **Walk-forward analysis**: roll train/test windows through time so parameters are tested on **out-of-sample** segments ([walk-forward optimization](https://en.wikipedia.org/wiki/Walk_forward_optimization)).
- **Purged k-fold / embargo**: for overlapping labels, remove training samples that overlap test label windows ([purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation)); combinatorial variants (CPCV) are used to estimate **probability of backtest overfitting (PBO)** in serious quant work.

**Implication for v2:** The existing **expanding walk-forward** in `weighted_walkforward` is the minimum bar. v2 may add **optional** stricter splits or a **frozen holdout** set for promotion only (already partially present via `run_autoresearch_holdout.py`).

### 3.3 Multi-objective black-box optimization

**Pareto optimality:** A trial is **non-dominated** if no other trial is strictly better on all objectives.

**Optuna (recommended baseline):** [Multi-objective optimization with Optuna](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/002_multi_objective.html) uses `optuna.create_study(directions=[...])`, objective returns a **tuple** of values, and `study.best_trials` yields the **Pareto front**. Visualization includes `plot_pareto_front` and per-objective hyperparameter importance.

**Samplers:** Default **NSGA-II** is a strong baseline for MO; **TPE / MOTPE** variants target expensive objectives (community discussion and Optuna release notes evolve here—pin Optuna version in `requirements.txt` and re-read release notes before ship).

**Pruners:** Standard **median/percentile pruners do not apply** to multi-objective studies in the same way as single-objective; treat each trial as **atomic** (full benchmark run) unless a future Optuna version documents supported MO pruning—**do not** assume step-wise pruning inside `replay_event` loops without verification.

**Parallel noisy MO:** Research literature (e.g. **q-NEHVI**, noisy expected hypervolume improvement) addresses **parallel** batch selection under **noise**—relevant if you later add Gaussian-process surrogates; v2 can stay with Optuna’s built-in samplers + **sequential** trials first.

### 3.4 Constrained expensive optimization

When **feasibility** is expensive (e.g. `total_bets < min_bets`), **penalty-only** objectives can mislead samplers. Prefer:

- Marking trials **infeasible** and using Optuna’s **constraints** / **inf** handling patterns recommended for your Optuna version, **or**
- Returning **dominated** objective vectors that reflect infeasibility, documented in §7.3.

---

## 4. Stakeholders and roles

| Role | Needs |
|------|--------|
| **Operator** | Start/stop search, see Pareto vs promotable, run holdout, promote via registry. |
| **Developer** | Clear module boundaries, one evaluator, tests, migration from v1. |
| **Charter / risk** | No bypass of live promotion gates. |

---

## 5. System context (current repository)

### 5.1 Existing components (v1) to subsume or retire

- **Loop:** `backtester/autoresearch_engine.py` → `run_research_cycle` → `theory_engine` + `evaluate_weighted_walkforward`.
- **Storage:** `research_proposals` table via `backtester/proposals.py`.
- **Champion:** `backtester/model_registry.py`.
- **CLI eval:** `scripts/run_autoresearch_eval.py` (checkpoint, stdout contract).
- **Git loop:** `scripts/run_autoresearch_loop.py` + `autoresearch/strategy_config.json`.
- **Runtimes:** `backtester/optimizer_runtime.py` (thread), `workers/research_agent.py` `autoresearch_loop`.
- **API:** `/api/autoresearch/*`, `/api/optimizer/*`, `POST /api/research/run`.
- **Config drift:** `autoresearch/cycle_config.json` is **not loaded by code** today—v2 must **implement or delete** it.

### 5.2 Strategy resolution (unchanged contract)

Production still uses `src/strategy_resolution.resolve_runtime_strategy` (live → research champion → …). v2 only changes **how** the research champion is **proposed**, not the resolution order.

---

## 6. Functional requirements

### 6.1 Canonical evaluation

**FR-CANON-1:** Implement `evaluate_candidate(strategy, baseline_strategy, benchmark_spec) -> EvaluationResult` where:

- `benchmark_spec` includes: `eval_contract_version`, `years`, `min_train_events`, `test_window_size`, `weighting_mode`, optional `event_filter`, optional `checkpoint_ids` for audit alignment with `pilot_contract.json`.
- Output includes: `summary_metrics`, `baseline_summary_metrics`, `guardrail_results` (reasons, passed), `event_results` (or references), `segmented_metrics`, **objective_vector** (ordered tuple for Optuna), **feasibility** flags.

**FR-CANON-2:** `scripts/run_autoresearch_eval.py` **must** delegate to canonical evaluation (or call a shared library function) so checkpoint and walk-forward modes differ only by `benchmark_spec`.

**FR-CANON-3:** Preflight: `validate_autoresearch_data_health` runs before batch studies; failures surface in API/UI with **actionable** messages.

### 6.2 Multi-objective optimization

**FR-MO-1:** An **Optuna** `study` with `directions` set per objective (e.g. maximize ROI, maximize CLV, minimize calibration error).

**FR-MO-2:** **Parameter space** covers at minimum:

- Sub-model simplex: `w_sub_course_fit`, `w_sub_form`, `w_sub_momentum` via **softmax(logits)** or equivalent reparameterization so weights sum to 1 and stay positive.
- Bounded knobs: `min_ev`, `kelly_fraction`, `softmax_temp`, `max_implied_prob`, `min_model_prob`, `ai_adj_cap`, `use_weather` as applicable.

**FR-MO-3:** **Feasibility:** If `total_bets < min_bets` (or other hard feasibility rules), record trial as infeasible per §7.3; do not present as Pareto-optimal in the same sense as feasible trials (UI badge).

**FR-MO-4:** **Persistence:** Optuna `study` stored in a **dedicated** SQLite file under `output/research/optuna/` (or RDB URL in env) to avoid locking `golf.db` from replay workers.

### 6.3 Control plane (Karpathy-aligned)

**FR-CP-1:** Human-editable **`docs/research/research_program.md`**: objectives, allowed parameter bounds, stop conditions, notes for operators (not executed code).

**FR-CP-2:** **Append-only ledger** `output/research/ledger.jsonl`: one JSON object per trial with fields at minimum: `ts`, `trial_id`, `study_id`, `git_commit`, `strategy_hash`, `eval_contract_version`, `params`, `objective_vector`, `feasible`, `guardrail_passed`, `benchmark_spec_hash`, `duration_ms`, `error` (nullable).

**FR-CP-3:** **State file** `output/research/study_state.json`: active `study_id`, last heartbeat, cumulative trial counts, optional **Pareto snapshot** (trial ids).

**FR-BUDGET-1:** Each trial respects **max_wall_seconds** and **max_replay_events** (configurable); on timeout, trial marked failed with structured error.

### 6.4 Promotion pipeline (separate from search)

**FR-PRO-1:** **Search** produces Pareto **candidates**. **Promotion** to research champion requires:

1. Operator or policy-selected trial from **feasible** Pareto set.
2. `evaluate_guardrails` **passed** vs baseline snapshot used for that benchmark.
3. **Holdout** script success (`run_autoresearch_holdout` or successor) when policy requires it.
4. `model_registry` gates unchanged for live promotion.

**FR-PRO-2:** Automatic champion updates from v1 (`research_cycle` global-best ROI) are **replaced** by explicit policy: either manual pick from Pareto + gates, or automated rule documented in `research_program.md` (e.g. max ROI among feasible trials with CLV ≥ baseline − ε).

### 6.5 API and CLI consolidation

**FR-API-1:** A **single** backend “engine” module powers:

- `POST /api/autoresearch/run-once` (or renamed `run-study-step`)
- `POST /api/autoresearch/start` / `stop` (daemon)
- `POST /api/research/run` → thin wrapper or **redirect** to same engine
- `/api/optimizer/start|stop|status` → **alias** documented; prefer one naming scheme in docs

**FR-API-2:** Responses include: `pareto_trials`, `promotable_trials`, `data_health`, `eval_contract_version`, `study_summary`.

**FR-CLI-1:** `start.py` subcommands `research-run`, `autoresearch-batch` call the same engine.

**FR-CLI-2:** `run_autoresearch_loop.py` either **deprecated** or reimplemented as “invoke N Optuna trials + ledger” without conflicting semantics with dashboard.

### 6.6 User interface

**FR-UI-1:** Dashboard shows:

- **Pareto chart** (e.g. ROI vs CLV) for latest study; points labeled feasible / infeasible.
- **Promotable** list separate from **exploratory** frontier.
- Baseline reference lines from **fixed** benchmark baseline, not conflated with “best failed trial.”

**FR-UI-2:** Engine metrics: trials/hour, guardrail pass rate, last error, data health—**fix** v1 bugs where `keep_rate` is derived from presence of `winner` only.

### 6.7 Daemons

**FR-DAEMON-1:** Only **one** autoresearch daemon path is **supported** by default: either `optimizer_runtime` **or** `research_agent` autoresearch thread—**document mutex** or shared lock on study + DB.

---

## 7. Technical design

### 7.1 Objective vector (normative)

Default **four** objectives (adjustable in `research_program.md` with eval contract version bump):

| Index | Metric | Direction |
|-------|--------|-----------|
| O1 | `weighted_roi_pct` | maximize |
| O2 | `weighted_clv_avg` | maximize |
| O3 | `weighted_calibration_error` | minimize |
| O4 | `max_drawdown_pct` | minimize |

**Rationale:** Matches operator mental model; avoids collapsing to `compute_blended_score` during search (that scalar may remain for **legacy** or **audit** only).

### 7.2 Feasibility and infeasible trials

If `total_bets < min_bets`:

- Set `feasible = false`.
- Option A (preferred): use Optuna **constraints** if available for the pinned version.
- Option B: return objective values that are **strongly dominated** (e.g. large negative ROI placeholder) **and** filter such trials out of `study.best_trials` for operator display—**document** so samplers are not misled long-term.

### 7.3 Baseline handling

Each trial compares candidate vs **same baseline strategy** (current research champion or explicit frozen baseline in `benchmark_spec`). Baseline metrics must be **cached per benchmark_spec** within a process to avoid double replay where v1 already uses `precomputed_baseline`.

### 7.4 Trial atomicity and parallel execution

- **Default:** sequential trials (simplest SQLite + replay safety).
- **Optional:** worker pool with **one writer** to `golf.db` or **read-only** replay connections—must be validated under load.
- Optuna **n_jobs** > 1 only if replay/DB proven safe; otherwise parallelize **studies** (different benchmarks), not shared DB writers.

### 7.5 Versioning

- **`eval_contract_version`:** bump when objective definitions, walk-forward builder, or guardrail semantics change.
- **`api_version`:** bump REST response shapes.
- Migration: v1 `research_proposals` rows tagged `legacy` or `trial_version=1`; v2 trials use `trial_version=2` or new table.

---

## 8. Data model

### 8.1 Optuna storage

- **SQLite** file: `output/research/optuna/studies.db` (path configurable via env).
- **Study name:** e.g. `golf_autoresearch_{scope}_{eval_contract_version}`.

### 8.2 Application DB

Either extend `research_proposals` with:

- `trial_version`, `study_name`, `optuna_trial_number`, `objective_vector_json`, `feasible`, `benchmark_spec_hash`

or create **`research_trials_v2`** with foreign key optional to proposals for human-readable titles.

---

## 9. Contracts and documents

| Document | Purpose |
|----------|---------|
| `docs/research/research_program.md` | Human intent, bounds, stop conditions |
| `docs/autoresearch/evaluation_contract.md` | **v2 bump:** MO outputs, stdout if CLI kept |
| `docs/autoresearch/pilot_contract.json` | Checkpoint lists for audit alignment |
| `program.md` (root) | Deprecate or point to `research_program.md` |

**Stdout protocol (if retained for subprocess eval):** extend beyond scalar `autoresearch_metric` to structured JSON line(s) for MO, or single JSON blob with version field.

---

## 10. Observability and operations

- Structured logging: `research_lab.trial_start`, `trial_complete`, `trial_error`.
- Metrics: trial duration, replay count, guardrail reason histogram.
- **Runbook** update: `docs/autoresearch/RUNBOOK.md` with v2 operator steps.
- GitHub issue template `.github/ISSUE_TEMPLATE/autoresearch-run.yml` updated for Pareto + holdout checklist.

---

## 11. Security and safety

- **Secrets:** No API keys in ledger; `.env` unchanged.
- **Subprocess:** If eval stays subprocess-based, validate timeouts and max output size.
- **Git hooks:** v1 `run_autoresearch_loop` git commit behavior—either **remove** from default path or restrict to opt-in to avoid surprising repo mutations.

---

## 12. Testing strategy

| Layer | Tests |
|-------|--------|
| Unit | Parameter mapping (simplex), `EvaluationResult` schema, Pareto filtering helpers |
| Integration | Mocked `replay_event` pipeline with fixed event list; Optuna study 5–10 trials |
| Contract | Migration of v1 rows; API response shapes |
| Regression | Promotion gates (`test_autoresearch_promotion_policy` patterns) still pass |

---

## 13. Rollout plan

1. **Canonical eval + tests (no UI)** — **in progress (phase 1 landed):** `backtester/research_lab/canonical.py` provides `EvaluationResult`, `evaluate_walk_forward_benchmark`, `evaluate_checkpoint_pilot`, `evaluation_from_walk_forward_dict`, objective vector, `feasible` flag. `scripts/run_autoresearch_eval.py` delegates to canonical. `run_research_cycle` attaches `canonical_evaluation` + `eval_contract_version_walk_forward` to API payload. Tests: `tests/test_canonical_evaluation.py`.
2. Add Optuna study + CLI `research-run` pointing to v2.
3. Wire dashboard read-only Pareto view.
4. Disable v1 `theory_engine` default; feature flag if needed.
5. Remove dead `cycle_config` references or implement loading.
6. Documentation sweep: `AGENTS_KNOWLEDGE.md` §9.

---

## 14. Open questions (resolve before coding)

1. **Exact** automated rule for “pick champion from Pareto” vs manual-only.
2. **Minimum** trial count for feasibility—align with `min_bets` in guardrails vs search-only floor.
3. **Pin** Optuna version and re-verify MO + constraints API.
4. Whether **LLM** proposes **initial** trials (warm start) or is **removed** from default path.

---

## 15. References

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — autonomous experiment loop pattern.
- [Optuna: Multi-objective optimization](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/002_multi_objective.html) — `directions`, `best_trials`, Pareto front.
- [Walk-forward optimization (Wikipedia)](https://en.wikipedia.org/wiki/Walk_forward_optimization) — time-rolled validation.
- [Purged cross-validation (Wikipedia)](https://en.wikipedia.org/wiki/Purged_cross-validation) — overlap-safe CV for time series.
- López de Prado — *Advances in Financial Machine Learning* — CPCV, PBO (conceptual reference for future hardening).
- [Parallel BO for multiple noisy objectives (q-NEHVI)](https://arxiv.org/abs/2105.08195) — optional future scaling.
- [Optuna discussion: MO constraints / MOTPE vs NSGA-II](https://github.com/optuna/optuna/discussions/5259) — sampler selection notes.

---

## Document history

| Date | Change |
|------|--------|
| 2026-03-20 | Initial full spec from v2 plan + repo audit + external research |
| 2026-03-20 | Phase 1: canonical module + research_cycle / eval script wiring (see §13) |
