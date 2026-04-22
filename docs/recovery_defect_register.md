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
3. Dual live-refresh ownership (app lifespan + systemd worker) can run concurrent loops. **[FIXED — Q10, PR fix/live-refresh-single-owner]**
   - Files: `app.py`, `workers/live_refresh_worker.py`, `deploy.sh`, `src/live_refresh_policy.py`
   - Risk: duplicate API load, snapshot write races, stale/inconsistent runtime state.
   - Resolution: `LIVE_REFRESH_EMBEDDED_AUTOSTART` default flipped from `1` to `0`; systemd worker is sole owner. Worker writes `/tmp/golf_live_refresh.pid` (override via `LIVE_REFRESH_PIDFILE`); the lifespan hook skips and logs WARNING if the pidfile points to a live process. Opt-in embedded autostart emits a LOUD WARNING. See `tests/test_live_refresh_ownership.py`. Out-of-scope follow-up: worker pidfile cleanup on uncaught crash.
4. Past-event UI mode is non-functional but appears selectable.
   - Files: `frontend/src/App.tsx`
   - Risk: operator believes they are reviewing a past event while reading live/current data.

## P1 (high)

1. Silent fallback to default strategy when active strategy JSON parsing fails.
   - Files: `backtester/experiments.py`, `backtester/model_registry.py`
2. Non-atomic live snapshot writes can produce torn JSON reads. **FIXED** (defect 2.3.6; see PR `fix/atomic-snapshot-writes`).
   - Files: `backtester/dashboard_runtime.py`, `src/atomic_io.py`
   - Resolution: snapshot writes now go through `src.atomic_io.atomic_write_json`, which writes to a sibling temp file in the same directory, fsyncs, then `os.replace`s onto the final path and fsyncs the parent directory. A mid-write crash leaves either the previous file or no file — never a partial/corrupt one. Tests in `tests/test_atomic_io.py` cover happy path, mid-write failure preservation, and concurrent writers.
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
3. CI lacks frontend build/lint gates. — **FIXED (Q3)**
   - Files: `.github/workflows/ci.yml`, `frontend/package.json`
   - CI now runs `npm ci`, `npm run lint`, `npm run typecheck`, and `npm run build` against the frontend on every push and pull request. A `typecheck` script (`tsc -b --noEmit`) was added to `frontend/package.json`. Pre-existing lint violations (unused imports, implicit `any`, a setState-in-effect) were cleaned up to land the gate green without weakening any rules.
4. FastAPI lifespan behavior not covered by tests.
   - Files: `tests/`

## P3 (low)

1. Non-critical worker paths swallow exceptions and overstate counters.
   - Files: `workers/intel_harvester.py`
2. Operational docs and deploy defaults drift.
   - Files: `docs/AGENTS_KNOWLEDGE.md`, `deploy.sh`

## Q (performance / query tuning)

1. (reserved)
2. (reserved)
3. (reserved)
4. Missing composite indexes cause full scans on hot-path queries.
   - Files: `src/db.py`, `tests/test_db_indexes.py`
   - Indexes added: `idx_rounds_player_event` on `rounds(player_key, event_completed)`,
     `idx_metrics_tourn_player_cat` on `metrics(tournament_id, player_key, metric_category)`,
     `idx_historical_odds_event_book_ts` on `historical_odds(event_id, book, year)`
     (historical_odds has no explicit `ts` column; `year` is the available temporal key).
   - Status: **FIXED** — PR `perf/db-indexes` (Q4). Idempotent migration via
     `_ensure_hot_path_indexes()`; schema unchanged, data untouched.

## Quality / DX defects

- Q6 (FIXED 2026-04-22): LLM prompts were multi-line f-strings embedded in
  `src/prompts.py`, which made review, diffs, and A/B testing painful. Templates
  are now externalized to `prompts/v1/*.md` and loaded via
  `src.prompts.load_prompt(name, version="v1")`. Public function signatures are
  unchanged and output is bit-for-bit identical — see
  `tests/test_prompts_externalized.py`. Future prompt revisions land in
  `prompts/v2/` side-by-side so A/B comparisons need no code change.
  - Files: `src/prompts.py`, `prompts/v1/*.md`, `tests/test_prompts_externalized.py`,
    `pyproject.toml`, `MANIFEST.in`

## Acceptance Criteria per defect

Each fix must include:
- Code change and explicit test (unit/integration) when practical.
- Before/after validation evidence in recovery run notes.
- No regression in existing tests and lint checks.
