# AGENTS.md

## Cursor Cloud specific instructions

### Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| FastAPI backend | `python3 app.py` | 8000 | Serves API + built React SPA at `/`; API docs at `/docs` |
| Vite dev server | `cd frontend && npm run dev` | 5173 | Proxies `/api` and `/static` to `:8000`; use for frontend dev |

Both services must run simultaneously for full-stack development. Start the backend first.

### Quick reference

- **Python tests:** `python3 -m pytest tests/ -v --tb=short` (~683 tests; full run ~75s on this box). 4 tests are known to fail on a clean checkout regardless of environment (see Gotchas) — do not treat them as setup breakage.
- **Python lint:** `ruff check .` (pre-existing lint issues in `app.py` and `run_predictions.py` are known; do not fix unless explicitly asked)
- **Frontend lint:** `cd frontend && npm run lint` (pre-existing ESLint errors in `legacy-routes.tsx` are known)
- **Frontend typecheck:** `cd frontend && npm run typecheck`
- **Frontend tests:** `cd frontend && npm run test` (34 files, 121 tests)
- **Frontend build:** `cd frontend && npm run build` (outputs to `frontend/dist/`)
- **Frontend a11y (Playwright):** `cd frontend && npm run test:a11y` (axe on `/` and `/lab`, 0 critical)
- **Frontend bundle budget:** `cd frontend && npm run build && npm run bundle:budget`

### Gotchas

- `python` is not available, use `python3` explicitly.
- pip installs to `~/.local/bin` which may not be on PATH. Ensure `export PATH="$HOME/.local/bin:$PATH"` is in effect before running `pytest`, `ruff`, or `uvicorn`.
- The `.env` file is required for the backend to start (even with a placeholder `DATAGOLF_API_KEY`). Without a real API key, the pipeline/sync endpoints will fail, but the dashboard and tests still work.
- SQLite database `data/golf.db` is auto-created at runtime; no external database needed.
- The live-refresh worker (`workers/live_refresh_worker.py`) is a separate daemon for production. For local dev, the FastAPI app handles everything — do not run the worker unless specifically testing it.
- Frontend build chunk warning (>500KB) is expected and harmless.
- `ruff` is not in `requirements.txt` (installed separately; the startup update script pins `ruff==0.8.6` to match `.pre-commit-config.yaml`). CI installs it via `pip install ruff`.
- Known pre-existing pytest failures (present on a clean checkout, not env-related; do not "fix" as part of setup): `tests/test_live_refresh_runtime.py::test_live_refresh_snapshot_endpoint_generates_snapshot_on_demand` and three `tests/test_simple_dashboard.py` grading/track-record tests (`test_grading_history_summary_splits_1u_record_by_market_without_result_fanout`, `test_grading_history_coalesces_event_id_from_rounds_when_tournament_null`, `test_track_record_endpoint_returns_pick_details_with_edge_and_lane`). The track-record one is a test-data-vs-schema `picks` UNIQUE-constraint mismatch.
- The backend serves the built SPA from `frontend/dist/`. For frontend dev use the Vite dev server (`npm run dev`, port 5173, proxies to :8000). To serve the integrated SPA at `:8000` you must run `cd frontend && npm run build` once (the startup update script intentionally does not build).

### Standard workflows

See `README.md` for full quick-start and deployment. See `docs/AGENTS_KNOWLEDGE.md` for comprehensive architecture reference.
