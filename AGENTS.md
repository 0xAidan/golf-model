# AGENTS.md

## Cursor Cloud specific instructions

### Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| FastAPI backend | `python3 app.py` | 8000 | Serves API + built React SPA at `/`; API docs at `/docs` |
| Vite dev server | `cd frontend && npm run dev` | 5173 | Proxies `/api` and `/static` to `:8000`; use for frontend dev |

Both services must run simultaneously for full-stack development. Start the backend first.

### Quick reference

- **Python tests:** `python3 -m pytest tests/ -v --tb=short` (~493 tests; full run ~5–6 min on this box)
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

### Standard workflows

See `README.md` for full quick-start and deployment. See `docs/AGENTS_KNOWLEDGE.md` for comprehensive architecture reference.
