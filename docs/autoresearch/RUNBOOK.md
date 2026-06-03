# Autoresearch Runbook

Operator-focused guide for running the autoresearch system safely.

## 1) Before You Start

1. Create and activate virtualenv:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

2. Ensure `.env` exists and includes at least `DATAGOLF_API_KEY` for live data sync.
3. Ensure SQLite has enough historical data for meaningful evaluation:
   - `rounds`
   - `pit_rolling_stats`
   - `historical_odds`
   - `historical_matchup_odds`

If data health is weak, results can look "good" but be unreliable.

## 2) Operating Modes (UI)

- **Simple Mode (default/recommended):**
  - Uses scalar Optuna workflow
  - Objective defaults to `weighted_roi_pct`
  - Report-only by default (does not blindly auto-ship)
- **Lab Mode:**
  - Advanced controls for engine mode, studies, and low-level options

## 3) Engine Modes

- `research_cycle`: bounded proposal-driven evaluation path
- `optuna`: multi-objective Pareto exploration
- `optuna_scalar`: single objective (`blended_score` or `weighted_roi_pct`)

Primary API endpoints:

- `POST /api/autoresearch/start`
- `POST /api/autoresearch/stop`
- `GET /api/autoresearch/status`
- `POST /api/autoresearch/run-once`
- `GET /api/autoresearch/study`
- `POST /api/autoresearch/reset`

Simple Mode endpoints:

- `POST /api/simple/autoresearch/start`
- `POST /api/simple/autoresearch/stop`
- `POST /api/simple/autoresearch/run-once`
- `GET /api/simple/autoresearch/status`

## 4) Safe Operating Rules

- Do not intentionally run duplicate autoresearch drivers at once.
- Keep one controlling process path at a time (dashboard-driven path is usually enough).
- Treat "blocked" candidate outcomes as normal guardrail behavior, not automatic system failure.

## 5) Guardrails

Guardrail thresholds come from:

- `src/config.py` (`get_autoresearch_guardrail_params`)
- optional overrides in `data/autoresearch_settings.json`
- optional env overrides (`AUTORESEARCH_GUARDRAIL_*`)

Common block reasons:

- insufficient sample size
- CLV regression
- calibration regression
- drawdown regression

## 6) Reset Behavior

`POST /api/autoresearch/reset` performs archive-first reset.

Archived to:

- `output/research/archive/<timestamp>/`

Archived content includes:

- `research_proposals`, `proposal_reviews`, `research_model_registry` lane data
- `output/research/` artifacts and study files
- `data/autoresearch_settings.json`

What stays active:

- live prediction lane (`live_model_registry`)
- experiments/active strategy lane

## 7) Promotion Reality

- Passing research metrics does not mean immediate production promotion.
- Production lane promotion is separate and should follow project charter gates.
- Runtime resolution order is still: live weekly model -> research champion -> active strategy -> default.

## 8) Useful CLI Helpers

```bash
. .venv/bin/activate
python3 scripts/run_autoresearch_optuna.py --n-trials 10 --years 2024,2025
python3 scripts/run_autoresearch_optuna.py --scalar --scalar-metric weighted_roi_pct --n-trials 10 --years 2024,2025
python3 scripts/run_autoresearch_eval.py
python3 scripts/run_autoresearch_loop.py --iterations 5 --timeout-seconds 120
```

## 9) Troubleshooting

- If dashboard on port `8000` is already running, stop duplicate server first.
- If outputs look empty, inspect `GET /api/autoresearch/status` and data-health fields.
- If results are unstable, reduce scope to fewer years/events and inspect diagnostics first.

## 10) Related Docs

- `docs/AGENTS_KNOWLEDGE.md`
- `docs/autoresearch/evaluation_contract.md`
- `docs/research/research_program.md`
- `.cursor/rules/project-charter.mdc`
