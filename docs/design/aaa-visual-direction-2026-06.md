# AAA visual direction — June 2026

Premium operator terminal for golf-model. Dense enough for betting workflows, polished enough for GTM.

## North star

- **Operator-first density** — scan plays and rankings in seconds.
- **Clear hierarchy** — one primary action per panel; metadata in chips, not cramped headers.
- **Honest status** — stale, degraded, and empty states are explicit; no decorative noise.
- **Native UX** — system cursor, keyboard focus, reduced-motion respect.

Inspired by Linear, Stripe Dashboard, and Vercel — without generic AI-dashboard gradients or purple slop.

## Typography

| Token | Size | Use |
|-------|------|-----|
| `--text-2xs` | 10px | Micro labels, table meta |
| `--text-xs` | 11px | Column headers, chips |
| `--text-sm` | 12px | Body, table cells |
| `--text-base` | 13px | Default UI text |
| `--text-md` | 15px | Section titles |
| `--text-lg` | 18px | Page titles |

Fonts: **Zodiak** (display), **Switzer** (body), **Fragment Mono** (data).

## Spacing scale

| Token | Value |
|-------|-------|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |

Page padding uses `--layout-page-pad-x` / `--layout-page-pad-y`. Section gaps use `--layout-section-gap` (24px).

## Elevation

| Token | Use |
|-------|-----|
| `--shadow-surface` | Cards on base background |
| `--shadow-raised` | Popovers, sticky toolbars |
| `--shadow-overlay` | Modals, drawers |

Surfaces: `--surface` (primary), `--surface-2` (nested), `--surface-3` (inset).

## Tables

- Default density: **compact** (32px rows) with optional comfortable (40px).
- Header row: uppercase mono labels, `--text-secondary`, bottom border only.
- Row hover: `--row-hover`; selected: `--row-selected`.
- Positive edge accent: left inset bar `--accent-edge`.

## Cards and headers

- Card headers: `min-height` not fixed height; title + metadata chips on separate rows when needed.
- Avoid cramming baseline labels into a 30px header strip.

## Banners

One owner per notice type:

| Notice | Owner |
|--------|-------|
| Snapshot stale / worker | `TrustStatusBanner` via lane trust |
| Lab fallback / partial lane | Lane trust (not duplicated in Lab shell) |
| Hydration fallback | Workspace alerts |
| Eligibility | Workspace alerts |

## Status colors

Semantic only — no decorative gradients:

- Positive / edge: `--green`
- Warning / stale: `--amber`
- Danger / error: `--red`
- Neutral / no market: `--text-tertiary`

## Motion

- No custom cursor (`MotionCursor` removed).
- Transitions: `--ease` (160ms); respect `prefers-reduced-motion`.
- Odds flash: brief row highlight only.

## Anti-patterns (banned)

- Token rename without visible layout change
- Purple-gradient generic dashboards
- Displaying non-bettable markets as actionable
- Duplicate stale/snapshot banners
- Fixed-height headers with overflowing metadata

## Evidence gate

Before marking UI epics done:

```bash
cd frontend && npm run screenshots:matrix:v3 && npm run visual:diff && npm run bundle:budget
```

Owner review must confirm perceptible quality lift vs `docs/screenshots/gtm-2026-06-14/` baselines.
