# Golf Model — Agent Knowledge Base

Purpose: single, current source of operational truth for coding agents.

Audience: AI agents and maintainers doing implementation or ops work.

Last audited: 2026-06-03 (fresh repo scan + command validation).

## 1) Verified Runtime Truth

Environment checks:

- `python3 --version` -> `3.12.3`
- `python --version` -> command not found
- `node --version` -> `v20.18.2`
- `npm --version` -> `10.8.2`

Validation commands (this audit):

- `.venv/bin/ruff check .` -> pass
- `.venv/bin/python -m pytest tests/ -v --tb=short` -> 477 collected; 475 passed; 1 skipped; 1 failed
- `cd frontend && npm run lint` -> warnings only
- `cd frontend && npm run typecheck` -> pass
- `cd frontend && npm run test` -> fail (`rolldown` native binding missing)
- `cd frontend && npm run build` -> fail (Node < 20.19 plus same `rolldown` binding issue)

Known failing backend test:

- `tests/test_live_refresh_runtime.py::test_live_refresh_snapshot_extremely_stale_triggers_on_demand_even_when_runtime_running`

## 2) High-Level System

- Core app: FastAPI backend + React frontend
- Primary pipeline: Data Golf ingest -> model scoring -> value/matchup detection -> card output
- Research system: walk-forward + Optuna + proposal/model registry lanes
- Storage: SQLite (`data/golf.db`) + markdown/json output artifacts
- Deployment: `deploy.sh` + systemd services on VPS

## 3) Critical Entry Points

- `app.py` -> backend API + serves frontend at `/`
- `run_predictions.py` -> full pipeline execution
- `start.py` -> unified launcher for dashboard/agent/backfill/backtest/research subcommands
- `setup_wizard.py` -> dependency/setup helper (interactive)
- `results.py` -> scoring results
- `dashboard.py` -> CLI performance dashboard/retune helper
- `course.py` -> course profile extraction/list/view

## 4) Repo Map (Operational)

- `src/` -> domain logic, model computations, DB, routes, services
- `backtester/` -> walk-forward, evaluation, research orchestration
- `workers/` -> background daemons
- `frontend/` -> React + Vite app
- `scripts/` -> maintenance, audits, replay, autoresearch tools
- `tests/` -> backend/integration tests
- `docs/` -> runbooks and architecture docs

## 5) Command Baseline

Setup:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run app:

```bash
python3 app.py
```

Run primary checks:

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest tests/ -v --tb=short
cd frontend && npm ci
cd frontend && npm run lint
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
```

## 6) Configuration Surfaces

- `.env` -> secrets and runtime overrides (see `.env.example`)
- `feature_flags.yaml` -> feature toggles
- `profiles.yaml` -> run profiles
- `src/config.py` -> model thresholds, weights, adaptation constants, caps

Rule: tune values in `src/config.py`/config files, not ad-hoc magic numbers.

## 7) Data Flow (Canonical)

1. Resolve event context from Data Golf
2. Sync rounds/predictions/field/odds
3. Compute rolling metrics
4. Build composite model scores
5. Optionally apply AI adjustments
6. Calculate value and matchup bets
7. Apply diversification/exposure logic
8. Persist outputs (`output/*.md`, DB rows, logs)

Primary orchestration path: `src/services/golf_model_service.py`.

## 8) Persistence Contracts (Important Tables)

- Core run data: `tournaments`, `rounds`, `metrics`, `runs`
- Betting records: `picks`, `pick_outcomes`, `results`
- Calibration/research: `prediction_log`, `calibration_curve`, `market_prediction_rows`
- Research lanes: `research_proposals`, `proposal_reviews`, `research_model_registry`, `live_model_registry`
- Live refresh history: `live_snapshot_history`, `market_prediction_rows`, pre-teeoff freeze tables

Reference doc: `docs/data-contracts.md`.

## 9) Autoresearch Reality

- Default posture is cautious/report-first (not blind auto-promotion)
- Primary UI path is Simple Mode scalar workflow
- Reset endpoint archives research state before clearing active lane
- Runtime strategy resolution path favors live lane before research lane fallback

Primary runbook: `docs/autoresearch/RUNBOOK.md`.

## 10) Deployment Truth

Deployment scripts:

- `deploy.sh`
- `scripts/deploy-update-steps.sh`

Common commands:

- `DEPLOY_HOST='root@204.168.147.6' ./deploy.sh --setup`
- `DEPLOY_HOST='root@204.168.147.6' ./deploy.sh --update`
- `cd /opt/golf-model && ./deploy.sh --update-local`
- `DEPLOY_HOST='root@204.168.147.6' ./deploy.sh --status`

Services created/managed:

- `golf-dashboard`
- `golf-agent`
- `golf-live-refresh`
- `golf-backup.timer`

## 11) Known Operational Risks / Gaps

- Frontend test/build currently blocked in this environment due Node/toolchain mismatch and optional native binding resolution.
- One backend test is currently failing (see section 1).
- `run_predictions.py` requires valid Data Golf key; missing key causes early failure.
- `setup_wizard.py` is interactive and can block unattended automation.

## 12) Agent Guardrails

- Do not fabricate env values, endpoints, hostnames, or deployment details.
- Use `python3` explicitly.
- Prefer docs/admin-only edits unless asked for code changes.
- Never use destructive git commands in shared workflows.
- If verification cannot fully run, record exact command, exact error, and precise maintainer follow-up.

## 13) When To Update This File

Update this document whenever any of the following changes:

- entry point behavior or CLI commands
- config/env keys and defaults
- deployment commands/services
- test/lint/build baseline outcomes
- major architecture/data-flow conventions
