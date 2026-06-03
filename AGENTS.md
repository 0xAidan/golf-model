# AGENTS.md

## Cursor Agent Operational Notes

### Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| FastAPI backend | `python3 app.py` | 8000 | Serves API + built frontend (if present) at `/`; docs at `/docs` |
| Vite dev server | `cd frontend && npm run dev` | 5173 | Use for frontend development; backend should already be running |

For full-stack local work, run both services (backend first).

### Environment Bootstrap

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Why this matters:

- `python` command is unavailable here; use `python3`.
- System-level pip install may fail with "externally managed environment" (PEP 668), so virtualenv is the default path.

### Verification Commands

Backend:

- `.venv/bin/ruff check .`
- `.venv/bin/python -m pytest tests/ -v --tb=short`

Frontend:

- `cd frontend && npm ci`
- `cd frontend && npm run lint`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run test`
- `cd frontend && npm run build`

### Current Known Results (2026-06-03 audit)

- Backend lint: passes (`ruff check .`)
- Backend tests: 477 collected, 1 known failure:
  - `tests/test_live_refresh_runtime.py::test_live_refresh_snapshot_extremely_stale_triggers_on_demand_even_when_runtime_running`
- Frontend lint: warnings only (no blocking errors)
- Frontend typecheck: passes
- Frontend test/build currently blocked in this environment by:
  - Node `20.18.2` (toolchain expects `20.19+`)
  - missing `rolldown` native binding package (`@rolldown/binding-linux-x64-gnu`)

### Practical Gotchas

- `.env` is required for real pipeline runs; without a real `DATAGOLF_API_KEY`, sync/pipeline operations fail.
- SQLite (`data/golf.db`) is local and auto-created.
- Production uses dedicated worker service for live refresh (`workers/live_refresh_worker.py`); local dev can run without separately launching it.

### References

- `README.md` for contributor onboarding
- `docs/AGENTS_KNOWLEDGE.md` for architecture, workflows, and conventions
