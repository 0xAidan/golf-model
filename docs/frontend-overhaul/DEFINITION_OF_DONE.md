# Definition of Done (auditable)

Mark complete only when **every** item is checked with evidence linked in the PR.

- [x] All core routes have before/after screenshots at 375 and 1280 in dark and light themes — [ui-overhaul-v2](../screenshots/ui-overhaul-v2/README.md) (40 PNGs)
- [x] UI is materially different and more polished on `/`, `/matchups`, `/players`, `/lab` — TerminalPageHeader + KPI strips on picks/players/lab; cockpit grid on dashboard
- [x] Draggable resize handles removed from cockpit production UX — `react-resizable-panels` removed; dead CSS deleted
- [x] Upcoming rankings table uses model-centric columns (`#`, Composite, Form, Course, Mom., SG Traj)
- [x] Live rankings table uses movement columns (Model now, Model Δ, Pos, Pos Δ, To par, Composite)
- [x] `prediction-board.test.ts` and `cockpit-columns.test.ts` pass — 106 frontend tests green
- [x] Functional parity checklist in [07-test-strategy-and-quality-gates.md](./07-test-strategy-and-quality-gates.md) passes — post-deploy soak logged
- [x] `npm run typecheck`, `npm run test`, `npm run build` pass
- [x] Python test suite passes — 481 passed (2026-06-04)
- [x] Hydration fallback banner appears when upcoming falls back to live section — tested + `data-testid="hydration-fallback-banner"`
- [x] PR includes evidence packet index and rollback notes — [09-evidence-packet-index.md](./09-evidence-packet-index.md)
- [x] No unresolved critical UX or runtime regressions — soak test on golf.ancc.blog

**Blocked if any item lacks evidence.** "Looks fine locally" is not acceptable.
