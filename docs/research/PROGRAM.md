# PROGRAM — Golf Autoresearch Control Plane

**Status:** Authoritative research-organization definition (Karpathy `program.md` equivalent).
**Operators iterate THIS FILE to steer the research org. Agents and daemon cycles MUST read it before doing anything.**
Companion docs: [execution plan](../plans/autoresearch_execution_plan.md) · [agent runbook](KARPATHY_AGENT_RUNBOOK.md) · [operator runbook](../autoresearch/RUNBOOK.md)

---

## Scope

This program governs the autonomous strategy-research loop only:

- **In scope:** mutating `autoresearch/strategy_config.json` parameters inside declared ranges; running evaluations through the frozen evaluator; recording every trial in the append-only ledger; staging promotion-ready dossiers for human action.
- **Out of scope:** editing any Python module under `backtester/`, `src/`, `workers/`, `frontend/`; touching live prediction/grading/live-refresh behavior; placing or suggesting real bets; contacting any paid API beyond keys already configured; opening pull requests without explicit operator action.

The single mutable artifact is `autoresearch/strategy_config.json`. Everything else is read-only to the loop.

## Immutable Evaluator Rule

The evaluator is FROZEN. It consists of:

| Component | File | Version constant |
|---|---|---|
| Walk-forward replay | `backtester/weighted_walkforward.py` | `EVAL_CONTRACT_VERSION_WALK_FORWARD = 2` |
| Checkpoint pilot | `backtester/checkpoint_replay.py` + `research_lab/canonical.py` | `CHECKPOINT_SCRIPT_EVALUATOR_VERSION = 1` |
| Strategy replay core | `backtester/strategy.py` | pinned by characterization tests |
| PIT data layer | `backtester/pit_models.py`, `backtester/pit_stats.py` | pinned by characterization tests |

Rules:

1. No loop participant may modify evaluator files. CI enforces this twice: `frozen-zone-guard` blocks diffs to these paths, and `tests/test_evaluator_characterization.py` pins golden metrics on fixture databases.
2. Every ledger row carries `evaluator_version` plus `evaluator_fingerprint` (sha256 over evaluator source). A changed fingerprint with an unchanged version number indicates tampering or drift — treat all comparisons against older rows as invalid.
3. Evaluator fixes happen ONLY as human-reviewed PRs that bump the relevant version constant(s) AND regenerate characterization baselines. Such a bump invalidates cross-version experiment comparisons; re-baseline the champion before resuming keep/discard decisions.
4. Evaluation windows are frozen per cycle by the window-selection helper (search / confirmation / sealed-holdout sets). Windows may only be re-declared here or by a reviewed PR — never chosen ad hoc by a cycle.

## Objective

One primary metric decides everything — the **research score**:

> Flat-unit ROI percent on MATCHUP bets, out-of-sample via purged walk-forward, priced against the operator's own collected book lines (`market_prediction_rows` pre-tournament snapshots), graded by the existing outcomes spine.

Hard floors (all must pass for a keep verdict):

- `n >= 300` primary-window picks (below this, the cycle is REPORT-ONLY: log everything, decide nothing).
- Brier/calibration must not regress vs the current champion beyond tolerance (central constants in the autoresearch guardrail settings; strict mode defaults).
- CLV regression within strict guardrail tolerance.
- Max drawdown regression within strict guardrail tolerance.

Keep/discard rule (mechanical, no judgment): a candidate replaces the lab-champion-candidate ONLY if its primary score improves on the search window AND every floor above passes AND the edge survives the rolling confirmation window (currently 3 most recent completed capture-era events, rotating forward as new events grade). Both outcomes are ALWAYS appended to `output/research/ledger.jsonl`. Nothing is ever deleted from the ledger.

Multiplicity armor: every dossier states how many trials were run in the lineage (deflation context); winners must survive the fresh confirmation window; the sealed holdout (below) is the final quarterly check.

Sealed holdout: `docs/research/sealed_holdout_events.json` lists events excluded from ALL search and confirmation windows. They are opened ONLY by operator invocation of `scripts/run_autoresearch_sealed_holdout.py`; results append permanently to the ledger regardless of outcome.

## Loop Protocol

Each cycle (nightly fast tier unless declared otherwise):

1. Read this file. Verify `evaluator_fingerprint` matches the last known-good value; abort and alert on mismatch.
2. Load the champion candidate config and compute its `config_hash`.
3. Propose mutations strictly within the ranges declared in `autoresearch/strategy_config.json`.
4. Evaluate each candidate on the frozen SEARCH window under the fixed budget (effort preset: Light ≈ 20 min, Standard ≈ 60 min / ~100 trials, Max ≈ 3 h — set via dashboard settings; never exceeded).
5. Apply the mechanical keep/discard rule; append one ledger row per trial (ts, source, config_hash, parent_hash, mutation description, tier, window id, all metrics incl. per-segment n, verdict, runtime_ms, evaluator_version, evaluator_fingerprint).
6. For survivors, run the CONFIRMATION window evaluation; append those rows too.
7. If a survivor passes everything AND n >= 300: write a promotion-ready dossier (human-readable, with diff-vs-champion, evidence, trial counts) and send ONE high-signal alert. Do NOT promote anything yourself — ever.
8. Weekly deep cycle additionally refreshes Data Golf data (resume-safe backfill), rebuilds PIT caches incrementally, then searches.
9. On crash or stall: recover state from the ledger, never re-write history, resume at the next trial.

Escalation: repeated guardrail failures (>20 consecutive cycles with zero keeps), evaluator-fingerprint mismatch, ingestion failure, or sealed-holdout anomaly → high-signal alert immediately and halt further trials until an operator intervenes.

## Promotion Rule

Autonomy ends at the dossier. The promotion ladder is human-driven:

1. **Research → Lab:** Operator clicks "Promote to Lab" in the dashboard confirm modal (shows exact config diff + evidence). This records an auditable track-config row with rollback available in one click. Maximum one lab swap per week by convention.
2. **Lab → Main:** Existing gated flow (`/eval` Promotion tab, typed confirmation, charter go-live gates). Production swaps always require typed human confirmation; automation never touches the dashboard champion.
3. **Rollback:** One action restores the parent config at either rung.
4. Per-algorithm performance ("eras") is measured strictly from each algorithm's activation timestamp forward, alongside all-time performance, so every algo's ROI/W-L record is attributable.

## Forbidden Actions (summary)

- Modifying evaluator code, tests' golden baselines, or window declarations outside a reviewed PR.
- Promoting anything automatically, including "temporarily" or "to test".
- Deleting or rewriting ledger rows, dossiers, or holdout results.
- Drawing conclusions from segments with n < 30 (report them, label them inconclusive).
- Adding dependencies, services, or API usage not already present.
- Running cycles outside the effort budget or overlapping another running study (shared lock is mandatory).
