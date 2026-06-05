# 12 — Deslop Checklist (Monitoring V3)

Sign when Phase 1 is verified on `feat/monitoring-v3-complete`.

| # | Check | Pass |
|---|--------|:----:|
| 1 | Removed Fontshare + Google Fonts from `index.html` | ☑ |
| 2 | Removed Cabinet/Satoshi CDN import from `index.css` | ☑ |
| 3 | Removed `@fontsource-variable/geist` from `package.json` | ☑ |
| 4 | Removed `@fontsource/jetbrains-mono` from `package.json` | ☑ |
| 5 | `themes.css` uses Zodiak / Switzer / Fragment Mono tokens | ☑ |
| 6 | Self-hosted `@font-face` in `fonts.css` + woff2 in `public/fonts/` | ☑ |
| 7 | `terminal-monitoring-v3.css` loaded after `terminal-visual-v2.css` | ☑ |
| 8 | Mono only on `.num`, `.kpi-value`, numeric table cells | ☑ |
| 9 | `@number-flow/react` on macro KPI numbers | ☑ |
| 10 | `@formkit/auto-animate` added (used Phase 4+ feeds) | ☑ |
| 11 | Screenshot matrix does **not** block `/fonts/` (CDN only) | ☑ |
| 12 | `npm run typecheck && npm run test && npm run build` pass | ☑ |

**Signed:** Phase 7 documentation gate **Date:** 2026-06-05

**Notes:** Verified on `feat/monitoring-v3-complete` — 483 pytest / 119 vitest / bundle budget green. See [verification-2026-06-05.log](./verification-2026-06-05.log).
