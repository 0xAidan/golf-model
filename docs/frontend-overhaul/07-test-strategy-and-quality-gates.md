# 07 — Test Strategy and Quality Gates

## Automated (required before merge)

```bash
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
python3 -m pytest tests/ -v --tb=short
```

## Rankings-specific tests
- `frontend/src/lib/cockpit-columns.test.ts` — column header contract
- `frontend/src/lib/prediction-board.test.ts` — hydration section + upcoming vs live board
- `frontend/src/pages/prediction-workspace-page.test.tsx` — live vs upcoming UI

## Visual evidence (required before "done")

V2 (historical):
```bash
cd frontend && npm run screenshots:matrix
```
Output: `docs/screenshots/ui-overhaul-v2/`

V3 (Monitoring — CI `frontend-visual-diff`):
```bash
cd frontend && npm run build
SCREENSHOT_MATRIX_VERSION=v3 SCREENSHOT_BASE_URL=http://127.0.0.1:8000 npm run screenshots:matrix:v3
```
Output: `docs/screenshots/ui-overhaul-v3/` (60 PNGs; see [09-evidence-packet-index.md](./09-evidence-packet-index.md))

## Grading weekly checklist (+EV verification)

Use before calling grading “trusted” for the week:

1. **Backend:** `python3 -m pytest tests/test_learning.py tests/test_grading_integration.py -q` — all green; integration test confirms +EV picks persist and score.  
2. **Frontend:** `cd frontend && npm run test -- grading-trust legacy-routes fixtures.snapshot` — trust strip, ungraded banner, fixtures stable.  
3. **UI `/grading`:** Trust strip shows **Last graded**, **+EV picks**, **Ungraded +EV**; banner absent when ungraded count is 0.  
4. **Source toggle:** Dashboard vs Lab refetches history (`grading-source-*` test IDs).  
5. **Expanded rows:** Every graded pick in `HeroDataGrid` has positive EV; no negative-EV rows in history tables.  
6. **Docs:** See [14-grading-trust-contract.md](./14-grading-trust-contract.md) for policy and auto-grade notes.

## Manual parity checklist
- [ ] Live / Upcoming / Past mode switch on `/`
- [ ] Book filter + min edge on `/matchups` (Full picks tab on `/`)
- [ ] Player select → spotlight
- [ ] Lab lane fallback banner on `/lab`
- [ ] Grading trust strip + source toggle on `/grading`
- [ ] Team event notice on dashboard when `event_format=team`
- [ ] Past gate on replay / full picks

## Accessibility
- Keyboard: tab through segment tabs, activate with Enter; MonitoringShell drawer (see `monitoring-shell-drawer-a11y.test.tsx`)
- CI: `frontend-a11y` — Playwright + `@axe-core/playwright` on `/` and `/lab` (critical violations = 0)

## Anti-shortcut gates
1. Visual evidence gate — screenshots attached
2. Functional parity gate — checklist signed off
3. Rankings gate — tests green
4. Interaction gate — no drag handles in cockpit
5. Build gate — typecheck/test/build pass
6. Claim integrity — no "done" without evidence packet
