# Golf Betting Model

Quantitative golf betting system that pulls data from the Data Golf API, runs composite scoring models (course fit, form, momentum), compares model probabilities to market odds for expected value, and improves automatically after each tournament. An AI layer provides qualitative analysis and persistent memory.

## What It Does

- **Data pipeline** — Syncs round-level strokes-gained data, pre-tournament predictions, and live odds from the Data Golf API. Computes rolling stats across configurable windows (8/12/16/24 rounds).
- **Composite model** — Scores every player in the field on course fit, current form, and momentum. Blends into a single edge score with weights that adapt based on past results.
- **Value detection** — Compares model probabilities to market odds across outrights (win, top 5/10/20) and matchups. Flags bets above the EV threshold. Kelly criterion sizing with exposure caps.
- **AI brain** — Pre-tournament qualitative analysis, score adjustments, and post-tournament review. Persistent memory stores learnings per course and strategy.
- **Self-improving** — After each tournament: grades picks, logs predictions for calibration, nudges model weights, updates course-specific profiles, and stores AI learnings.
- **Backtester** — Walk-forward backtesting with point-in-time data. Autoresearch engine proposes, tests, and promotes strategy changes through a model registry.

## Requirements

**Python 3.11+** and the following API keys (set in `.env`):

| Key | Required | Source |
|-----|----------|--------|
| `DATAGOLF_API_KEY` | Yes | [datagolf.com/api-access](https://datagolf.com/api-access) (Scratch Plus) |
| `OPENAI_API_KEY` | Recommended | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Optional | [console.anthropic.com](https://console.anthropic.com) |

Set `AI_BRAIN_PROVIDER` to `openai` (default), `anthropic`, or `gemini`. Set `OPENAI_MODEL` to override the default (`gpt-4o`).

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your API keys

python setup_wizard.py          # first-time setup: backfills data, initializes DB
python run_predictions.py       # run the full pipeline for this week's tournament
python app.py                   # start the web UI at http://localhost:8000
```

## Web UI

The dashboard at `http://localhost:8000` handles the full workflow: run predictions, view betting cards, grade past tournaments, manage the model registry, run autoresearch experiments, and track calibration/ROI over time. FastAPI auto-generates API docs at `/docs`.

### Always-On Live Refresh

The dashboard now supports an always-on snapshot runtime for separate **Live Tournament** and **Upcoming Tournament** views:

- `POST /api/live-refresh/start` starts the runtime loop
- `POST /api/live-refresh/stop` stops the runtime loop
- `GET /api/live-refresh/status` returns runtime health and cadence
- `GET /api/live-refresh/snapshot` returns the latest live/upcoming snapshot payload

Cadence windows are tournament-aware and configurable through persisted settings (`live_refresh` in `data/autoresearch_settings.json`).

For quieter local logs while developing, set:

```bash
export QUIET_DEV_ACCESS_LOGS=1
```

## How It Works

1. **Sync** — Pull the current event, field, predictions, decompositions, skill ratings, and odds from Data Golf.
2. **Rolling stats** — Compute strokes-gained averages and rankings over multiple round windows from stored historical data.
3. **Composite scoring** — Run course fit, form, and momentum models. Blend into a single edge score per player.
4. **AI analysis** — (Optional) AI pre-tournament analysis adjusts composite scores based on qualitative factors.
5. **Value + sizing** — Compare model probabilities to market odds. Apply Kelly criterion with fractional sizing, exposure caps, and portfolio diversification.
6. **Card generation** — Output a betting card with recommended plays, stakes, and methodology notes.
7. **Post-tournament** — Auto-grade results, update calibration, nudge weights, run AI review, store learnings.

## Project Structure

```
golf-model/
├── run_predictions.py       # Full prediction pipeline (CLI)
├── app.py                   # Web UI + API (FastAPI)
├── setup_wizard.py          # First-time setup
├── analyze.py               # Lightweight CLI entry point
├── src/
│   ├── datagolf.py          # Data Golf API client
│   ├── db.py                # SQLite database + migrations
│   ├── ai_brain.py          # AI analysis + persistent memory
│   ├── value.py             # EV calculator + value detection
│   ├── card.py              # Betting card generator
│   ├── learning.py          # Post-tournament learning system
│   ├── matchup_value.py     # Matchup bet valuation (Platt calibrated)
│   ├── kelly.py             # Kelly criterion sizing
│   ├── config.py            # Central configuration
│   ├── models/              # Course fit, form, momentum, composite, weights
│   └── services/            # GolfModelService orchestration layer
├── backtester/              # Walk-forward backtesting + autoresearch
├── workers/                 # Research agent + intel harvester
├── scripts/                 # Grading, backfill, backtest utilities
├── tests/                   # pytest suite (138 tests)
├── data/golf.db             # SQLite database (auto-created)
├── output/                  # Generated betting cards + methodology docs
├── feature_flags.yaml       # Toggle features without code changes
├── profiles.yaml            # Run profiles (default, quick, full)
└── .env.example             # Template for API keys
```

## Configuration

- **`.env`** — API keys and provider selection. See `.env.example`.
- **`feature_flags.yaml`** — Toggle Kelly sizing, CLV tracking, exposure caps, dynamic blending, and more.
- **`profiles.yaml`** — Predefined run profiles (`default`, `quick`, `full`) controlling AI, backfill depth, and output.
- **`src/config.py`** — Model parameters: EV thresholds, blend weights, adaptation rates, matchup settings.

## License

Private. Not for redistribution.
