# UI Design Contract — Golf Model Operator Terminal

**Status:** Active (UI-first recovery program)  
**Audience:** Frontend contributors and AI agents  
**Production:** https://golf.ancc.blog/

This document is the single source of truth for visual and information architecture rules during the UI-first recovery. It implements plan sections §1.3.1–§1.3.7. **A beautiful UI must never hide the truth** — broken, stale, or unhealthy states are shown loudly until underlying problems are fixed.

---

## 1. Tokens (`frontend/src/styles/themes.css`)

### Type scale

| Token | Size | Role |
|-------|------|------|
| `--text-2xs` | 10px | Micro labels |
| `--text-xs` | 11px | Chips, meta |
| `--text-sm` | 12px | Table body |
| `--text-base` / `--text-md` | 13–15px | UI copy |
| `--text-lg` | 18px | KPI values |
| `--text-xl` | 22px | Page titles |
| `--text-2xl` | 28px | Event headlines |

Roles: table text = `sm`; UI copy = `md`; KPI value = `lg`/`xl` mono; page title = `xl`; shell event headline = `2xl`.

### Fonts

- **Display:** Zodiak (`--font-display`)
- **Body:** Switzer (`--font-body`)
- **Numerics only:** Fragment Mono (`--font-mono`) — `.num`, KPI values, table numeric columns

Banned fonts: per [docs/frontend-overhaul/11-monitoring-design-system.md](../frontend-overhaul/11-monitoring-design-system.md).

### Spacing (`--space-1` … `--space-8`)

4 / 8 / 12 / 16 / 20 / 24 / 28 / 32 px.

Rhythm: page sections `--space-6`; card padding `--space-4`; intra-card stacks `--space-2`/`--space-3`. No raw pixel margins in TSX on touched files.

### Surfaces & elevation

- Card: `--surface` + `--border` + `--r-md`
- Overlay (drawer/sheet/menu): `--surface-2` + `--shadow-overlay`
- Radius: `--r-sm` 4 / `--r-md` 6 / `--r-lg` 8

### Status colors — usage rules

| Token | Meaning |
|-------|---------|
| `--green` / `--amber` / `--red` (+ `-bg`) | **System or outcome status only** — freshness, worker health, disk, W/L/Push, graded/ungraded |
| `--accent-edge` | **EV / edge numerics only** — never reuse health green for positive edge |
| `--turf-*` | Decorative accent only (hero eyebrow, brand) — never state |

If a color does not answer “what state is this in?”, use `--text` / `--text-muted`.

### Motion

- Hover/expand: `--ease` 160ms
- Route transition ≤ 120ms fade
- `NumberFlow` on KPI value changes only
- No shimmer longer than actual load; honor `prefers-reduced-motion`

---

## 2. Action language

| Kind | Look | Rule |
|------|------|------|
| Primary | Filled button | Max **one** per page header + shell Refresh |
| Secondary | Outline/ghost | Other actions |
| Destructive | Red outline + typed confirm | Promote/rollback, restore |
| Quiet | Text/icon | Toggles, expanders, theme, command |

Shell owns global Refresh (primary), Grade (secondary), theme/command (quiet). Pages do not duplicate shell actions.

---

## 3. Pick-row anatomy

Left→right (row) or top→bottom (card):

1. Market chip (`72-hole` / `Round N` / `Top 20`)
2. Pick player vs opponent (pick emphasized)
3. Edge % in mono `--accent-edge`
4. Best odds + book
5. Model prob vs implied (muted)
6. Tier badge (STRONG / GOOD / LEAN)
7. Status slot (pre-event blank; live position; graded W/L/Push/Void)

One expand affordance for detail. No other buttons on a pick row.

Component: `frontend/src/components/ui/pick-row.tsx` (U4+).

---

## 4. Table anatomy

`ProDataGrid` / `HeroDataGrid` is the only table primitive.

- 32px rows; numeric columns right-aligned mono `tabular-nums`
- Sticky header; virtualize >80 rows
- Loading = shimmer inside frame; empty = `EmptyState` inside frame
- Row hover `--row-hover`; mobile horizontal scroll with `--layout-table-edge-pad`, first column sticky

---

## 5. Status-banner anatomy

`StatusBanner`: icon + bold title + one plain-English sentence + optional action + optional “Details → System”.

Tones: `info` / `warn` / `danger`.

**One page-level banner slot** under the page header; highest severity wins; extras collapse to “+ n more”.

---

## 6. Shell anatomy

**Top bar:** brand/hamburger · event headline + sub (course · field) · mode switch (Live/Upcoming/Past on `/` and `/lab` only) · **FreshnessChip** · Refresh · Grade · command/theme.

**Nav drawer:** Product (Dashboard, Lab, Compare, Players, Results, System) + collapsed Research (Eval, Champion vs Challenger, Legacy model).

**Page content:** `.page-shell--route` — max-width 1440px, `padding-inline: var(--layout-page-pad-x)`.

Exactly one `PageHeader` per page (title, subtitle, ≤1 primary action, banner slot below).

Files: `monitoring-shell.tsx`, `terminal-monitoring-v3.css`, `page-layouts.css`.

---

## 7. One metric — one home

| Metric | Home | Others may show |
|--------|------|-----------------|
| Live/upcoming +EV picks & edges | `/`, `/lab` | Count chip linking there |
| Season P&L, ROI, hit rate, units | `/results` → Analytics | “Results →” link |
| Last-event graded + ungraded +EV | `/results` → Grading | ✓/✗ chip on `/` |
| Dashboard vs Lab disagreement | `/compare` | — |
| Player skill / form / course fit | `/players` | Rank in pick detail only |
| Worker / disk / backup / jobs | `/system` | FreshnessChip + global banners |
| Calibration, CLV, Brier, promotion | `/eval` | — |

---

## 8. Related docs

- Master recovery plan: `.cursor/plans/ui-first-recovery-plan.md` (plan branch; do not edit during implementation PRs)
- Monitoring design system: `docs/frontend-overhaul/11-monitoring-design-system.md`
- Grading trust: `docs/frontend-overhaul/14-grading-trust-contract.md`
- Agent quick reference: `docs/AGENTS_KNOWLEDGE.md` §12

---

## Appendix A. Cohesion Audit 2026-07-06

Scope: U12 cohesion pass against the live frontend structure on branch `impl/u12-cohesion`.

### Verified as cohesive

- Shell ownership is clean: `frontend/src/app/app-content.tsx` owns route wiring, shell actions, and dashboard/lab hydration; `frontend/src/App.tsx` is now just provider composition.
- Primary navigation matches the contract: `MonitoringShell` exposes Dashboard, Lab, Compare, Players, Results, and System, with Research collapsed behind its own section.
- Route homes are consistent with the one-page-one-header model: route screens live in `frontend/src/pages/`, reusable shell/product primitives live under `frontend/src/components/`.
- Global actions stay in the shell: Refresh and Grade are mounted in `MonitoringShell` header actions rather than duplicated across the main route pages.

### Drift found

- `docs/AGENTS_KNOWLEDGE.md` had stale frontend home references: it still described `App.tsx` as the shell/route owner, omitted `app/app-content.tsx`, and listed the fonts path under `frontend/src/` instead of `frontend/public/`.

### Fixes applied in this pass

- Updated `docs/AGENTS_KNOWLEDGE.md` frontend sections to reflect the real shell split, route map, component homes, and fonts path.
- Added checkpoint-C verification notes to `docs/frontend-overhaul/verification-2026-07-06.log`.
- No frontend code changes were required for this cohesion pass; the issues found were documentation drift, not runtime contract violations.
