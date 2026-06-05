# 09 — Evidence Packet Index

Store artifacts under the screenshot dirs below and link from the PR.

## Screenshot matrices

| Version | Directory | Viewports | Baseline |
|---------|-----------|-----------|----------|
| V1 (pre-overhaul) | [ui-overhaul-v1](../screenshots/ui-overhaul-v1/README.md) | 375, 1280 | Git commit `371d194` |
| V2 (terminal visual) | [ui-overhaul-v2](../screenshots/ui-overhaul-v2/README.md) | 375, 1280 | 40 PNGs |
| V3 (monitoring) | [ui-overhaul-v3](../screenshots/ui-overhaul-v3/README.md) | 375, 1280, 1920 | 60 PNGs (CI `frontend-visual-diff`) |

### V3 matrix (committed baseline)

| Route | 375 dark | 375 light | 1280 dark | 1280 light | 1920 dark | 1920 light |
|-------|----------|-----------|-----------|------------|-----------|------------|
| dashboard | yes | yes | yes | yes | yes | yes |
| picks | yes | yes | yes | yes | yes | yes |
| players | yes | yes | yes | yes | yes | yes |
| lab | yes | yes | yes | yes | yes | yes |
| lab-picks | yes | yes | yes | yes | yes | yes |
| grading | yes | yes | yes | yes | yes | yes |
| track-record | yes | yes | yes | yes | yes | yes |
| legacy-model | yes | yes | yes | yes | yes | yes |
| champion-challenger | yes | yes | yes | yes | yes | yes |
| diagnostics | yes | yes | yes | yes | yes | yes |

Capture (backend on :8000):

```bash
cd frontend && npm run build
SCREENSHOT_MATRIX_VERSION=v3 SCREENSHOT_BASE_URL=http://127.0.0.1:8000 npm run screenshots:matrix:v3
```

PR candidates: `docs/screenshots/ui-overhaul-v3-pr/` (CI only; not committed).

## Test logs
- [verification-2026-06-04.log](./verification-2026-06-04.log) — V2 terminal overhaul
- [verification-2026-06-05.log](./verification-2026-06-05.log) — Monitoring V3 gates (`feat/monitoring-v3-complete`)

## PR body must include
- Before/after narrative (V1 → V3 or V2 → V3 as appropriate)
- Commit SHA
- Deploy target
- Rankings behavior confirmation (upcoming vs live)
- Grading trust strip / +EV-only policy confirmation
- Known limitations
