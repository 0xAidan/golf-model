# Golf Model Recovery Defect Register

Last updated: 2026-04-13

This register captures the full-codebase unknown-issue sweep for the recovery program.
Priorities are scoped to this project's trust goals (correct picks, reliable live runtime, safe deploy).

## P0 (must-fix before trust cutover)

1. Deploy pre-update backup checks the wrong DB path (`golf_model.db` vs `data/golf.db`).
   - Files: `deploy.sh`, `src/db.py`
   - Risk: no backup before deploy updates.
2. Deploy status checks wrong DB path and can misreport DB missing.
   - Files: `deploy.sh`
   - Risk: false operational confidence.
3. Dual live-refresh ownership (app lifespan + systemd worker) can run concurrent loops.
   - Files: `app.py`, `workers/live_refresh_worker.py`, `deploy.sh`, `src/live_refresh_policy.py`
   - Risk: duplicate API load, snapshot write races, stale/inconsistent runtime state.
4. Past-event UI mode is non-functional but appears selectable.
   - Files: `frontend/src/App.tsx`
   - Risk: operator believes they are reviewing a past event while reading live/current data.

## P1 (high)

1. Silent fallback to default strategy when active strategy JSON parsing fails.
   - Files: `backtester/experiments.py`, `backtester/model_registry.py`
2. Non-atomic live snapshot writes can produce torn JSON reads.
   - Files: `backtester/dashboard_runtime.py`
3. Dashboard runtime launched with `--reload` in production.
   - Files: `start.py`, `deploy.sh`
4. Picks insert path can violate unique constraint on reruns.
   - Files: `app.py`, `src/db.py`
5. Critical run metadata logging failures swallowed silently.
   - Files: `src/services/golf_model_service.py`
6. Live rankings field enforcement still allows invalid rows and permissive fallbacks.
   - Files: `src/db.py`, `src/field_selection.py`
7. Frontend hides query failures and stale/fallback snapshot state.
   - Files: `frontend/src/App.tsx`, `frontend/src/lib/types.ts`

## P2 (medium)

1. Tournament identity can drift (ingest context vs recompute detection).
   - Files: `backtester/dashboard_runtime.py`, `src/services/live_snapshot_service.py`
2. Tournaments table lacks uniqueness guard (duplicate event rows possible).
   - Files: `src/db.py`
3. CI lacks frontend build/lint gates.
   - Files: `.github/workflows/ci.yml`, `frontend/package.json`
4. FastAPI lifespan behavior not covered by tests.
   - Files: `tests/`

## P3 (low)

1. Non-critical worker paths swallow exceptions and overstate counters.
   - Files: `workers/intel_harvester.py`
2. Operational docs and deploy defaults drift.
   - Files: `docs/AGENTS_KNOWLEDGE.md`, `deploy.sh`

## Acceptance Criteria per defect

Each fix must include:
- Code change and explicit test (unit/integration) when practical.
- Before/after validation evidence in recovery run notes.
- No regression in existing tests and lint checks.
