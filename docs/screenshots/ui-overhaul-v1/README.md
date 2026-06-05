# UI Overhaul V1 screenshot baseline (historical)

**Baseline commit:** `371d194` — state of `main` before the terminal visual overhaul (V2).

This directory holds the **before** matrix for before/after PR narratives. PNGs are not always committed (large binaries); regenerate from the baseline SHA when needed.

## Regenerate from baseline

```bash
git worktree add ../golf-model-v1-baseline 371d194
cd ../golf-model-v1-baseline/frontend
npm ci && npm run build
# Start backend from that worktree on :8000, then:
SCREENSHOT_BASE_URL=http://127.0.0.1:8000 npm run screenshots:matrix
# Outputs to docs/screenshots/ui-overhaul-v2/ in that worktree — copy or re-run with out dir v1 if scripted
```

For the committed **after** matrices, see:

- V2 (terminal): [ui-overhaul-v2/README.md](../ui-overhaul-v2/README.md) — 40 PNGs @ 375×1280
- V3 (monitoring): [ui-overhaul-v3/README.md](../ui-overhaul-v3/README.md) — 60 PNGs @ 375×1280×1920

## Expected matrix (V1 / V2 capture script)

Same routes as V2 — 10 routes × 2 viewports × 2 themes = **40 PNGs**:

| Route | 375 dark | 375 light | 1280 dark | 1280 light |
|-------|----------|-----------|-----------|------------|
| dashboard | yes | yes | yes | yes |
| picks | yes | yes | yes | yes |
| players | yes | yes | yes | yes |
| lab | yes | yes | yes | yes |
| lab-picks | yes | yes | yes | yes |
| grading | yes | yes | yes | yes |
| track-record | yes | yes | yes | yes |
| legacy-model | yes | yes | yes | yes |
| champion-challenger | yes | yes | yes | yes |
| diagnostics | yes | yes | yes | yes |
