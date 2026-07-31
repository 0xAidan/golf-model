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

| Item | Confirmed by | Date | Notes |
|------|--------------|------|-------|
| Required checks enabled | _pending_ | | |
| No direct pushes to `main` | _pending_ | | |
| Approval required for UI/baseline | _pending_ | | |

## PR checklist

| PR | Title | Code merged | Acceptance notes |
|----|-------|-------------|------------------|
| 0A | Restore CI and merge enforcement | pending | Workflow validator + e2e wired; branch protection external |
| 0B | API responsiveness | pending | |
| 0 | Domain + baseline | pending | |
| 1 | SPA delivery / BrowserRouter | pending | |
| 1B | Worker runtime | pending | |
| 2–13 | Remaining recovery | pending | |

## Evidence links

- Plan: operator-site-recovery (Cursor plan)
- CI validator: `scripts/validate_ci_workflow.py`
- Expected jobs: `scripts/ci/expected_jobs.json`
