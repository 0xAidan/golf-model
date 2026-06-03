# Golf Model

Production-oriented golf modeling platform with a FastAPI backend, React dashboard, live snapshot refresh, and research/backtesting workflows.

For a plain-English product summary, see `ABOUT.md`.

## What This Repo Does

- Pulls Data Golf data (field, rounds, predictions, rankings, odds)
- Computes model scores (course fit + form + momentum)
- Prices value bets and matchup edges
- Serves dashboard + API from `app.py`
- Runs autoresearch and walk-forward evaluation tooling
- Stores model history and artifacts in SQLite + markdown/json outputs

## Requirements

- Python `3.11+` (verified here on `3.12.3`)
- Node `20.19+` or `22.12+` for modern Vite toolchain
- npm (verified here on `10.8.2`)
- `.env` file (copy from `.env.example`)

Required env key:

- `DATAGOLF_API_KEY` (real key required for live pipeline/data sync)

Optional keys:

- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ODDS_API_KEY`
- `AI_BRAIN_PROVIDER`, `OPENAI_MODEL`, `LIVE_REFRESH_LAB_PROFILE_ENABLED`, others in `.env.example`

## Quick Start (Copy/Paste)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 app.py
```

Open:

- `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

Notes:

- Use `python3` (this environment has no `python` alias).
- On Debian/Ubuntu, global `pip install` may fail with PEP 668 ("externally managed"); virtualenv avoids that.

## Common Commands

Backend:

```bash
. .venv/bin/activate
python3 app.py
python3 start.py --help
python3 run_predictions.py
python3 results.py --tournament "Masters Tournament" --score-only
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
```

## Verified Status (Audit: 2026-06-03)

From this audit run:

- `python3` exists; `python` does **not**
- `.venv/bin/ruff check .` passes
- `.venv/bin/python -m pytest tests/ -v --tb=short` collects 477 tests, with:
  - `475 passed`
  - `1 skipped`
  - `1 failed` (`tests/test_live_refresh_runtime.py::test_live_refresh_snapshot_extremely_stale_triggers_on_demand_even_when_runtime_running`)
- `frontend`:
  - `npm run lint` returns warnings only (no lint errors)
  - `npm run typecheck` passes
  - `npm run test` and `npm run build` fail in this environment because Node is `20.18.2` (below required `20.19+`) and `rolldown` native binding is missing

## Local Full-Stack Dev

Run backend + Vite in separate terminals:

```bash
# terminal 1
. .venv/bin/activate
python3 app.py
```

```bash
# terminal 2
cd frontend
npm run dev
```

Default ports:

- FastAPI: `8000`
- Vite: `5173`

## Deployment

Primary script: `deploy.sh`

```bash
# first-time setup from local machine
DEPLOY_HOST='root@<server-ip>' ./deploy.sh --setup

# update from local machine
DEPLOY_HOST='root@<server-ip>' ./deploy.sh --update

# update while already SSH'd into server
cd /opt/golf-model && ./deploy.sh --update-local

# status
DEPLOY_HOST='root@<server-ip>' ./deploy.sh --status
```

Services managed by deploy script:

- `golf-dashboard`
- `golf-agent`
- `golf-live-refresh`
- `golf-backup.timer`

## Repo Map (Short)

- `app.py` — FastAPI app + dashboard API
- `run_predictions.py` — full prediction pipeline CLI
- `start.py` — unified launcher CLI
- `src/` — model, DB, value logic, routes, services
- `backtester/` — walk-forward/research runtime
- `workers/` — background daemons
- `frontend/` — React + Vite dashboard
- `docs/` — runbooks, architecture notes, research docs

## More Documentation

- `AGENTS.md` — quick operational commands/caveats
- `docs/AGENTS_KNOWLEDGE.md` — deep architecture + conventions
- `docs/autoresearch/RUNBOOK.md` — autoresearch operator flow
- `docs/data-contracts.md` and `docs/storage-retention.md` — data/retention references

## License

Private repository. Not for redistribution.
