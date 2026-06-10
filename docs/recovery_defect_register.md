# Golf Model Recovery Defect Register

Last updated: 2026-06-10 (engine-scale Wave 1 PR 1b defect burn-down)

This register captures the full-codebase unknown-issue sweep for the recovery program.
Priorities are scoped to this project's trust goals (correct picks, reliable live runtime, safe deploy).

## P0 (must-fix before trust cutover)

1. **FIXED** — Deploy pre-update backup checked the wrong DB path (`golf_model.db` vs `data/golf.db`).
   - Files: `deploy.sh`, `src/backup.py`, `src/db.py`
   - Resolution: PR #48 (`fix/deploy-authoritative-db-path`). `src/backup.py` exposes `--print-path`/`--print-backup-dir` returning the live `src.db.DB_PATH`. `deploy.sh` queries the venv Python for the authoritative path on every `update`/`status` run, with a `$DEPLOY_PATH/data/golf.db` fallback for first-boot.
2. **FIXED** — Deploy status checks wrong DB path and could misreport DB missing.
   - Files: `deploy.sh`
   - Resolution: same PR #48 — status check now logs the resolved path on every invocation.
3. **FIXED** — Dual live-refresh ownership (app lifespan + systemd worker) could run concurrent loops.
   - Files: `app.py`, `workers/live_refresh_worker.py`, `deploy.sh`, `src/live_refresh_policy.py`
   - Resolution: Q10 / PR `fix/live-refresh-single-owner`. `LIVE_REFRESH_EMBEDDED_AUTOSTART` default flipped from `1` to `0`; systemd worker is sole owner. Worker writes `/tmp/golf_live_refresh.pid` (override via `LIVE_REFRESH_PIDFILE`); the lifespan hook skips and logs WARNING if the pidfile points to a live process. Opt-in embedded autostart emits a LOUD WARNING. See `tests/test_live_refresh_ownership.py`. Out-of-scope follow-up: worker pidfile cleanup on uncaught crash.
4. **FIXED** — Past-event UI mode was non-functional but appeared selectable.
   - Files: `frontend/src/App.tsx`, `backtester/dashboard_runtime.py`
   - Resolution: PR #64 (`fix/cockpit-past-events`). Past-events selector excludes currently-active live/upcoming event ids and resolves event names from the most recent snapshot row (correlated subquery on `generated_at`) instead of `MAX(source_event_name)` alphabetical. Upcoming events no longer leak into the PAST tab mislabeled as the prior season's event.

## P1 (high)

1. **FIXED** (Wave 1 PR 1b) — Silent fallback to default strategy when active strategy JSON parsing fails.
   - Files: `backtester/experiments.py`, `backtester/model_registry.py`, `src/runtime_health.py`, `app.py`
   - Resolution: both parse-failure sites (`experiments.get_active_strategy`, `model_registry._strategy_from_json`) now record a non-fatal degradation into `src/runtime_health.py`. `GET /api/ops/health` surfaces `strategy_config_errors` and flips its summary to `strategy_config_fallback` (still `ok=True` — a safe default strategy is served, but the fallback is no longer invisible). Test: `tests/test_runtime_health.py`.
2. **FIXED** — Non-atomic live snapshot writes could produce torn JSON reads (defect 2.3.6; PR `fix/atomic-snapshot-writes`).
   - Files: `backtester/dashboard_runtime.py`, `src/atomic_io.py`
   - Resolution: snapshot writes go through `src.atomic_io.atomic_write_json`, which writes to a sibling temp file in the same directory, fsyncs, then `os.replace`s onto the final path and fsyncs the parent directory. A mid-write crash leaves either the previous file or no file — never a partial/corrupt one. Tests in `tests/test_atomic_io.py` cover happy path, mid-write failure preservation, and concurrent writers.
3. **FIXED** (Wave 1 PR 1b) — Dashboard runtime could launch with `--reload` in production.
   - Files: `start.py`, `tests/test_start_research.py`
   - Resolution: `cmd_dashboard` (the production systemd path) already defaulted reload OFF (opt-in via `UVICORN_RELOAD`). Added a production guard that suppresses `--reload` even if `UVICORN_RELOAD=1` leaks into a prod `.env`, detected via `LIVE_REFRESH_WORKER_OWNED=1` / `GOLF_APP_ROOT=/opt/golf-model`. Tests: `test_cmd_dashboard_suppresses_reload_in_production`, `test_cmd_dashboard_allows_reload_in_dev`.
4. **FIXED** (Wave 1 PR 1b) — Picks insert path could violate unique constraint on reruns.
   - Files: `src/db.py`, `tests/test_db.py`
   - Resolution: verified-closed. Both pick writers (`GolfModelService._store_displayed_picks`, `persist_lab_logged_picks`) route through `db.store_picks`, which uses `INSERT OR IGNORE` against `idx_picks_unique`. Extended `test_store_picks_dedupes_within_lane_but_allows_cross_lane` to assert repeated separate-call reruns stay idempotent and never raise.
5. **FIXED** (Wave 1 PR 1b) — Critical run metadata logging failures swallowed silently.
   - Files: `src/services/golf_model_service.py`, `src/runtime_health.py`
   - Resolution: `_log_run` now attaches `result["run_logging_error"]` (visible to API callers) and records a `run_logging_error` degradation in `runtime_health`, instead of only emitting a log line.
6. Live rankings field enforcement still allows invalid rows and permissive fallbacks. **OPEN — deferred from Wave 1 PR 1b (deliberate).**
   - Files: `src/db.py`, `src/field_selection.py`
   - Note: tightening field enforcement to fail-closed risks emptying live boards if mis-scoped, which conflicts with the "do not break live boards" non-negotiable. Deferred to a dedicated change with a representative-field regression fixture rather than a blind tightening.
7. Frontend hides query failures and stale/fallback snapshot state. **PARTIAL** (Q5 snapshot-age chip landed; per-query error surfacing still pending — carried forward, not addressed in PR 1b).
   - Files: `frontend/src/App.tsx`, `frontend/src/lib/types.ts`
8. **FIXED** (Wave 1 PR 1b) — Book filter (restrict visible plays to selected sportsbooks) regressed out of reach in the PR #145 rebuild (operator-reported).
   - Files: `frontend/src/components/product/model-filter-toolbar.tsx`, `frontend/src/lib/prediction-board.ts`, `frontend/src/components/monitoring/dashboard/prediction-workspace-page.tsx`, `frontend/src/App.tsx`
   - Resolution: `ModelFilterToolbar` is now interactive (book chips + min-edge + player search) and renders directly with the Actionable plays section on `/` and `/lab`, not buried in a non-default tab. Available books are sourced via `collectBooksForFilter` (union of run rows + snapshot `diagnostics.books_seen`, falling back to `SUPPORTED_BOOKS`) so chips render even with zero qualifying edges. Filtering logic was already intact. Tests: `frontend/src/components/product/model-filter-toolbar.test.tsx`.
9. **FIXED** (Wave 1 PR 1b) — Two API routes (`/api/players/{key}/standalone-profile`, `/api/players/search`) and the startup cache warmer were defined *after* the `if __name__ == "__main__"` block in `app.py`, so they never registered under `python3 app.py` (the documented dev entry) — silently 404ing.
   - Files: `app.py`, `tests/test_simple_dashboard.py`
   - Resolution: moved the `__main__`/`uvicorn.run` block to the end of the module. Guard test `test_late_registered_player_routes_are_registered` asserts both routes are registered.

## P2 (medium)

1. Tournament identity can drift (ingest context vs recompute detection). **OPEN**
   - Files: `backtester/dashboard_runtime.py`, `src/services/live_snapshot_service.py`
2. Tournaments table lacks uniqueness guard (duplicate event rows possible). **OPEN**
   - Files: `src/db.py`
3. **FIXED (Q3)** — CI lacks frontend build/lint gates.
   - Files: `.github/workflows/ci.yml`, `frontend/package.json`
   - CI runs `npm ci`, `npm run lint`, `npm run typecheck`, and `npm run build` against the frontend on every push and pull request. A `typecheck` script (`tsc -b --noEmit`) was added to `frontend/package.json`. Pre-existing lint violations cleaned up to land the gate green without weakening any rules.
4. FastAPI lifespan behavior not covered by tests. **OPEN**
   - Files: `tests/`

## P3 (low)

1. Non-critical worker paths swallow exceptions and overstate counters. **OPEN**
   - Files: `workers/intel_harvester.py`
2. Operational docs and deploy defaults drift. **OPEN**
   - Files: `docs/AGENTS_KNOWLEDGE.md`, `deploy.sh`

## Q (performance / query tuning / quality)

- Q3 — see P2 #3 above.
- Q4 (FIXED) — Missing composite indexes caused full scans on hot-path queries.
  - Files: `src/db.py`, `tests/test_db_indexes.py`
  - Indexes added: `idx_rounds_player_event` on `rounds(player_key, event_completed)`, `idx_metrics_tourn_player_cat` on `metrics(tournament_id, player_key, metric_category)`, `idx_historical_odds_event_book_ts` on `historical_odds(event_id, book, year)` (historical_odds has no explicit `ts` column; `year` is the available temporal key).
  - Status: PR `perf/db-indexes` (Q4). Idempotent migration via `_ensure_hot_path_indexes()`; schema unchanged, data untouched.
- Q5 (FIXED) — Snapshot-age / data-source chip globally visible.
  - Files: `backtester/dashboard_runtime.py`, `frontend/src/components/snapshot-chip.tsx`, `frontend/src/App.tsx`
  - Snapshot payload carries `generated_at` and a new `data_source` (`live` | `replay` | `fixture`). A `<SnapshotChip />` mounted in the global app shell shows age (`12s ago`, `14m ago`, `stale (>60m)`) and the source label, updating every second client-side with green/amber/red tone thresholds at 30m/60m.
- Q6 (FIXED 2026-04-22) — LLM prompts externalized.
  - Files: `src/prompts.py`, `prompts/v1/*.md`, `tests/test_prompts_externalized.py`, `pyproject.toml`, `MANIFEST.in`
  - Templates loaded via `src.prompts.load_prompt(name, version="v1")`. Public function signatures unchanged and output is bit-for-bit identical. Future revisions land in `prompts/v2/` side-by-side.
- Q7 (FIXED 2026-04-22) — Legacy Jinja UI removed.
  - `templates/index.html`, `static/` directory removed.
  - FastAPI routes `/legacy` and `/legacy-classic` removed; `/static` mount removed.
  - Inline `HTML_PAGE` / `SIMPLE_HTML_PAGE` fallbacks removed from `app.py`.
  - React SPA (`frontend/dist/`) is the sole UI served at `/`.
- Q8 (FIXED 2026-04-22) — Minimum-viable end-to-end pipeline integration test.
  - Files: `tests/integration/__init__.py`, `tests/integration/test_pipeline_e2e.py`, `tests/integration/fixtures/players.json`, `tests/integration/fixtures/odds.json`, `pyproject.toml` (registers the `integration` marker).
  - Synthetic field exercises DB seed → `compute_composite` → matchup-first value path → snapshot JSON write. Asserts the `BEST_BETS_MATCHUP_ONLY` invariant. Deterministic — zero network I/O. Runtime ~1–2 s, well under the 15 s budget.
  - Out of scope: full `GolfModelService.run_analysis` orchestration, AI narrative path, 3-ball value bets, card / methodology Markdown generation.
- Q9 (FIXED 2026-04-27) — Picks tab unification + diagnostics surfacing.
  - Files: `frontend/src/pages/picks-page.tsx`, `frontend/src/components/cockpit/secondary-board.tsx`, `frontend/src/lib/prediction-board.ts`, `frontend/src/lib/types.ts`, `backtester/dashboard_runtime.py`
  - PR #65 unified Picks behind one tab with sub-tabs (Matchups / Secondary / Best Bets) and routed Cockpit Secondary scrolling through the shared board. PR #66 fixed the `Books=0` diagnostics field that was being dropped on the way to the frontend (both live and upcoming pipelines), captured `failed_candidates` from `matchup_value.py` into the response payload, and added a "Show all candidates" toggle on the Picks Matchups sub-tab so the operator can see gated rows with reason codes (below-EV, DG-disagreement, etc).
- Q11 (FIXED 2026-04-28) — Secondary-market labels collapsed all bets to `MISPRICED`.
  - Files: `frontend/src/pages/page-shared.tsx`
  - The `secondaryBadgeLabel` helper previously returned `"mispriced"` / `"placement"` / `"miss-cut"` for every market, so the Picks Secondary tab grouped Outright, FRL, Top 5, Top 10, Make Cut etc. all under a single `MISPRICED` header. Rewrite maps the canonical backend keys (`outright`, `win`, `winner`, `frl`, `top5`/`top_5`, `top10`/`top_10`, `top20`, `top30`, `top40`, `make_cut`, `miss_cut`) to readable labels, with a `top[_\s-]?(\d+)` regex fallback and a last-resort title-case so we never lose information silently.
- Q12 (FIXED 2026-04-28) — Frontend cleanup pack.
  - Files: `frontend/src/pages/legacy-routes.tsx`, `frontend/src/pages/players-page.tsx`
  - Removed orphaned `MatchupsPage` (~138 lines) plus its unused imports (`MatchupBet`, `buildMatchupKey`) and helper components (`EV`, `TierBadge`) from `legacy-routes.tsx`. The legacy `/matchups` route was already de-listed; this removes the dead code so future readers don't mistake it for the live path. Wrapped `searchResults` in `useMemo` in `players-page.tsx` to silence the `react-hooks/exhaustive-deps` warning that the new CI typecheck/lint gates would otherwise have to ignore.
- Q10 — see P0 #3 above.

## Cleanup (Q-series)

- Q7: see above.

## 3. Phase 2 Enablement

### 3.3 Evaluation infrastructure

#### 3.3.1 Champion-challenger dashboard — FIXED

- Files: `src/config.py`, `src/models/base.py`, `src/db.py`, `src/evaluation/*.py`, `src/matchup_value.py`, `src/routes/champion_challenger.py`, `frontend/src/pages/champion-challenger-page.tsx`, `frontend/src/components/shell.tsx`, `tests/test_champion_challenger.py`.
- Rails that let Phase 2 challengers (T1 shot-level SG, T2 Monte Carlo) be evaluated on Brier / matchup ROI / CLV against the live champion (v4.2) without ever pricing live bets. Champion pipeline output is byte-identical to pre-rails main; verified by a golden SHA-256 hash test on `matchup_value._find_matchup_value_bets_core`. Challenger failures are caught + logged WARNING and never break the pipeline. `CHALLENGERS` is empty by default.

## Open follow-ups (added 2026-04-28)

- Frontend bundle size: Vite warns at 1,622 kB (514 kB gzipped). Code-split Players, Course, and Champion-Challenger routes via `React.lazy` + `Suspense` in `frontend/src/App.tsx`. (Tracked in current branch `chore/cleanup-and-codesplit`.)
- Pre-existing frontend test failures (6): `player-profile-sections`, `player-spotlight`, `/players` route gate, `cockpit/workspace.test.tsx` blueprint tests. Not introduced by recent work; baseline failures.
- Server-side `frontend/dist/index.html` drift on each deploy: the file is committed to repo by design but the server's `npm run build` rewrites it, causing `git pull` conflicts. Mitigation today: `git checkout -- frontend/dist/index.html` before `git pull origin main` on the server. Longer-term: either stop committing `frontend/dist/index.html` (verify no other consumer first) or add a server-side `--assume-unchanged` / smudge filter.

## Acceptance Criteria per defect

Each fix must include:
- Code change and explicit test (unit/integration) when practical.
- Before/after validation evidence in recovery run notes.
- No regression in existing tests and lint checks.
