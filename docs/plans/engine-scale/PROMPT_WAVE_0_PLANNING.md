# Wave 0 — Master planning prompt (paste into Fable / Agent, Planning mode)

```
MODE: PLANNING ONLY — Do not implement product code. You may only add/update markdown under docs/plans/engine-scale/ and edit docs/plans/2026-06-10-engine-scale-program.md.

Read docs/AGENTS_KNOWLEDGE.md fully first.

## Mission
Produce an auditable master plan to move golf-model from ~60% → ~90% operator vision:
- Unified command center (combine Lab + Dashboard UX if superior) with clear champion vs challenger provenance
- Challenger (Lab) with promote-to-champion workflow + rollback
- Eval platform proving track validity in the product (you choose best UI/API design)
- Field-complete player intelligence (every entrant; upcoming/live/completed; all stat dimensions)
- P0/P1 defect burn-down
- Algorithm improvements allowed when walk-forward + promotion gates prove benefit
- Engine-grade platform (tests, CI, deploy, observability)

## Operator decisions (fixed)
- Improve all major workflows materially
- Lab + Dashboard may unify if diffs remain visible
- Lab = challenger, Dashboard = champion; promotion is a product feature
- Full technical scope: APIs, schema, workers, models — justify each change
- You choose eval UI placement; justify in EVAL_PLATFORM_SPEC.md

## Deliverables (write these files in the repo)
1. docs/plans/engine-scale/WAVE_BACKLOG.md — P0/P1/P2, effort, dependencies, wave assignment
2. docs/plans/engine-scale/FILE_OWNERSHIP.md — parallel agent file boundaries
3. docs/plans/engine-scale/TRACK_MODEL_SPEC.md — data model, APIs, promotion/rollback, pick_source semantics
4. docs/plans/engine-scale/EVAL_PLATFORM_SPEC.md — metrics, routes, API extensions (ab-report etc.)
5. docs/plans/engine-scale/PLAYER_FIELD_SPEC.md — UX, pagination, APIs, perf budget
6. docs/plans/engine-scale/DEFINITION_OF_DONE.md — 90% checklist with evidence types
7. Update docs/plans/2026-06-10-engine-scale-program.md wave tables with concrete scopes
8. Create stub prompt files: PROMPT_WAVE_1_FOUNDATION.md, PROMPT_WAVE_2_PLAYERS.md, PROMPT_WAVE_2_PROMOTION.md, PROMPT_WAVE_3_EVAL.md, PROMPT_WAVE_3_MODEL.md, PROMPT_WAVE_4_ENGINE.md (each ready to paste for execution agents)

## Survey requirements (cite in specs)
- docs/frontend-overhaul/*, docs/frontend-rebuild/*
- docs/research/LAB_*, matchup tuning summaries, pair_matchup_phase0_audit
- docs/recovery_defect_register.md, PROJECT_AUDIT_2026.md
- output/research/ artifacts, ab_reports
- tests/ and frontend tests, .github/workflows/ci.yml
- backtester/dashboard_runtime.py, live-refresh worker, market_prediction_rows sections

## Anti-shortcuts
- No theme-only UI plan
- No conflating tracks without provenance fields
- No algo promotion without gates + rollback
- No bug rows without file path + repro
- No "done" without test + screenshot evidence per DoD item

## End with
- Wave 1 approval checklist (what human says "go" to)
- Recommended parallel agent count per wave
- Explicit OUT OF SCOPE for this program
```
