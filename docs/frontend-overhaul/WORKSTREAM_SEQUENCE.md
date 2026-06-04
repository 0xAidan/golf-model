# Multi-Agent Workstream Sequence

## Phase 0 — Baseline (complete before UI work)
- Capture screenshot matrix on `main`
- Document current rankings behavior

## Phase 1 — Parallel execution
| Workstream | Owner | Depends on | Delivers |
|------------|-------|------------|----------|
| WS1 UI overhaul | UI Agent | Phase 0 | Grid layout, tabbed boards, design tokens |
| WS2 Bug/perf | Stability Agent | WS1 column contract | Rankings hydration, polling constants, fallback UX |

## Phase 2 — Integration
| Workstream | Owner | Depends on | Delivers |
|------------|-------|------------|----------|
| WS3 QA | QA Agent | WS1 + WS2 merged | Tests, screenshots, parity checklist |
| WS4 Release | Integration Agent | WS3 green | PR, deploy soak, rollback doc |

## File ownership boundaries
- **WS1 only:** `workspace.tsx`, `cockpit-resizable-stack.tsx`, `responsive-panels.tsx`, `terminal-base.css`, `themes.css`
- **WS2 only:** `prediction-board.ts`, `App.tsx`, `query-polling.ts`, `cockpit-columns.tsx`
- **WS3 only:** `*.test.ts(x)`, `capture-screenshot-matrix.mjs`, `docs/frontend-overhaul/`
- **Shared (coordinate):** `prediction-workspace-page.tsx`

## Merge order
1. WS2 rankings contract (tests first)
2. WS1 layout overhaul
3. WS3 evidence + fixes
4. WS4 PR
