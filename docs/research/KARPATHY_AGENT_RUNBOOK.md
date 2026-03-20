# Karpathy-style agent workflow (Cursor / LLM)

[Karpathy’s autoresearch](https://github.com/karpathy/autoresearch) uses a **human `program.md`**, a **fixed evaluation harness**, **one mutable training file**, and an **LLM** that edits code in a tight loop. This repo maps that pattern to golf strategy search **without** GPU training.

## Mapping

| Karpathy | Golf model |
|----------|------------|
| `prepare.py` (immutable) | Walk-forward + `replay_event` + DB (`evaluate_walk_forward_benchmark`) |
| `train.py` (agent edits) | `autoresearch/strategy_config.json` **or** Optuna parameters indirectly via dashboard/CLI |
| `program.md` | This doc + `docs/research/research_program.md` + root `program.md` |
| `results.tsv` / logs | `output/research/ledger.jsonl` |
| Fixed 5-minute runs | `AUTORESEARCH_MAX_TRIAL_SECONDS` per trial |

## Setup

1. Ensure `data/golf.db` and PIT/odds prerequisites (see `docs/autoresearch/RUNBOOK.md`).
2. Read `docs/research/research_program.md` and the evaluation contract.
3. Baseline strategy comes from research champion → live weekly → active strategy.

## Agent loop (manual)

1. Propose **one** coherent change to `autoresearch/strategy_config.json` (or document parameters if using Optuna only).
2. Run **one** evaluation:
   - Walk-forward: `python scripts/run_autoresearch_optuna.py --n-trials 1 ...` or dashboard **Run trials**.
   - Checkpoint pilot: `python scripts/run_autoresearch_eval.py` (audit contract).
3. Inspect `output/research/ledger.jsonl` for the new row (`source` will indicate origin).
4. **Keep** if scalar objective / policy improves and guardrails pass; **discard** otherwise (revert JSON).

## Automated scalar overnight

If you want **unattended** single-objective search, use **Engine = Optuna scalar** in the dashboard (not the LLM loop). That optimizes `blended_score` or `weighted_roi_pct` per settings and logs every trial.

## What not to do

- Do not treat **Optuna MO** as “maximize ROI only” — it returns a **Pareto** set unless you add an explicit selection rule in `research_program.md`.
- Do not edit evaluator code for “quick wins” during a study; bump `eval_contract_version` if the harness changes.
