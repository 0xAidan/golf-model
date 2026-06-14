# GTM production hardening — baseline screenshots (2026-06-14)

Capture before/after evidence for the AAA UI and reliability epics (E0, E9–E12).

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Dashboard — upcoming, live, and past modes |
| `/lab` | Lab command center |
| `/compare` | Track comparison |
| `/eval` | Model eval and promotion |
| `/players` | Player profiles |
| `/results` | Grading and track record |
| `/system` | Ops and data health |

## Viewports

Capture each route at:

- **375px** — mobile
- **1280px** — laptop
- **1920px** — desktop

## Commands

From `frontend/`:

```bash
npm run screenshots:matrix:v3
npm run visual:diff
```

## Naming convention

```
gtm-2026-06-14/<route>-<viewport>-<mode>.png
```

Examples:

- `gtm-2026-06-14/dashboard-1280-live.png`
- `gtm-2026-06-14/lab-375-upcoming.png`
- `gtm-2026-06-14/compare-1920-upcoming.png`

## Modes to capture on dashboard

1. **Upcoming** — event loaded, rankings visible
2. **Live** — active tournament, live columns
3. **Past** — replay selector visible (with and without event selected)

## Acceptance

Store baselines in this folder before E9–E12 polish lands. Re-run the matrix after polish and attach the visual diff report to the E13 verification log.
