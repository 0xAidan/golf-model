# Frontend UI/UX Rebuild (2026-06)

Staged rebuild replacing the cramped three-column cockpit with a picks-first product command center.

## Docs

| Doc | Phase |
|-----|-------|
| [00-audit.md](./00-audit.md) | Phase 0 — baseline audit |
| [01-ia-and-routes.md](./01-ia-and-routes.md) | Phase 1 — IA and routes |

## Primary navigation

- **Dashboard** `/` — production model command center
- **Lab** `/lab` — research model lane
- **Players** `/players`
- **Results** `/results` — grading + track record (aliases: `/grading`, `/track-record`)
- **System** `/system` — diagnostics + data health (alias: `/research/diagnostics`)

## Key frontend paths

- Product components: `frontend/src/components/product/`
- Lane trust helper: `frontend/src/features/model-workspace/use-lane-trust.ts`
- Dashboard workspace: `frontend/src/components/monitoring/dashboard/prediction-workspace-page.tsx`
- Results hub: `frontend/src/pages/results-page.tsx`
- System hub: `frontend/src/pages/system-page.tsx`
- Shell nav: `frontend/src/components/monitoring/monitoring-shell.tsx`
- Product CSS: `frontend/src/styles/product-shell.css`

## Verification

```bash
cd frontend && npm run typecheck && npm run test && npm run build
python3 -m pytest tests/ -v --tb=short
```
