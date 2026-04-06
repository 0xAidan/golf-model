# Golf Betting Model

Production-focused golf betting platform that continuously ingests DataGolf data, computes player rankings and matchup edges, and powers an always-on dashboard with separate **Live Tournament** and **Upcoming Tournament** views.

For a product-level overview, see [`ABOUT.md`](ABOUT.md).

## Core Capabilities

- **Always-on live refresh**: background runtime updates snapshots without manual button clicks.
- **Live + upcoming views**: top-nav dashboard tabs for active and next tournament contexts.
- **Quant model pipeline**: course fit, form, and momentum blended into composite rankings.
- **Odds + value detection**: compares model probabilities vs sportsbook odds across placements and matchups.
- **Autoresearch control plane**: walk-forward evaluation, Optuna studies, and guarded strategy iteration.
- **Post-event learning**: grading, calibration tracking, and model adaptation feedback loops.

## Requirements

- Python 3.11+
- API keys in `.env`:

| Key | Required | Source |
|---|---|---|
| `DATAGOLF_API_KEY` | Yes | [datagolf.com/api-access](https://datagolf.com/api-access) |
| `OPENAI_API_KEY` | Optional | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Optional | [console.anthropic.com](https://console.anthropic.com) |

Optional:
- `AI_BRAIN_PROVIDER` (`openai`, `anthropic`, `gemini`)
- `OPENAI_MODEL` (override default)
- `QUIET_DEV_ACCESS_LOGS=1` (reduce local access-log noise)
- `LIVE_REFRESH_ENABLED=0` (hard kill switch for live-refresh runtime)

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env

python setup_wizard.py
python app.py
```

Open: `http://localhost:8000`

API docs: `http://localhost:8000/docs`

## Always-On Live Refresh

The app now supports an always-on refresh loop with tournament-aware cadence windows (`off_window`, `upcoming_window`, `live_window`, `settlement_window`).

Key endpoints:

- `POST /api/live-refresh/start`
- `POST /api/live-refresh/stop`
- `GET /api/live-refresh/status`
- `GET /api/live-refresh/snapshot`

Settings persist under `live_refresh` in `data/autoresearch_settings.json`.

### Matchup Diagnostics Runbook

Use this sequence before assuming matchup generation is broken:

1. Check `GET /api/live-refresh/snapshot`.
2. Inspect `snapshot.live_tournament.diagnostics.state` (or `upcoming_tournament` when on upcoming tab).
3. Interpret state:
   - `no_market_posted_yet`: books have not published matchup rows yet.
   - `market_available_no_edges`: rows exist, but none pass model/EV filters.
   - `pipeline_error`: fetch/transform/model pipeline failed; inspect diagnostics errors.
   - `edges_available`: rows should be visible unless filtered in UI.
4. Compare counts:
   - `diagnostics.market_counts.tournament_matchups.raw_rows` (raw posted rows)
   - `diagnostics.selection_counts.selected_rows` (rows that survived model filters)
5. If UI still shows empty with `edges_available`, clear book/search/min-EV filters or switch board source.

## Dashboard UX

- Top navigation (no side nav for primary workflow)
- Primary tabs:
  - **Live Tournament**
  - **Upcoming Tournament**
- Manual controls moved to **Ops** tab to keep core views clean
- Visibility-aware polling to reduce hidden-tab API traffic

## Deployment (Hetzner-friendly)

You can deploy first on a raw server IP; a domain is optional.

`deploy.sh` provisions:
- `golf-dashboard.service`
- `golf-agent.service`
- `golf-live-refresh.service`
- `golf-backup.timer`

Commands:

```bash
./deploy.sh --setup
./deploy.sh --update
./deploy.sh --status
```

## Project Structure

```text
golf-model/
├── app.py
├── deploy.sh
├── start.py
├── backtester/
│   ├── dashboard_runtime.py
│   └── ...
├── workers/
│   ├── live_refresh_worker.py
│   └── research_agent.py
├── src/
│   ├── datagolf.py
│   ├── db.py
│   ├── live_refresh_policy.py
│   ├── autoresearch_settings.py
│   └── services/
│       ├── golf_model_service.py
│       └── live_snapshot_service.py
├── static/
├── templates/
├── tests/
└── docs/
```

## Quality Status

- Test suite: `174 passed` (latest full run)
- Focused live-refresh + dashboard tests added
- Syntax checks for updated runtime/service modules pass

## License

Private. Not for redistribution.
