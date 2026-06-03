# About This Project

## What it is

Golf Model is a golf prediction and betting research platform.

It combines:

- live and pre-tournament data ingestion,
- model scoring (course fit, form, momentum),
- value and matchup edge detection,
- a web dashboard for operators,
- a research loop for strategy improvement.

## Why it exists

The project is designed to reduce manual weekly betting workflow.

Instead of repeatedly running one-off scripts by hand, the system can keep data and snapshots fresh, expose current model output through the API/UI, and keep historical records for grading and learning.

## Main building blocks

- **Backend API/UI host:** `app.py` (FastAPI)
- **Prediction pipeline:** `run_predictions.py` + `src/services/golf_model_service.py`
- **Research/backtesting:** `backtester/`
- **Background workers:** `workers/`
- **Frontend app:** `frontend/` (React + Vite)
- **Persistence:** SQLite (`data/golf.db`)

## Runtime model

Typical production setup runs separate processes:

- `golf-dashboard` (web/API)
- `golf-agent` (research worker)
- `golf-live-refresh` (continuous refresh worker)

These are managed by `systemd` through `deploy.sh`.

## Who this is for

- Operators who want weekly model output and diagnostics
- Builders who want a research/test loop before promoting strategy changes
- Contributors who need a reproducible local/dev/deploy workflow

## Where to start

- `README.md` for setup and command basics
- `AGENTS.md` for quick operational notes
- `docs/AGENTS_KNOWLEDGE.md` for detailed architecture and conventions
