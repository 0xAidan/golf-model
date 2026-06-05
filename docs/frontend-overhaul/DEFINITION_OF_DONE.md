# Definition of Done (auditable)

Mark complete only when **every** item is checked with evidence linked in the PR.

## Visual & layout
- [x] All core routes have before/after screenshots at 375 and 1280 in dark and light themes — [ui-overhaul-v2](../screenshots/ui-overhaul-v2/README.md) (40 PNGs)
- [x] Monitoring V3 screenshot matrix at 375, 1280, and 1920 (dark + light) — [ui-overhaul-v3](../screenshots/ui-overhaul-v3/README.md) (60 PNGs); capture via `npm run screenshots:matrix:v3`
- [x] Pre-overhaul baseline preserved — [ui-overhaul-v1](../screenshots/ui-overhaul-v1/README.md) @ commit `371d194`
- [x] UI is materially different and more polished on `/`, `/matchups`, `/players`, `/lab` — MonitoringShell + bento lanes; TerminalPageHeader on satellite routes
- [x] Draggable resize handles removed from cockpit production UX — `react-resizable-panels` removed; dead CSS deleted
- [x] Self-hosted fonts (Zodiak / Switzer / Fragment Mono); no CDN font requests — [12-deslop-checklist.md](./12-deslop-checklist.md) signed 2026-06-05

## Rankings & cockpit
- [x] Upcoming rankings table uses model-centric columns (`#`, Composite, Form, Course, Mom., SG Traj)
- [x] Live rankings table uses movement columns (Model now, Model Δ, Pos, Pos Δ, To par, Composite)
- [x] `prediction-board.test.ts` and `cockpit-columns.test.ts` pass
- [x] Hydration fallback banner appears when upcoming falls back to live section — `data-testid="hydration-fallback-banner"`

## Quality gates
- [x] `npm run typecheck`, `npm run test`, `npm run build` pass — 119 frontend tests (2026-06-05)
- [x] `npm run bundle:budget` pass — CI job `frontend-bundle-budget`
- [x] Python test suite passes — 483 passed (2026-06-05); [verification log](./verification-2026-06-05.log)
- [x] Playwright a11y on `/` and `/lab` — CI job `frontend-a11y`
- [x] Visual diff vs v3 baseline — CI job `frontend-visual-diff`
- [x] Functional parity checklist in [07-test-strategy-and-quality-gates.md](./07-test-strategy-and-quality-gates.md) passes

## Grading & trust
- [x] +EV-only grading policy enforced (`ev > 0` for persist + grade) — [14-grading-trust-contract.md](./14-grading-trust-contract.md)
- [x] Grading trust strip on `/grading` and `/track-record` — `grading-trust` / `legacy-routes` tests

## Ship evidence
- [x] PR includes evidence packet index and rollback notes — [09-evidence-packet-index.md](./09-evidence-packet-index.md)
- [x] `LiveSnapshotProvider` prevents full-app flash on snapshot poll — [13-interaction-and-performance.md](./13-interaction-and-performance.md)
- [x] No unresolved critical UX or runtime regressions — soak test on golf.ancc.blog

**Blocked if any item lacks evidence.** "Looks fine locally" is not acceptable.
