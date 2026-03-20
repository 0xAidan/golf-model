# Research program (control plane)

This document is the **human-edited contract** for autoresearch in this repository. It is **not** executable code. Implementation details live in `backtester/research_lab/` and `docs/autoresearch/SPEC_V2.md`.

## Immutable harness

- Walk-forward evaluation and PIT replay are fixed for a given `eval_contract_version` (see `backtester/research_lab/canonical.py`).
- Checkpoint pilot evaluation (`scripts/run_autoresearch_eval.py`) is a separate audit path; align benchmarks explicitly if you compare numbers.

## Mutable artifacts

| Artifact | Purpose |
|----------|---------|
| `autoresearch/strategy_config.json` | Strategy overrides for CLI / agent workflows |
| Optuna study (`output/research/optuna/studies.db`) | Persisted trials — **MO** and **scalar** studies use **different** `study_name` values |

## Engines (pick one)

1. **Research cycle** — theory proposals + walk-forward, writes `research_proposals`.
2. **Optuna MO** — multi-objective Pareto search (ROI, CLV, calibration, drawdown); **exploration**, not a single “improve ROI” guarantee.
3. **Optuna scalar** — single objective (`blended_score` or `weighted_roi_pct`); closest automated analogue to a **one-number** improvement loop (see Karpathy runbook).

## Promotion

- Search output is **not** live promotion. Research champion / live registry gates from the project charter still apply.
- Prefer **holdout** scripts before promoting (`run_autoresearch_holdout` / policy in model registry).

## Ledger

- Every Optuna trial appends a row to `output/research/ledger.jsonl` (and CLI loop dual-writes the legacy filename).
- Fields include `source`, `trial_id`, `strategy_hash`, `benchmark_spec_hash`, `duration_ms`, `objective_vector` or `scalar_metric`, `feasible`, `guardrail_passed`, `error`.

## Budgets

- `AUTORESEARCH_MAX_TRIAL_SECONDS` (default `3600`) caps wall time per trial evaluation (thread timeout). Set lower on laptops.

## Local Mac

- No GPU required. Keep `data/` and `output/` off iCloud/Dropbox. Prefer sequential Optuna (`n_jobs=1`).

## Related

- Operator steps: `docs/autoresearch/RUNBOOK.md`
- Agent-driven workflow: `docs/research/KARPATHY_AGENT_RUNBOOK.md`
