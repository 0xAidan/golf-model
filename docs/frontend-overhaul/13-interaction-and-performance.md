# 13 — Interaction and Performance

Monitoring V3 interaction patterns, performance gates, and CI tooling added in Phase 6.

## Interaction

### Shell and drawer

- **Viewport:** `100dvh` monitoring shell; main column is a flex stack (macro KPI strip + bento grid).
- **Narrow:** Off-canvas drawer with `role="dialog"` + `aria-modal` when open; **Escape** closes; overlay click closes.
- **Banners:** Workspace alerts use `role="status"` or `role="alert"`; Lab lane banners use `status` / `alert` for fallback and partial-snapshot warnings.

### Motion and data

- `InteractionProvider` respects `prefers-reduced-motion` (disables MotionCursor, NumberFlow where configured).
- `LiveSnapshotProvider` + `keepPreviousData` on snapshot queries to avoid full-page flash on poll.
- Warm snapshot prefetch on nav hover for `/`, `/lab`, `/players`.

### Keyboard

- Segment tabs: roving tabindex (cockpit workspace).
- Drawer nav: all `NavLink` items reachable; activating a link closes the drawer on narrow viewports.
- See `monitoring-shell-drawer-a11y.test.tsx` for regression coverage.

## Performance

### Baseline

Metrics live in [`performance-baseline.json`](./performance-baseline.json):

| Metric | Purpose |
|--------|---------|
| `mainChunkGzipBytes` | CI bundle budget (max +5% vs `after` baseline) |
| `snapshotTtfbMs` | API snapshot latency (manual / devtools) |
| `rankingsPaintMs` | Time to rankings grid paint (optional dev marks) |
| `pollLongTaskMsMax` | Main-thread long tasks during 10s poll |

### Bundle analysis

```bash
cd frontend
npm run build
npm run bundle:budget          # fail if main chunk gzip > baseline + 5%
BUNDLE_ANALYZE=1 npm run build # writes dist/stats.html (rollup-plugin-visualizer)
```

### Code splitting

- Route-level lazy imports in `App.tsx` for players, grading, track record, research routes.
- **ECharts** on grading: `BarTrendChartLazy` in `legacy-routes.tsx` defers `echarts-for-react` until the chart section mounts.

### Viewport fill

- Target: **≥75%** of the main column occupied by lane content at **1280×900** and **1920×1080**.
- Test: `frontend/src/test/monitoring-viewport-fill.test.tsx`
- Utility: `frontend/src/lib/monitoring-viewport-coverage.ts`

## CI jobs (`.github/workflows/ci.yml`)

| Job | What it does |
|-----|----------------|
| `frontend-bundle-budget` | `npm run build` + `npm run bundle:budget` |
| `frontend-a11y` | Playwright + `@axe-core/playwright` on `/` and `/lab` (critical = 0) |
| `frontend-visual-diff` | Screenshot matrix → pixel diff vs `docs/screenshots/ui-overhaul-v3/` |

## Storybook

Isolated stories for monitoring primitives (no full app data):

```bash
cd frontend && npm run storybook
```

Stories: `BentoPanel`, `MacroKpiStrip`, `StatusPill`, `HeroDataGrid` under `src/components/monitoring/*.stories.tsx`.

## Screenshots

```bash
# V3 matrix (375 / 1280 / 1920, light + dark) → docs/screenshots/ui-overhaul-v3/
cd frontend && npm run screenshots:matrix:v3
```

Visual diff on PRs compares the PR capture folder to the committed v3 baseline (see `scripts/compare-visual-baseline.mjs`).

## Verification

```bash
export PATH="$HOME/.local/bin:$PATH"
cd frontend && npm ci
npm run typecheck && npm run test && npm run build && npm run bundle:budget
npx playwright install chromium --with-deps
npm run test:a11y
```
