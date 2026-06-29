# Golf Model — Master Upgrade Plan Prompt (v5)

**Use this document:** Paste the fenced block below into a **Plan** agent chat to produce the full master plan.  
**Operator:** Solo. Desktop-first; mobile must work.  
**Target:** C- → A (trust, performance, analytics, UX — all equal P0).  
**Frozen:** Dashboard prediction models/algorithms — do not change pick logic or composite outputs.

**Prior work to merge:**
- Grading plan: `/root/.cursor/plans/fix_event_grading_56d76423.plan.md` (chat [ef4280d8](ef4280d8-558f-47f6-9eb4-cdc6d78c8dd0)) — audit landed vs TODO before coding
- Monitoring V3: `.cursor/plans/remaining_overhaul_items_5374a86c.plan.md` — gap analysis, not “already done”

**Project skills:** 65 skills vendored in `.cursor/skills/` from [awesome-cursor-skills](https://github.com/spencerpauly/awesome-cursor-skills). Wave gates below reference them by directory name.

---

## Skills map (waves → invoke these)

### Wave 0 — Reality audit
| Skill | Path | Use |
|-------|------|-----|
| `codebase-onboarding` | `.cursor/skills/codebase-onboarding/` | Parallel explore → architecture doc |
| `parallel-exploring` | `.cursor/skills/parallel-exploring/` | Fast multi-area codebase investigation |
| `api-smoke-testing` | `.cursor/skills/api-smoke-testing/` | Hit all FastAPI routes, report failures |
| `finding-dev-server-url` | `.cursor/skills/finding-dev-server-url/` | Locate :8000 / :5173 for local verify |
| `saving-workspace-context` | `.cursor/skills/saving-workspace-context/` | Persist audit findings to repo docs |
| `architecture-decision-records` | `.cursor/skills/architecture-decision-records/` | ADR for frozen zone + SWR redesign |
| **Also:** `ce-plan`, `verify-this` (cursor-team-kit / compound-engineering) |

### Wave 1 — Grading trust (grading plan PR1–3)
| Skill | Path | Use |
|-------|------|-----|
| `systematic-debugging` | `.cursor/skills/systematic-debugging/` | Reproduce grade failures |
| `incident-response` | `.cursor/skills/incident-response/` | Production recovery on VPS |
| `monitoring-terminal-errors` | `.cursor/skills/monitoring-terminal-errors/` | journalctl / worker crashes |
| `grinding-until-pass` | `.cursor/skills/grinding-until-pass/` | Until grading tests green |
| `writing-tests` | `.cursor/skills/writing-tests/` | Pending cell + grade mutation tests |
| **Also:** `verification`, `bugbot`, `review-security` |

### Wave 2 — Performance + freshness UX redesign
| Skill | Path | Use |
|-------|------|-----|
| `profiling-performance` | `.cursor/skills/profiling-performance/` | Browser CPU profile on poll tick |
| `auditing-performance` | `.cursor/skills/auditing-performance/` | Bundle, waterfalls, API p95 |
| `network-request-auditing` | `.cursor/skills/network-request-auditing/` | Snapshot/dashboard duplicate/slow calls |
| `detecting-port-conflicts` | `.cursor/skills/detecting-port-conflicts/` | Dev server EADDRINUSE |
| `tailing-build-output` | `.cursor/skills/tailing-build-output/` | Frontend build warnings |
| `auto-type-checking` | `.cursor/skills/auto-type-checking/` | `npm run typecheck` after edits |
| **Also:** `react-best-practices`, `performance-optimizer` (Vercel plugin) |

### Wave 3 — Analytics workspace
| Skill | Path | Use |
|-------|------|-----|
| `database-design` | `.cursor/skills/database-design/` | Read-only aggregation schema (no model tables change) |
| `adding-api-docs` | `.cursor/skills/adding-api-docs/` | Document `/api/analytics/*` |
| `form-testing` | `.cursor/skills/form-testing/` | Filter toolbar valid/invalid states |
| **Also:** `shadcn` (plugin), `ce-plan` |

### Wave 4 — AAA UX unification
| Skill | Path | Use |
|-------|------|-----|
| `using-ui-stack` | `.cursor/skills/using-ui-stack/` | 8px grid, tokens, 5-state interactions |
| `visual-qa-testing` | `.cursor/skills/visual-qa-testing/` | Browser screenshots after route polish |
| `verifying-in-browser` | `.cursor/skills/verifying-in-browser/` | Dev server + side-by-side verify |
| `accessibility-auditing` | `.cursor/skills/accessibility-auditing/` | ARIA, tab order, labels |
| `responsive-testing` | `.cursor/skills/responsive-testing/` | Desktop + mobile breakpoints |
| `dark-mode-testing` | `.cursor/skills/dark-mode-testing/` | Light/dark token audit |
| `comparing-branches-visually` | `.cursor/skills/comparing-branches-visually/` | Before/after PR visuals |
| `screenshotting-changelog` | `.cursor/skills/screenshotting-changelog/` | PR evidence packet |
| `converting-css-to-tailwind` | `.cursor/skills/converting-css-to-tailwind/` | Legacy CSS cleanup only if needed |
| **Also:** `deslop`, `thermo-nuclear-code-quality-review` (cursor-team-kit) |

### Wave 5 — Guardrails & ship
| Skill | Path | Use |
|-------|------|-----|
| `adding-e2e-tests` | `.cursor/skills/adding-e2e-tests/` | Extend Playwright coverage |
| `recording-browser-flow-as-test` | `.cursor/skills/recording-browser-flow-as-test/` | Tab start + grade flow specs |
| `parallel-test-fixing` | `.cursor/skills/parallel-test-fixing/` | Multiple failing tests |
| `parallel-ci-triage` | `.cursor/skills/parallel-ci-triage/` | GitHub Actions failures |
| `parallel-code-review` | `.cursor/skills/parallel-code-review/` | Security/perf/correctness/readability |
| `reviewing-code` | `.cursor/skills/reviewing-code/` | PR review |
| `auditing-security` | `.cursor/skills/auditing-security/` | Analytics export + API |
| `babysitting-pr` | `.cursor/skills/babysitting-pr/` | Keep PR merge-ready |
| `creating-pr` | `.cursor/skills/creating-pr/` | Structured PR bodies |
| `writing-commit-messages` | `.cursor/skills/writing-commit-messages/` | Conventional commits |
| `grinding-until-pass` | `.cursor/skills/grinding-until-pass/` | CI green before merge |
| `setting-up-ci` | `.cursor/skills/setting-up-ci/` | Extend `.github/workflows/ci.yml` |
| `verifying-markdown-formatting` | `.cursor/skills/verifying-markdown-formatting/` | Plan + runbook docs |
| **Also:** `fix-ci`, `loop-on-ci`, `run-smoke-tests`, `make-pr-easy-to-review`, `review-and-ship`, `new-branch-and-pr` |

### Hard problems (optional)
| Skill | Path | Use |
|-------|------|-----|
| `best-of-n-solving` | `.cursor/skills/best-of-n-solving/` | Parallel worktrees for perf/SWR approaches |
| `suggesting-cursor-rules` | `.cursor/skills/suggesting-cursor-rules/` | Encode frozen zone as rule |
| `suggesting-cursor-hooks` | `.cursor/skills/suggesting-cursor-hooks/` | Auto lint/test on save |
| `building-skills-from-patterns` | `.cursor/skills/building-skills-from-patterns/` | New skills from repeated ops workflows |

### Out of scope for this program (do not invoke unless operator asks)
`adding-stripe`, `adding-auth`, `react-native-patterns`, `kubernetes-deploying`, `setting-up-terraform`, `adding-docker`, `seo-auditing`, `writing-copy`, `generating-images`, `adding-analytics` (PostHog), `adding-error-tracking` (Sentry) — not required for solo operator upgrade.

---

## Copy-paste prompt for Plan agent

```text
[CURSOR PROMPT START]

# ROLE
Principal Product Architect + Performance Engineer — **master plan only**, no implementation code.

**Site:** https://golf.ancc.blog/
**Operator:** Solo power user. Desktop-first; mobile must work (responsive, not parity).
**Target:** C- → A on trust, performance, analytics, UX — **all four pillars equal P0**.
**Vigilance:** No corners cut. Every claim falsifiable via `verify-this`.

---

# PROJECT SKILLS (MANDATORY)
Read `.cursor/skills/README.md`. **65 skills** vendored from https://github.com/spencerpauly/awesome-cursor-skills

At each wave gate, **read and follow** the SKILL.md files listed in `.cursor/plans/golf-model-master-upgrade-plan-prompt.md` (Skills map section). Also use cursor-team-kit (`verify-this`, `deslop`, `thermo-nuclear-code-quality-review`, `fix-ci`, `new-branch-and-pr`, `review-and-ship`) and Vercel plugin (`react-best-practices`, `performance-optimizer`, `shadcn`) where listed.

Do not improvise workflows when a project skill exists.

---

# OPERATOR REQUIREMENTS (BINDING)

## Performance — ALL triggers broken today
Fix slowness on: deploy first load, browser refresh, tab start/return, manual Refresh, Grade event.

### Per-trigger SLOs (verify-this each)
| Trigger | Interactive UI | Meaningful data | Must NOT happen |
|---------|----------------|-----------------|-----------------|
| Tab start (warm) | <1s | <500ms cache | Blank workspace 5min |
| Tab start (cold) | <2s | <3s | Full recompute blocking HTTP |
| Browser refresh | <2s | <3s cached | Query waterfall block |
| After deploy | <5s usable | <8s once | SSH to start worker |
| Refresh click | <200ms feedback | background | Frozen board |
| Grade click | <200ms feedback | ≤3min progress | 12s timeout; frozen UI |

## Stale-while-revalidate — YES, REDESIGN (current impl is clunky)
Operator accepts cached data instantly if freshness UX is **clean**.

Fix known issues:
- `live-snapshot-provider.tsx`: `displaySnapshot = snapshot` ignores `warmSnapshot` during fetch
- `warm-snapshot.ts`: sessionStorage only — weak on tab start
- `app.py`: on-demand `generate_snapshot_once()` when cache empty
- Banner soup: SnapshotChip + snapshotNotice + hydration banner + trust banner

Deliver **Freshness UX mini-spec**: state machine (Fresh|Updating|Stale|Offline|Error), single shell indicator, section shimmer, copy deck, migration map removing duplicate banners.

## Mobile
Desktop terminal density; mobile = drawer nav + scrollable panels + 44px targets.

---

# FROZEN ZONE — DO NOT TOUCH
Prediction models & dashboard pick outputs unchanged:
`src/models/*`, `src/value.py`, `src/matchup_value.py`, `src/matchups.py`, `src/kelly.py`, `src/portfolio.py`, `src/exposure.py`, `src/config.py` prediction weights, `run_predictions.py`, `golf_model_service.py` pick generation, `backtester/pit_models.py`, `backtester/strategy.py`, `dashboard_runtime.py` **compute** paths.

ALLOWED: serve/cache/UI, grading ops pipeline, read-only analytics APIs, query orchestration, freshness UX.

Plan must include Frozen Zone Contract + CI guard.

---

# PRIOR PLANS TO MERGE

## A) Grading — `/root/.cursor/plans/fix_event_grading_56d76423.plan.md`
Wave 0: audit landed (GRADE_TOURNAMENT_TIMEOUT_MS, to_thread, ops health, etc.) vs TODO.
Carry forward unimplemented PR1–PR3 items verbatim.

## B) Monitoring V3 — `.cursor/plans/remaining_overhaul_items_5374a86c.plan.md`
Reuse shell, LiveSnapshotProvider, HeroDataGrid. Gap-analyze vs operator C- rating.

---

# FOUR PILLARS (ALL P0)

## 1. TRUST & GRADING
Full grading plan + zero Pending + +EV-only preserved.

## 2. PERFORMANCE & LIVE DYNAMICS
Worker always warm; HTTP never blocks on full recompute; defer grading-season off `/` boot; IndexedDB warm cache; App.tsx decomposition; Grade/Refresh as background jobs.

**Skills:** profiling-performance, auditing-performance, network-request-auditing, react-best-practices, performance-optimizer

## 3. GRANULAR ANALYTICS (net-new)
Slice: book, player, event, season, market type, EV, confidence, lane, outcome, date range.
`/analytics` or unified `/results`; URL filters; KPI + group-by + ledger + drill-downs; `GET /api/analytics/summary`, `GET /api/analytics/picks`.

**Skills:** database-design, adding-api-docs, form-testing, shadcn

## 4. AAA UX
using-ui-stack; route scorecard ≥8/10; deslop; no legacy links; axe 0 critical.

**Skills:** visual-qa-testing, verifying-in-browser, accessibility-auditing, responsive-testing, dark-mode-testing, comparing-branches-visually, screenshotting-changelog

---

# WAVES
0 — Audit (codebase-onboarding, parallel-exploring, api-smoke-testing, verify-this, ADR)
1 — Grading trust (systematic-debugging, incident-response, grinding-until-pass, writing-tests)
2 — Perf + Freshness UX (profiling-performance, auditing-performance, network-request-auditing)
3 — Analytics MVP
4 — UX unification
5 — Guardrails (parallel-ci-triage, parallel-code-review, auditing-security, adding-e2e-tests, recording-browser-flow-as-test, babysitting-pr, creating-pr)

Each wave: goals, files, acceptance criteria, skills invoked, evidence, rollback.

---

# OUTPUT
Single markdown: TL;DR, Wave 0 audit tables, Freshness UX spec, merged waves, analytics spec, perf diagram (mermaid), PR queue 15–20, DoD checklist, risks, timeline.

No implementation code.

[CURSOR PROMPT END]
```
