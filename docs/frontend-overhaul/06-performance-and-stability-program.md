# 06 — Performance and Stability Program

## Polling constants
Centralized in `frontend/src/lib/query-polling.ts`:
- Dashboard: 30s
- Live snapshot: 10s
- Live refresh status: 2.5s (busy) / 15s (idle)

## Render isolation
- Expensive derived state stays in `useMemo` boundaries in workspace page.
- Future: extract `LiveSnapshotProvider` from `App.tsx`.

## Snapshot hydration
- `hydration_section` on `PredictionRunResponse` surfaces fallback transparency.
- Upcoming never uses `live_player_board` rows.

## Backend (unchanged in this PR unless regression)
- Snapshot build: `backtester/dashboard_runtime.py`
- Eligibility gate may empty upcoming rankings — UI shows warning.

## Metrics to capture before merge
1. Time to first snapshot JSON (Network tab)
2. Time to rankings grid paint
3. Main-thread long tasks during 10s poll tick

Target: no regression vs baseline; document in PR.
