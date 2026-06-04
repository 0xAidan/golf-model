# 02 — Current State and Failure Lessons

## Architecture snapshot (pre-overhaul)
- Monolithic `App.tsx` owns queries, filters, lab/prod branching.
- Cockpit layout uses `react-resizable-panels` with drag handles in workspace, center stack, and left rail.
- Single `buildRankingsColumns` used for all modes — live-scoring columns shown on upcoming tab.
- Snapshot hydration falls back cross-section (upcoming → live) without visible source labeling.

## Prior failure patterns
| Pattern | Manifestation | Prevention |
|---------|---------------|------------|
| Premature completion | User saw unchanged UI after "shipped" claims | Two-key gate: technical + perceptual evidence |
| CSS cascade bug | V2 styles loaded before base CSS | Enforced import order in `index.css` |
| Post-deploy regressions | Blocking `/api/dashboard/state`, worker detection | Pre-merge soak + canary checks |
| Rankings regression | Upcoming table looked like live table or disappeared | Explicit column builders + hydration contract tests |

## Key files
- Layout: `frontend/src/components/cockpit/workspace.tsx`, `cockpit-resizable-stack.tsx`, `responsive-panels.tsx`
- Rankings: `frontend/src/lib/cockpit-columns.tsx`, `frontend/src/lib/prediction-board.ts`
- Data: `frontend/src/App.tsx`, `backtester/dashboard_runtime.py`
