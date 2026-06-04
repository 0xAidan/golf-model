# UI Overhaul V2 — Completion checklist

**Branch:** `feat/ui-overhaul-v2`  
**Status:** COMPLETE (M2–M4 implementation pass)

## M1 Visual foundation — COMPLETE

- [x] `terminal-visual-v2.css` tokens, tables, command menu mobile, filter chip
- [x] Cabinet Grotesk + Satoshi (Fontshare) in `index.css`
- [x] `ChartThemeProvider` in `main.tsx`
- [x] `table-density.ts`, `use-odds-flash.ts`, ProDataGrid density + flash
- [x] Shell logo CSS vars, `NARROW_VIEWPORT_MAX_PX=767`

## M2 Routes & grids — COMPLETE

- [x] `players-columns.tsx` — field list, rolling SG, course fit, recent rounds
- [x] `players-page.tsx` — no VAR, ProDataGrid field + profile tables, CSS classes
- [x] `player-profile-sections.tsx` — ProDataGrid tournament/bets, ≤15 inline styles
- [x] `legacy-model-page.tsx` — ProDataGrid
- [x] `legacy-routes.tsx` — removed duplicate `PlayersPage`, accordion CSS, `TerminalPageHeader`
- [x] `picks-page.tsx` — SecondaryBoard ProDataGrid + `buildSecondaryColumns`
- [x] `PanelChrome` on `player-spotlight.tsx`, `event-modules.tsx` (course/weather, market intel)
- [x] `lab-picks-page`, `cockpit-lab-page`, `research-instrumentation-deck` inline reduction
- [x] `diagnostics-page` / `data-health-panel` — CSS classes

## M3 Mobile — COMPLETE

- [x] `FilterSheet` — prediction workspace, picks, grading (legacy-routes), lab picks
- [x] Filter summary chip — prediction workspace narrow header
- [x] Command menu mobile full-width — `terminal-visual-v2.css` (verified)

## M4 Proof — COMPLETE

- [x] `scripts/check-inline-styles.sh` (max 120 `style={{` in `frontend/src`)
- [x] Vitest — `filter-sheet.test.tsx`, `command-menu.test.tsx`, ProDataGrid density test
- [x] `frontend/scripts/capture-screenshot-matrix.mjs` + `npm run screenshots:matrix`
- [x] Reason badge, failed-candidates-card, term-notice--inset, leaderboard-row-detail, players sidebar CSS

## Verification

```bash
cd frontend && npm run typecheck && npm run test && npm run build
bash scripts/check-inline-styles.sh
chmod +x scripts/check-inline-styles.sh
```

Manual: `npm run screenshots:matrix` with backend on `:8000`.
