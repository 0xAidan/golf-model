# Engine Scale v1 — visual-diff baseline

This directory holds the committed screenshot baseline used by the
`frontend-visual-diff` CI job (`frontend/scripts/compare-visual-baseline.mjs`,
`VISUAL_BASELINE_DIR=docs/screenshots/engine-scale-v1`).

## Why this replaces `ui-overhaul-v3`

The legacy baseline at `docs/screenshots/ui-overhaul-v3/` was captured before the
PR #145 product rebuild (`feat/ui-ux-rebuild`). Every route diverges from it now,
so diffing against it produces only noise. That directory is retained for history.

## Status

Empty by design. While this directory contains no `*.png` files, the visual-diff
comparison **skips gracefully (exit 0)** so CI stays green. The job still runs the
full capture each PR, so capture-time regressions (crashes, blank pages) are caught.

## How to establish the baseline (one-time, against real data)

Placeholder-backend screenshots (empty boards) are low value. Capture against a
backend with a real `DATAGOLF_API_KEY` and seeded `data/golf.db` so the boards
render real rankings/picks:

```bash
# backend serving the built SPA on :8000 with real data
cd frontend
SCREENSHOT_MATRIX_VERSION=engine-scale-v1 \
SCREENSHOT_OUT_DIR=docs/screenshots/engine-scale-v1 \
SCREENSHOT_BASE_URL=http://127.0.0.1:8000 \
node scripts/capture-screenshot-matrix.mjs
```

Commit the resulting PNGs (10 routes x {375,1280,1920} x {dark,light}). From then
on the CI job enforces an 8% max per-image diff ratio (`VISUAL_MAX_DIFF_RATIO`).
Refresh the baseline whenever an intentional UI change is shipped.
