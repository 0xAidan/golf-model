# Frontend Recovery — Acceptance Log

Status: **in progress** (Operator Site Recovery program)

This file records external gates that cannot be delivered by code alone, plus
acceptance checkpoints for each recovery PR.

## Branch protection (external — operator action required)

Code PR **0A** restores workflow YAML so GitHub creates real CI jobs. That alone
does **not** protect `main`.

**Operator must configure GitHub branch protection / rulesets after the first
green protected-main candidate:**

1. Require status checks to pass before merging to `main`
2. Required checks must include at least:
   - `validate-workflow`
   - `test` (all matrix cells)
   - `lint` (all matrix cells)
   - `frontend`
   - `backend-smoke`
   - `frontend-bundle-budget`
   - `frontend-a11y`
   - `frontend-e2e`
   - `frontend-visual-diff`
   - `frozen-zone-guard` (on pull requests)
3. Disallow direct pushes to `main`
4. Require at least one approving review for UI / visual-baseline changes

**Current state (2026-07-31):** not yet confirmed in GitHub. Do not treat later
implementation PRs as mergeable while checks are absent, red, or optional.

Record confirmation here when done:

| Protection | Required state | Confirmed by | Date | Notes |
|------------|----------------|--------------|------|-------|
| Required checks | All checks listed above are required before merge | _pending_ | | |
| Direct pushes | Blocked for `main` | _pending_ | | |
| Reviews | One approving review required for UI/baseline changes | _pending_ | | |
| Force pushes | Blocked for `main` | _pending_ | | |

## PR checklist

| PR | Title | Code merged | Acceptance notes |
|----|-------|-------------|------------------|
| 0A | Restore CI and merge enforcement | pending | Workflow validator + e2e wired; branch protection external |
| 0B | API responsiveness | pending | Cached health; season aggregates default |
| 0 | Domain + measurable baseline | pending | CONTEXT, ADR, baseline schema, superseded prior gates |
| 1 | SPA delivery / BrowserRouter | pending | |
| 1B | Worker runtime | pending | |
| 2 | Sentry observability | pending | |
| 3 | Operator read model | pending | |
| 4 | Player API | pending | |
| 5 | Data provider + preview | pending | |
| 6 | Dark Dashboard prototype | pending | Operator visual approval gate |
| 7 | Dashboard + Lab workspaces | pending | No Champion→Challenger fallback |
| 8–9 | Compare + Players | pending | Current-event Compare only |
| 10 | Results | pending | Separate track evidence; no winner |
| 11 | Eval + System; retire Legacy | pending | |
| 12 | Quality gates + cutover | pending | |
| 13 | Legacy cleanup | pending | |

## Evidence links

- Context: [`../../CONTEXT.md`](../../CONTEXT.md)
- Track isolation: [`../adr/0001-track-isolation.md`](../adr/0001-track-isolation.md)
- Baseline schema: [`baseline.json`](baseline.json)
- Plan: operator-site-recovery (Cursor plan; do not edit from implementation PRs)
- CI validator: `scripts/validate_ci_workflow.py`
- Expected jobs: `scripts/ci/expected_jobs.json`
