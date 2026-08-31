# UI Design Contract — Golf Model Sports Desk

**Status:** Active (sports desk, Aug 2026)  
**Audience:** Frontend contributors and AI agents  
**Production:** https://golf.shermandavison.com/

`/* anchor: Data Golf + racing form, diverge: Live/Lab split */`

A beautiful UI must never hide the truth. Broken, stale, or unhealthy states stay loud.

This is an operator odds desk, not a Linear/Stripe SaaS dashboard. Tables first. Player face + name first. One turf accent for navigation. Status is a text pill, not a glowing dot.

## Product rules

- Dashboard is Champion. Lab is Challenger. Lab never displays Champion data as a fallback.
- Compare is current-event disagreements only. Results holds historical A/B evidence.
- Grade is automated. Do not present manual grading as a workflow.
- The public operator site has no authentication.
- `/preview` is retired. Redirect to `/`.

## Tokens

Source of truth: [`frontend/src/styles/themes.css`](../../frontend/src/styles/themes.css).  
Primitives: [`frontend/src/styles/desk.css`](../../frontend/src/styles/desk.css) (loads last).  
[`design-system.css`](../../frontend/src/styles/design-system.css) and [`page-layouts.css`](../../frontend/src/styles/page-layouts.css) stay only as leftover layout helpers. Do not add a new CSS layer.

### Type

- Display (event names, page titles): Georgia / Iowan / Palatino serif
- Body: Segoe UI / Helvetica Neue / Avenir — **not** Inter, Geist, or Roboto
- Mono **only** on numbers (`.num`, KPI values, numeric table cells)

### Color

- Light: warm paper `#f3efe6`. Dark: clubhouse `#14110d`. Never `#000` or `#0b0e13` SaaS graphite.
- `--accent-focus` is turf, used for nav and focus — not for “healthy” and not for edge
- `--accent-edge` is EV/edge only
- `--green` / `--amber` / `--red` are system or outcome status only
- No purple, indigo, or violet (`#6366f1`, `#a78bfa`, `#c084fc`)

### Surfaces

- Hairline borders. No card shadows, no glass, no blur, no radial glows, no bento-as-decoration
- Radius 3–6px. No pills except status text chips

## Banned (do not add back)

- Glassmorphism, backdrop-blur bars, film grain
- Pulsing / glowing Live dots
- Mono font on labels, eyebrows, or section titles
- Inter, Geist, Roboto, Montserrat
- Purple-blue AI accents
- Four equal KPI cells unless the four metrics are true peers
- A new `overhaul-vN.css` overlay
- Page-enter fade on a tool opened all day (honor `prefers-reduced-motion`)

## Tables and picks

Use `ProDataGrid` / `HeroDataGrid` only. Pick row left-to-right: market, player face + name vs opponent, edge %, odds, model vs implied, tier, status.

## Shell

One primary action in the header (Refresh). Status chip is a text pill (`LIVE`, `STALE`, `DOWN`). Theme and Calm Mode stay. Do not duplicate Grade in the header if Results already owns it.
