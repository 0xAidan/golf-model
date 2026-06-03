# UI Overhaul 2026 — Design Specification

**Status:** Phase 1–3 complete on `feat/ui-overhaul-2026` (PR #134)  
**Scope:** Full `frontend/` visual and interaction rebuild; zero backend/API contract changes  
**Last updated:** 2026-06-03

---

## 1. Visual thesis

Golf Model should feel like a **professional odds terminal built for golf**—closer to Data Golf’s model-vs-market grids and MollyBet’s decision-first trading UI than to a generic SaaS dashboard. Surfaces are **flat and grid-aligned** (no glass, no hero marketing blocks); typography does the hierarchy (Cabinet Grotesk for structure, JetBrains Mono for numbers); color is **semantic only** (green = edge/positive, amber = caution/lab lane, red = loss/risk). Light mode is a clean paper terminal; dark mode is the default operator environment—both equally intentional, not an inverted afterthought. The product should scan in **under three seconds per screen**: what event, what’s live, where is edge, what’s the pick status.

**Feels like:** Bloomberg terminal × Data Golf odds screen × Pinnacle compact markets.  
**Not like:** Purple-gradient AI dashboard, card-heavy Notion clone, or decorative analytics landing page.

---

## 2. Information architecture — scan vs detail

Progressive disclosure follows three layers (Totals.us / bwin / SaaS playbook):

| Layer | Purpose | UI affordances |
|-------|---------|----------------|
| **Glance** | Decide in &lt;5s | KPI strip, primary table columns, status pills, tab counts |
| **Detail** | Validate a pick | Expand row, Sheet/Drawer, secondary tabs |
| **Configuration** | Power user | Column picker, density toggle, filters, “Expand all” |

### Per route

| Route | Glance (default) | Detail (disclosed) | Config |
|-------|------------------|-------------------|--------|
| `/` Dashboard | Event + mode tab; Top picks (Pick, Book·Odds, Tier, EV); Rankings (#, Player, Composite); Filters (edge, books) | Player spotlight; expanded pick gaps; secondary markets; leaderboard; course/weather | Column visibility; export; full recent-results |
| `/matchups` Picks | Matchup table core cols; tab counts | Row expand (gaps, probs, stake); diagnostics strip | Availability filter; min edge (from App); book chips |
| `/lab` | Same as dashboard + lab banner | Research instrumentation deck | Same + lab lane indicators |
| `/lab/picks` | Lab picks table + log CTA | Diagnostics | Same as picks |
| `/players` | Search + field list; header KPIs; skill profile | Rolling windows, charts, history tables | Section collapse per profile block |
| `/grading` | KPI strip; event list P&L | Per-event pick table | Source toggle; season chart |
| `/track-record` | KPI; event accordion summary | Pick-level expand | — |
| `/research/legacy-model` | Top-25 rankings + matchups | — | — |
| `/research/champion-challenger` | Model, Brier 30d, ROI 30d | N, CLV, 14d windows | — |
| `/research/diagnostics` | Warnings + counters | Reason codes; data health detail | — |

---

## 3. Design tokens

### Typography

| Token | Value | Use |
|-------|-------|-----|
| `--font-display` | Cabinet Grotesk, fallback system-ui | Headlines, nav labels |
| `--font-body` | Satoshi, fallback system-ui | UI chrome, descriptions |
| `--font-mono` | JetBrains Mono | All numeric columns, chips, timestamps |
| `--text-2xs` | 10px | Meta, section labels |
| `--text-xs` | 11px | Table header, chips |
| `--text-sm` | 12px | Body default |
| `--text-base` | 13px | Table cells |
| `--text-md` | 15px | Page titles |
| `--text-lg` | 18px | Event headline (header bar) |

### Spacing (4px base)

`--space-1` (4) … `--space-8` (32). Table cell padding: `--space-2` compact / `--space-3` comfortable.

### Radii

`--radius-sm` 4px · `--radius-md` 6px · `--radius-lg` 8px (no pills except status dots).

### Semantic colors (light `:root` / dark `.dark`)

| Role | Light | Dark |
|------|-------|------|
| `--bg-base` | `#f4f6f8` | `#080a0b` |
| `--bg-raised` | `#ffffff` | `#0d1012` |
| `--bg-overlay` | `#eef1f4` | `#141719` |
| `--border-default` | `#d8dee4` | `#1f2426` |
| `--text-primary` | `#0f1419` | `#e8ecef` |
| `--text-secondary` | `#5c6b78` | `#6b7a84` |
| `--text-tertiary` | `#8a97a3` | `#374349` |
| `--accent-positive` | `#15803d` | `#22c55e` |
| `--accent-warning` | `#b45309` | `#f59e0b` |
| `--accent-danger` | `#dc2626` | `#ef4444` |
| `--accent-lab` | `#ca8a04` | `#f5b418` |
| `--accent-focus` | `#2563eb` | `#5c6b78` |

Legacy aliases (`--green`, `--gold`, `--bg`, `--surface`, etc.) map to semantic tokens during migration.

---

## 4. Component strategy

### shadcn primitives (install via CLI)

Card, Tabs, Sheet, Dialog, Tooltip, Skeleton, ScrollArea, Badge, DropdownMenu, Select, Switch — compose with existing `Button`, `CollapsibleSection`.

### Shared app components

| Component | Responsibility |
|-----------|----------------|
| `DataTable` | TanStack Table v8: sort, column visibility, density (`compact`/`comfortable`), sticky header, numeric `tabular-nums` right-align |
| `MetricChip` | Label + value + optional delta tone |
| `PageHeader` | Title, description, actions slot |
| `FilterBar` / `FilterSheet` | Desktop inline filters; mobile bottom sheet |
| `EmptyState` | Extend existing; actionable next step |
| `ChartTheme` | ECharts `theme` object synced to light/dark CSS variables |

### Charts

`charts-v2.tsx` consumes `getChartTheme(mode)` — axis/grid/tooltip colors from tokens, not hardcoded RGBA.

### Shell

- Left nav: Workspace / Records / Research hierarchy (unchanged IA)
- Sticky context bar: event name, meta, Live|Upcoming|Past, snapshot chip, grade, refresh
- Theme toggle: Light / Dark / System (header, persists `golf-model.theme`)
- Mobile: bottom nav (primary) + drawer for Records/Research

### `data-testid`

All existing IDs preserved. New IDs only where tests need hooks (`theme-toggle`, `data-table-density`).

---

## 5. Route-by-route checklist

- [x] **`/`** — Collapsible course/weather & recent results; shared workspace CSS; filters/rail polish; route motion
- [x] **`/matchups`** — PageHeader + FilterBar; diagnostics in CollapsibleSection (default closed)
- [x] **`/lab`** — Lab banners; research deck patterns (prior commit)
- [x] **`/lab/picks`** — `lab-picks-*` layout utilities
- [x] **`/players`** — Profile blocks in CollapsibleSection; KPI/metric CSS classes
- [x] **`/grading`** — Season P&L chart in CollapsibleSection; `records-grid-2col`
- [x] **`/track-record`** — Accordion patterns (prior commit)
- [x] **`/research/*`** — PageHeader on research routes (prior commit)
- [x] **Shell** — Theme toggle, `RouteTransition` (Framer Motion + reduced-motion)
- [x] **`index.css`** — `themes.css` + `page-layouts.css`; inline styles reduced on major routes

---

## 6. Anti-slop checklist (we will NOT)

- Purple/violet gradients or “AI product” hero sections
- Glassmorphism, neumorphism, or decorative blur cards
- Generic stock illustrations or empty marketing copy on app routes
- Card grids where a table or split pane is clearer
- More than one display typeface family beyond display/body/mono pairing
- Animations &gt;200ms or motion without `prefers-reduced-motion` respect
- Hiding critical actions (grade, refresh, mode switch) behind menus
- Breaking `LegacyRouteGate`, lab env gating, or live-refresh hooks
- Renaming or removing stable `data-testid` values

---

## 7. Test and verification plan

```bash
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
```

Manual (browser): each primary route at **375px** and **1280px**, **light** and **dark** — screenshot evidence in PR.

Regression focus: prediction tab switching, book filter, min edge, player select → spotlight, lab snapshot fallback banners, grading source toggle, past-mode gate on `/matchups`.

---

## Appendix A — Codebase audit (Phase 0.1)

### Routes

See `App.tsx`: `/`, `/lab`, `/lab/picks`, `/cockpit-lab` → redirect, `/players`, `/matchups` (LegacyRouteGate past), `/grading`, `/track-record`, `/research/*`. Lazy: players, grading, track-record, research pages.

### Pages + cockpit

11 cockpit files; 9 page TSX (+ tests). **~404** inline `style={{}}` in pages+cockpit; `index.css` ~2700 lines monolithic terminal CSS.

### Storage keys

`golf-model.prediction-request`, `.latest-prediction-run`, `.matchup-search`, `.min-edge`, `.selected-books`, `.selected-player`, lab research expanded flags, react-resizable-panels autoSaveIds.

### Installed but unused in src

`@tanstack/react-table`, `framer-motion` — **adopt in Phase 1/3**.

---

## Appendix B — External research (Phase 0.2)

| Source | URL | Actionable patterns |
|--------|-----|---------------------|
| Data Golf Predictions | https://datagolf.com/predictions/pga-tour | Dense player grid; model selector; position probability columns; player search; odds format toggle |
| Data Golf Finish odds | https://datagolf.com/betting-tool-finish | Model vs books matrix; add/remove books; tap cell for EV; market selector (win/top5/…) |
| Data Golf Matchups | https://datagolf.com/betting-tool-matchups | Bet type + book selectors; hover/tap for EV; book comparison columns |
| Action Labs Markets | https://labs.actionnetwork.com/markets | Multi-book line grid; customize books; period/market filters; terminal nav (Markets/Props) |
| Flatstudio MollyBet | https://www.flatstudio.co/blog/why-your-betslip-is-wrong-ux-of-a-trading-terminal | Decision before comparison; light+dark from day one; token system; mobile compact betslip; A/B on dense UI |
| Totals dashboards | https://totals.us/designing-totals-dashboards-that-actually-make-bettors-smart | 3–7 glance metrics; model vs market divergence first; expandable layers |
| bwin live (Gromontova) | https://gromontova.com/projects/bwin | Progressive disclosure + “expand all”; speed over exhaustive data in live context |
| BetBank dashboard | https://betbank.ai/tools/dashboard | Command center; widget/custom layout; theme in settings; quick stats + feed |
| Pinnacle (reference) | — | Minimal chrome; tight row height; American odds; no decorative UI |

**Mobile:** bottom nav for primary destinations (already in shell); filters in sheet; horizontal scroll only for book columns with sticky first column.

**Color semantics:** green = positive EV/edge, amber = lab/warning, red = loss/danger, muted = unavailable/no line.

---

## Appendix C — OSS inventory (Phase 0.3)

| Asset | Link | Use |
|-------|------|-----|
| shadcn Data Table | https://ui.shadcn.com/docs/components/radix/data-table | Column visibility, sorting, pagination patterns |
| tablecn | https://github.com/sadmann7/tablecn | Filter toolbar, faceted filters reference |
| TanStack Table v8 | installed | Core of `DataTable` wrapper |
| shadcn dark mode | https://ui.shadcn.com/docs/dark-mode/vite | `class` on `document.documentElement` + blocking script |
| Framer Motion | installed | Page/panel transitions (Phase 3) |
| ECharts | installed | Themed via `ChartTheme` |
| Lucide | installed | Icons |
| **Optional** `sonner` | — | Toasts for grade/refresh feedback (only if replacing alert banners) |
| **Optional** `vaul` | — | Mobile filter drawer (only if Sheet insufficient) |
| **Optional** `cmdk` | — | Command palette (deferred; not in v1 scope) |

**New packages:** None required for theme (custom + inline script). Add `sonner` only if toast UX replaces inline alerts in a follow-up.

---

## Pre-build plan (ce-frontend-design)

1. **Visual thesis:** Above §1  
2. **Content plan:** Shell context bar → workspace table → spotlight/detail  
3. **Interaction plan:** (a) Staggered panel reveal on route change ≤150ms; (b) Row expand height transition; (c) Theme cross-fade via CSS `color-scheme` + variable swap (no layout shift)
