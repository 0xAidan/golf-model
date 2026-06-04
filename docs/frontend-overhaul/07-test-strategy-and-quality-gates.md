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
```bash
cd frontend && npm run screenshots:matrix
```
Output: `docs/screenshots/ui-overhaul-v2/`

## Manual parity checklist
- [ ] Live / Upcoming / Past mode switch on `/`
- [ ] Book filter + min edge on `/matchups`
- [ ] Player select → spotlight
- [ ] Lab lane fallback banner on `/lab`
- [ ] Grading source toggle on `/grading`
- [ ] Past gate on `/matchups`

## Accessibility
- Keyboard: tab through segment tabs, activate with Enter
- Future: `@axe-core/playwright` in CI

## Anti-shortcut gates
1. Visual evidence gate — screenshots attached
2. Functional parity gate — checklist signed off
3. Rankings gate — tests green
4. Interaction gate — no drag handles in cockpit
5. Build gate — typecheck/test/build pass
6. Claim integrity — no "done" without evidence packet
