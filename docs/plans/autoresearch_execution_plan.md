# Autoresearch Execution Plan — Karpathy-Style Research Loop

**Status:** Authoritative plan (supersedes overlapping sections of `docs/autoresearch/SPEC_V2.md` — see §6)
**Created:** 2026-08-23
**Approved by:** Operator via grilling session 2026-08-23 (decision record in §5)

---

## 1. Mission

Build an autonomous research loop modeled on [karpathy/autoresearch](https://github.com/karpathy/autoresearch) (verified real; architecture confirmed: human-iterated `program.md`, frozen evaluator `prepare.py`, agent-mutated `train.py`, fixed budget, single metric `val_bpb`, append-only experiment log). Adapted honestly to sports betting:

- A human-edited **PROGRAM.md** is the only steering surface.
- The evaluator (`backtester/strategy.py` replay + `pit_stats.py` + grading) is FROZEN — pinned by characterization tests and the CI frozen-zone guard.
- One versioned mutable config artifact is all the loop mutates.
- Every experiment runs under a fixed budget on a frozen window with cached PIT features.
- One primary metric decides keep/discard mechanically; both outcomes always logged to an append-only ledger.
- Nothing auto-promotes: winners become promotion-ready dossiers; humans click Promote-to-Lab; Lab→Main requires typed confirmation.
- Tier 2 (new code/features) reaches the operator as alerts + one-click draft-PR creation. No unattended GitHub writes.

## 2. What already exists (~70% of the scaffold)

| Pillar | Existing asset | State |
|--------|---------------|-------|
| Program file | `docs/research/research_program.md`, `KARPATHY_AGENT_RUNBOOK.md`; root `program.md` pointer | Broken: `validate_contract_documents()` demands sections in root `program.md` that were removed → checkpoint eval lane exits 1 |
| Frozen evaluator | `backtester/strategy.py` (906 ln), `pit_models.py`, `pit_stats.py`, `weighted_walkforward.py`, `checkpoint_replay.py`, `research_lab/canonical.py` | Solid but unpinned: no characterization tests; versions exist (`CHECKPOINT_SCRIPT_EVALUATOR_VERSION=1`, `EVAL_CONTRACT_VERSION_WALK_FORWARD=2`) |
| Mutable surface | `autoresearch/strategy_config.json` + whitelist validation + ranges in `param_space.py` | Flat file, no schema_version/ranges/segments; dead keys in `cycle_config.json` |
| Fixed budget | `AUTORESEARCH_MAX_TRIAL_SECONDS` (3600s default), per-invocation trial counts | No cumulative nightly budget or effort presets |
| Primary metric | THREE competing scalars (blended_score / weighted_roi_pct / MO vector) | Must collapse to ONE guarded score (matchup OOS ROI/bet vs own collected lines) |
| Ledger | `output/research/ledger.jsonl` via `research_lab/ledger.py` (fcntl lock) | Only Optuna + CLI write it; research_cycle engine does not |
| Orchestrator | `golf-agent.service` → `workers/research_agent.py` 6-thread daemon + dashboard optimizer_runtime + Simple Mode tuner | Three overlapping loops; legacy thread auto-promotes unguardrailed |
| Promotion rails | `track_configs` provenance + gates + rollback (`src/track_registry.py`), charter gates in `model_registry.evaluate_live_promotion_gates` | Good; needs lab-swap click flow + eras timeline |
| Holdout | `run_autoresearch_holdout.py` trailing-window script | NOT sealed — window drifts at call time |

Git archaeology: prior autoresearch arc (PRs #10, #20–26, Feb–Mar 2026) and engine-scale waves (#147–152, Jun 2026) are all merged to main; zero Revert commits in history; no tags. Recovery tooling verified present and idempotent: `scripts/import_season_cards.py` (dry-run default), `scripts/hydrate_season_2026.py`, `scripts/reconcile_event_picks.py`, `data/golf.db.malformed_20260816.gz` (1.43 GB SQLite image).

## 3. Empirical data inventory (DB-verified 2026-08-22/23)

| Source | Count | Notes |
|---|---|---|
| `rounds` | 33,848 rows | Round-level SG components (sg_total/ott/app/arg/putt/t2g). Finest granularity Data Golf returns at this tier. |
| `market_prediction_rows` (matchup) | **330,563 rows** | Every-book matchup line captures, **11 books**, 17 events, 2026-06-14 → 2026-08-23. This is the backtest pricing source. |
| `picks` + `pick_outcomes` | 1,900 graded matchup picks / 18 tournaments | cockpit 1,251, lab_sandbox 1,070. Grading spine for outcomes. |
| `historical_predictions` | 19,274 | DG archived pre-tournament predictions, 2025–2026. |
| `historical_odds` | 93,189 | SYNTHETIC DG-model odds only (books DG-Base/DG-CH). NOT book lines. |
| `historical_matchup_odds` | 0 | Endpoint wired but never populated; not needed given own-capture. |
| `pit_rolling_stats` | 52,584 | Windows 8/12/16/20/24/50; 46 events (2025) currently built. |
| `pit_course_stats` | 56 | Effectively empty (1 event); known gap, not load-bearing for matchup lane. |
| `hole_scores`/`hole_difficulty`/`player_hole_history` | 0/0/0 | Schema-only; hole-level data definitively unavailable at current tier. Kept forward-compatible. |

**Consequence:** the research score = flat-unit ROI per bet on MATCHUP bets priced against the operator's OWN collected book lines (from `market_prediction_rows` pre-tournament snapshots), outcomes from the existing grading spine. Coverage grows weekly; until n≥300 in the primary window, cycles run report-only.

## 4. Measured runtime baseline

- Warm `replay_event`: ~40 ms/event (2025 data); dominant cost = PIT sub-score computation ~24 ms/event.
- Full walk-forward 2025 (46 events, candidate+baseline): ~3.6 s.
- With cached PIT sub-scores + precomputed baseline: experiment ≈ 1.5–2 s ⇒ ~100 trials in ~4 min. Budget target ≤10 min/experiment-cycle is achievable; benchmarks committed in PR4.

## 5. Grilling decision record (2026-08-23, approved by operator)

| # | Question | Decision |
|---|----------|----------|
| 1 | Primary metric early weeks | Matchup flat-unit ROI vs operator's OWN collected book lines; report-only until n≥300 |
| 2 | Window split (~17–18 events today) | Search 13 / confirmation 3 (rolling most-recent) / sealed holdout 2 |
| 3 | Promotion autonomy | NOTHING auto-promotes. Loop stages promotion-ready dossiers; Promote-to-Lab = confirm modal with diff; Lab→Main typed confirmation; per-algo "eras" ROI/W-L tracking from activation moment + all-time |
| 4 | Notifications | Telegram high-signal only (promotable find / holdout result / crash / ingestion failure) + weekly digest; everything browsable in dashboard |
| 5 | Loop consolidation | ONE loop replaces Simple Mode tuner AND advanced optimizer (old paths removed after new UI ships) |
| 6 | Compute | Standard ≈60 min/night (~100 trials cap); Light ~20 min / Max ~3 h presets; effort dial IN THE DASHBOARD |
| 7 | Tier 2 | Alert + one-click draft PR creation. No unattended GitHub writes |
| 8 | Merge pace | All PRs merge as CI passes overnight; NO production service restarts while unattended — deploy is a morning step |

## 6. SPEC_V2 supersession map

| SPEC_V2 section | Disposition |
|---|---|
| Canonical evaluation, EvaluationResult, contract versioning | **Adopted** (already built) |
| Optuna MO/scalar engines | **Adopted** as search machinery inside the new orchestrator's nightly cycle |
| Append-only ledger.jsonl | **Adopted**, extended: research_cycle engine now writes too; evaluator_fingerprint added |
| Pareto view UI todo | **Replaced** — operator view pivots to promote-flow + eras timeline instead |
| v1 theory engine retirement intent | **Adopted** via full consolidation (PR9) |
| cycle_config cleanup | **Adopted** (PR3) |
| Two-daemon consolidation intent | **Extended**: three loops → one orchestrator (PR6/PR9) |
| Checkpoint pilot lane | **Kept** for pilot event; sealed-holdout mechanism added beside it |

## 7. Phases (PRs), files, tests, Definition of Done

### PR1 — This document. ✅ DoD: this file exists and is cited by later PRs.

### PR2 — PROGRAM.md + sealed holdout + evaluator pinning
Files: `docs/research/PROGRAM.md` (new, contains required markers Scope/Immutable Evaluator Rule/Objective/Loop Protocol/Promotion Rule), `backtester/autoresearch_config.py` (repoint PROGRAM_PATH, keep marker enforcement), root `program.md` stays a pointer, `docs/research/sealed_holdout_events.json` (2 oldest clean completed events), `scripts/run_autoresearch_sealed_holdout.py` (operator-invoked only; appends permanently), `src/config.py`-adjacent central tolerance constants (added to autoresearch settings layer, not frozen-zone files), tests `tests/test_evaluator_characterization.py` (golden metrics over replay_event / evaluate_weighted_walkforward / compute_blended_score on fixture DBs; pin set-order nondeterminism, date.today injection, guardrail-mode env), `tests/test_program_contract_docs.py`, `tests/test_sealed_holdout.py`. Evaluator fingerprint helper in `backtester/research_lab/canonical.py` stamped as `evaluator_fingerprint` in ledger rows.
DoD: `validate_contract_documents()` passes; characterization suite fails if evaluator behavior changes without version bump; sealed events excluded from search/confirmation loaders; ledger rows carry fingerprint+version.

### PR3 — Versioned strategy-config artifact
Files: new `backtester/strategy_config_artifact.py` (schema_version=2, declared `ranges` block mirroring `param_space.py` bounds, segment overrides whitelist, load/validate/diff/hash/migrate-from-flat-file), `autoresearch/strategy_config.json` upgraded, dead `cycle_config.json` keys removed (keep `max_candidates_per_cycle`), tests mirroring `test_autoresearch_config_schema.py`.
DoD: artifact round-trips; unknown/out-of-range keys rejected; diff produces human-readable change list; old flat file migrates cleanly.

### PR4 — Fast-tier runner + budget + benchmarks
Files: new `backtester/fast_tier.py` (per-window cache of strategy-independent PIT sub-score dicts; evaluate candidates through unchanged frozen blend; thread `precomputed_baseline` through Optuna objective), benchmark script `scripts/benchmark_autoresearch_tiers.py` writing `output/research/benchmarks/*.json` (committed), window-selection helper shared with PR5/PR7.
DoD: measured fast-tier experiment time committed; >10 min ⇒ documented trim proposal rather than silent slowdown; determinism fixes confined to inputs (sorted iteration) — evaluator untouched.

### PR5 — Backtest-grade odds/outcome ledger from our own capture
Files: builder module (idempotent) deriving per-event pre-tournament book lines from `market_prediction_rows` (sections upcoming/pre-teeoff, all books) joined with outcomes from `picks`/`pick_outcomes`/`rounds`; new research table via `src/db.py` init_db conventions; incremental PIT rebuild wrapper; weekly DG refresh wrapper around resume-safe `run_full_backfill`; honesty doc section (round-level SG confirmed; hole-level unavailable).
DoD: builder rerun = no-op (INSERT OR IGNORE semantics); coverage stats queryable; replay can price matchups against captured lines end-to-end on ≥13-event search window.

### PR6 — Orchestrator daemon/timers + notifications
Files: `workers/autoresearch_orchestrator.py` (nightly bounded by effort preset read each cycle: Light≈20 min / Standard≈60 min ≈100 trials / Max≈3 h; weekly deep cycle ingestion→PIT→search; fcntl lock reusing live-refresh conventions; heartbeat JSON; crash recovery from ledger state), systemd units `deploy/systemd/golf-autoresearch.timer|.service`, Telegram high-signal alerts (reuse `src/telegram_alerts.py`) + weekly digest; retire legacy auto-promotion writes in `workers/research_agent.py` ExperimentRunner/Optimizer threads.
DoD: two consecutive nightly cycles produce ledger rows; lock prevents overlap with manual studies; crash mid-cycle resumes; no service restarts performed by the program itself.

### PR7 — Tier 1 loop wired end-to-end
Files: mutation engine within declared ranges → fast tier → mechanical keep/discard on the single score → survivors evaluated on 3-event rolling confirmation set → passers staged as promotion-ready dossiers (+alert); research_cycle engine routed through ledger; multiplicity counters (trials-per-lineage) recorded.
DoD: full dry-run cycle produces: N trials logged, ≤K keeps, confirmation verdicts, zero promotions executed automatically, dossier artifacts written.

### PR8 — Tier 2 hypothesis pipeline
Files: residual/segment signal detector (ledger + graded picks), dossier emission, API endpoint + button wiring for one-click draft PR creation via `gh` (branch + implementation sketch + tests + backtest evidence), explicit "no unattended writes" guard (endpoint requires authenticated operator session/action).
DoD: detector produces ranked signals table; simulated signal produces a dossier; PR creation path tested with mocked gh.

### PR9 — Operator view + consolidation cutover
Files: extend autoresearch tab: cycle status/ETA, ledger browser (read-only `/api/autoresearch/ledger`), Promote-to-Lab confirm modal (config diff + evidence), Research→Lab→Main ladder, algorithm-eras timeline (per-algo ROI/W-L from activation timestamp + all-time), effort dial wired to settings; THEN remove Simple Mode tuner + advanced optimizer endpoints/UI/tests (cutover only after new UI ships).
DoD: operator can run the whole ladder from the UI; frontend checks green; old paths gone post-cutover.

### PR10 — Hardening
Full test coverage of every new module; full pytest suite green; ruff clean (known lints left alone); frontend checks if touched; update `docs/AGENTS_KNOWLEDGE.md` (Section 9, tables, env vars); author `docs/runbooks/autoresearch-operations.md` (start/stop, holdout opening, promotion/rollback drill, failure triage, deploy steps incl. timer units).
DoD: CI fully green; runbook reviewed against actual commands.

## 8. Hard constraints

- No new paid APIs/services. Missing capability documented, designed around.
- Live behavior untouched: predictions, grading, live-refresh worker, cockpit/lab split. All ~493 existing tests pass on every PR.
- python3 only; PATH includes ~/.local/bin; SQLite only.
- Frozen-zone paths modified only in separate reviewed PRs that bump `evaluator_version` and force re-baselining (CI `frozen-zone-guard` enforces).
- Charter stopping rules/go-live gates apply throughout; production swaps need typed human confirmation.

## 9. Honest limitations

1. Hole-level/shot-level data unavailable at current Data Golf tier — evidenced; schema slots finer granularity later.
2. Own-collected lines cover ~17 events/~10 weeks today; power grows weekly; report-only until n≥300.
3. Multiplicity inflates best-seen scores; confirmation window mitigates, not eliminates — dossiers carry trial counts and deflation caveats.
4. Positive research scores are lab-track evidence only; charter gates decide anything further.
