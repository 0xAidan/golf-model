# Phase 0 — Current-State UX Audit

Audit date: 2026-06-09. Baseline branch: `main` before `feat/ui-ux-rebuild`.

## Route inventory

| Route | Purpose | Data source | Notes |
|-------|---------|-------------|-------|
| `/` | Dashboard command center | `live_tournament` / `upcoming_tournament` | Primary operator board |
| `/lab` | Lab command center | `lab_live_tournament` / `lab_upcoming_tournament` | Gated by `VITE_COCKPIT_LAB` |
| `/lab/picks` | Redirect | → `/lab?tab=full-picks` | Legacy alias |
| `/cockpit-lab` | Redirect | → `/lab` | Legacy alias |
| `/players` | Player directory | Player APIs | Standalone |
| `/matchups` | Redirect | → `/?tab=full-picks` | Misleading primary nav item |
| `/grading` | Grading UI | `pick_source=cockpit\|lab\|all` | Records |
| `/track-record` | Track record | Grading history APIs | Records |
| `/research/diagnostics` | Diagnostics | Snapshot + dashboard | Research |
| `/research/legacy-model` | Legacy model | Snapshot | Research |
| `/research/champion-challenger` | Champion/challenger | APIs | Research |

## UX failure evidence

- Three-column cockpit (`CockpitWorkspace`) crams filters, boards, and player spotlight into one viewport.
- Up to eight mobile tabs (Picks, Rankings, Markets, Board, Full picks, Intel, Player).
- Terminal styling (`terminal-monitoring-v3.css`) prioritizes density over readability.
- `/matchups` and `/lab/picks` in primary nav redirect into tab states — confusing IA.
- `App.tsx` (~995 lines) duplicates cockpit/lab workspace prop assembly.

## Data contracts (frozen)

### Dashboard

- Snapshot sections: `live_tournament`, `upcoming_tournament`
- +EV gate: `passesPositiveEv` in `App.tsx` (frontend display filter)
- Pick logging: cockpit/main source
- Grading filter: `pick_source=cockpit`

### Lab

- Snapshot sections: `lab_live_tournament`, `lab_upcoming_tournament` via `mergeLabSnapshotSections`
- Fallback disclosure when lab lane off or partial sections
- Pick logging: `POST /api/lab/log-displayed-picks`
- Grading filter: `pick_source=lab`

### Reliability

- Stale/split-brain: hide boards; show `operator_message`, `data_state`, `split_brain_suspected`
- `LiveSnapshotProvider` uses `keepPreviousData` for poll stability

## Test baseline

| Test file | Covers |
|-----------|--------|
| `App.route-gating.test.tsx` | Route gating, shell render |
| `prediction-workspace-page.test.tsx` | Rankings, picks, past replay |
| `prediction-board.test.ts` | Hydration helpers |
| `lab-snapshot.test.ts` | Lab merge |
| `cockpit-lab-page.test.tsx` | Lab banners |
| `legacy-routes.test.tsx` | Redirects |
| `grading-trust.test.ts` | Grading trust |
| `monitoring-shell-drawer-a11y.test.tsx` | Drawer a11y |

## Screenshot baseline

- Script: `cd frontend && npm run screenshots:matrix:v3`
- Output: `docs/screenshots/ui-overhaul-v3/`
- Note: baselines may be incomplete; matrix must be re-run after rebuild.

## Verification commands (pre-change)

```bash
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
python3 -m pytest tests/ -v --tb=short
```
