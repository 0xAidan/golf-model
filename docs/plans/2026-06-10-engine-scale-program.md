# Engine Scale Program — Execution Orchestration

**Created:** 2026-06-10  
**Status:** Planning / Wave 0  
**Goal:** Move operator vision from ~60% → ~90% via unified command center, champion/challenger tracks with promotion, field-complete player intelligence, eval platform, and engine-grade platform hardening.

**Canonical context:** `docs/AGENTS_KNOWLEDGE.md`  
**Prior UI baseline:** `docs/frontend-overhaul/DEFINITION_OF_DONE.md` (Monitoring V3 largely complete — this program is reimagination + unification, not theme refresh)

---

## How to execute (recommended)

Do **not** run one agent on the entire program. Use this sequence:

| Step | What | Mode | Output |
|------|------|------|--------|
| **0** | Master plan | Planning only | This doc updated + `WAVE_BACKLOG.md` (agent fills) |
| **1** | Wave 1 — Foundation | Agent + PR | Track registry, P0 fixes, minimal compare UI |
| **2** | Wave 2 — Players + promotion MVP | Parallel agents → 1 PR | Field player UX + promote/rollback API/UI |
| **3** | Wave 3 — Eval platform + algo challengers | Parallel agents → 1 PR | Validity dashboard, shadow challengers |
| **4** | Wave 4 — Engine + evidence | Agent + PR | Perf, ops, screenshot matrix, DoD packet |

**Branch strategy:** `program/engine-scale-wave-N` off `main`; one PR per wave; merge only when CI green + evidence linked in PR body.

**Parallelism:** Within a wave, up to 3 agents with **file ownership** (see `docs/plans/engine-scale/FILE_OWNERSHIP.md` after Wave 0 plan). Never two agents on the same file.

**Human gates:** You approve Wave 0 plan → Wave 1 → Wave 2 → … Promotion to champion always requires explicit approval (even if gates pass).

---

## Wave 0 — Planning (Fable or Opus, Planning mode)

Paste: `docs/plans/engine-scale/PROMPT_WAVE_0_PLANNING.md`

Deliverables the planner must write into the repo:

1. `docs/plans/engine-scale/WAVE_BACKLOG.md` — P0/P1/P2, dependencies
2. `docs/plans/engine-scale/FILE_OWNERSHIP.md` — agent boundaries
3. `docs/plans/engine-scale/TRACK_MODEL_SPEC.md` — champion/challenger/promotion/rollback
4. `docs/plans/engine-scale/EVAL_PLATFORM_SPEC.md` — metrics, APIs, UI placement
5. `docs/plans/engine-scale/PLAYER_FIELD_SPEC.md` — every-player UX + APIs
6. Update this file’s wave tables with concrete file lists and acceptance tests

**Stop rule:** No implementation commits in Wave 0 except these markdown specs (optional: empty scaffold routes behind feature flag — only if planner recommends).

---

## Wave 1 — Foundation (execute after Wave 0 approval)

**Theme:** P0 defects + track model in code + minimal “see both tracks” UI.

Typical scope (planner finalizes):

- Close P0 items from `docs/recovery_defect_register.md`
- Champion/challenger config registry (single source of truth; env overrides documented)
- Snapshot/API provenance fields: `model_track`, `model_variant`, `config_hash` on rows where missing
- Minimal unified compare: same event, two tracks (ranks/edges), read-only
- Tests: track parity, ab-report pairing, grading pick_source unchanged semantics

Paste per agent: `docs/plans/engine-scale/PROMPT_WAVE_1_*.md` (created after Wave 0)

**Acceptance:** All P0 closed or explicitly deferred with ticket; pytest + frontend CI green; compare UI screenshot at 1280 dark.

---

## Wave 2 — Field players + promotion MVP

**Theme:** Every player in the field is useful; challenger can promote to champion.

Typical scope:

- Field list + search + compare; drawer/full page; upcoming/live/completed layouts
- Promotion workflow UI + API (propose → eval snapshot → approve → apply → rollback)
- Wire to `LAB_PROMOTION_GATES.md`; human approve step mandatory

**Parallel agents:**

| Agent | Owns | Prompt file |
|-------|------|-------------|
| Player UX | `frontend/src/pages/*player*`, profile components | `PROMPT_WAVE_2_PLAYERS.md` |
| Promotion | registry, routes, promotion API | `PROMPT_WAVE_2_PROMOTION.md` |

Integration agent merges + runs full CI + screenshot matrix delta.

---

## Wave 3 — Eval platform + algorithm challengers

**Theme:** Prove Lab vs Dashboard (and post-promotion history) inside the product.

Typical scope:

- Eval hub (planner picks route — research hub extension or `/research/track-compare`)
- Per-track ROI, hit rate, Brier, n, overlap, edge distribution, CLV where available
- Challenger algo experiments in shadow lane only; walk-forward proof before promotion candidate

**Parallel agents:**

| Agent | Owns | Prompt file |
|-------|------|-------------|
| Eval UI + API | research routes, eval pages | `PROMPT_WAVE_3_EVAL.md` |
| Model/algo | `backtester/`, `src/value.py`, lab config | `PROMPT_WAVE_3_MODEL.md` |

---

## Wave 4 — Engine grade + 90% DoD

**Theme:** Hobby → engine — perf, observability, deploy reliability, evidence packet.

- Live-refresh + lab lane soak checklist
- Bundle budget, a11y, visual-diff baseline update if UI changed materially
- `docs/plans/engine-scale/DEFINITION_OF_DONE.md` — all items checked with links

Paste: `docs/plans/engine-scale/PROMPT_WAVE_4_ENGINE.md`

---

## CI merge gate (every PR)

```bash
export PATH="$HOME/.local/bin:$PATH"
python3 -m pytest tests/ -v --tb=short
cd frontend && npm run typecheck && npm run test && npm run build && npm run bundle:budget
```

Optional before merge: `npm run screenshots:matrix:v3` if visual program changed.

---

## Promotion policy (non-negotiable)

1. Challenger runs in parallel lane until promoted.
2. Promotion requires: walk-forward/holdout gates (`LAB_PROMOTION_GATES.md`), grading segment review, rollback config snapshot.
3. Dashboard champion switch is auditable (who/when/why) and reversible in one action.
4. No silent `.env` or production config change without PR + deploy note.

---

## Related docs to read before any wave

- `docs/research/LAB_PROMOTION_GATES.md`
- `docs/research/LAB_EXPERIMENT_BASELINE.md`
- `docs/frontend-overhaul/14-grading-trust-contract.md`
- `docs/recovery_defect_register.md`
- `docs/frontend-overhaul/08-rollout-and-rollback-plan.md`
