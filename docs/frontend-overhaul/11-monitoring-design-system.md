# 11 — Monitoring Design System (V3)

**Status:** Phase 1 foundation  
**Branch:** `feat/monitoring-v3-complete`

## Typography (self-hosted)

| Role | Family | CSS token | Usage |
|------|--------|-----------|--------|
| Display | Zodiak | `--font-display` | Titles, panel headers, nav labels |
| Body | Switzer | `--font-body` | UI copy, nav items |
| Mono | Fragment Mono | `--font-mono` | `.num`, `.kpi-value`, KPI strip, table numeric columns |

**Banned:** Cabinet Grotesk, Satoshi, JetBrains Mono, Geist, Inter, Fontshare/Google CDN.

Files: `frontend/public/fonts/*.woff2` → `frontend/src/styles/fonts.css` → preloads in `index.html`.

## Color — turf palette

Defined in `frontend/src/styles/terminal-monitoring-v3.css`:

- `--turf-fairway`, `--turf-pin`, `--turf-sand`, `--turf-rough`, `--turf-sky`
- Semantic mapping: live = pin, warn = sand, positive = fairway

Base neutrals remain in `themes.css`; v3 accents layer on top.

## Layout

| Primitive | Class / component | Notes |
|-----------|-------------------|--------|
| Shell | `MonitoringShell` | `100dvh`, drawer nav, `monitor-lane` full width |
| Hero | `HeroBand` | Event title + eyebrow + meta |
| KPIs | `MacroKpiStrip` | NumberFlow on numeric cells |
| Bento | `BentoGrid` + `BentoPanel` | `1px` gap hairline grid, internal scroll |
| Empty | `PanelBackfill` | No empty bento cells in production lanes |
| Tables | `HeroDataGrid` | Wraps `ProDataGrid`; 32px rows, mono numerics |
| Feed | `FeedList` / `FeedItem` | Alert / pick streams |
| Ticker | `MonitoringTicker` | Dual-track scroll |
| Status | `StatusPill` | live / warn / idle / error |

## CSS load order

1. `themes.css`
2. `fonts.css`
3. `page-layouts.css`
4. … app utilities …
5. `terminal-base.css`
6. `terminal-visual-v2.css`
7. `terminal-monitoring-v3.css` (last)

## Import path

```tsx
import {
  MonitoringShell,
  HeroBand,
  MacroKpiStrip,
  BentoGrid,
  BentoPanel,
  HeroDataGrid,
} from "@/components/monitoring"
```

## Phase 1 gate

- [x] `npm run typecheck` / `test` / `build` green (119 tests, 2026-06-05)
- [x] Font woff2 files present under `public/fonts/`
- [x] No CDN font requests in network tab (screenshot script blocks CDN only)
- [x] `[12-deslop-checklist.md](./12-deslop-checklist.md)` signed 2026-06-05
