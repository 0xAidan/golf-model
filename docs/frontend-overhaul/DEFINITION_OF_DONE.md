# Definition of Done (auditable)

Mark complete only when **every** item is checked with evidence linked in the PR.

- [ ] All core routes have before/after screenshots at 375 and 1280 in dark and light themes
- [ ] UI is materially different and more polished on `/`, `/matchups`, `/players`, `/lab`
- [ ] Draggable resize handles removed from cockpit production UX
- [ ] Upcoming rankings table uses model-centric columns (`#`, Composite, Form, Course, Mom., SG Traj)
- [ ] Live rankings table uses movement columns (Model now, Model Δ, Pos, Pos Δ, To par, Composite)
- [ ] `prediction-board.test.ts` and `cockpit-columns.test.ts` pass
- [ ] Functional parity checklist in [07-test-strategy-and-quality-gates.md](./07-test-strategy-and-quality-gates.md) passes
- [ ] `npm run typecheck`, `npm run test`, `npm run build` pass
- [ ] Python test suite passes (no backend regressions from touched paths)
- [ ] Hydration fallback banner appears when upcoming falls back to live section
- [ ] PR includes evidence packet index and rollback notes
- [ ] No unresolved critical UX or runtime regressions

**Blocked if any item lacks evidence.** "Looks fine locally" is not acceptable.
