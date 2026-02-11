# Golf Betting Model

Quantitative golf betting system with an AI brain. Pulls data from the Data Golf API, computes rolling stats and rankings, runs course fit + form + momentum models, compares to market odds for EV, and continuously improves through automatic learning after each tournament.

**Data sources:** Data Golf API (primary), Betsperts CSVs (optional supplement), course profile screenshots (Claude Vision).

**AI brain:** OpenAI-powered analysis, betting decisions, and persistent memory that gets smarter each week.

**Bet types:** Outright, Top 5, Top 10, Top 20, Matchups. No DFS.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up your API keys (copy .env.example to .env and fill in)
cp .env.example .env
# Edit .env with your keys (see API Keys section below)

# 3. Backfill historical round data (one-time, takes ~1 minute)
python analyze.py --tournament "Setup" --course "Setup" --backfill 2024 2025 2026

# 4. Run analysis for this week's tournament
python analyze.py --tournament "AT&T Pebble Beach" --course "Pebble Beach" --sync

# 5. Run with AI brain for betting decisions
python analyze.py --tournament "AT&T Pebble Beach" --course "Pebble Beach" --sync --ai

# 6. Open the betting card
#    → output/att_pebble_beach_YYYYMMDD.md

# 7. After the tournament, results are auto-ingested from DG data
#    (or enter manually: python results.py --tournament "AT&T Pebble Beach")
```

## Web UI

```bash
python app.py
# Open http://localhost:8000
```

The web UI provides:
- Tournament setup + Data Golf sync (one-click)
- Betsperts CSV upload (optional supplement)
- Course profile screenshot upload (drag-and-drop)
- AI brain controls (pre-analysis, betting decisions, post-review)
- Performance dashboard with calibration and ROI tracking
- Learning insights and AI memory viewer

## API Keys

Create a `.env` file in the project root (see `.env.example`):

| Key | Required | Source | Purpose |
|-----|----------|--------|---------|
| `DATAGOLF_API_KEY` | Yes | [datagolf.com/api-access](https://datagolf.com/api-access) (Scratch Plus) | Round data, predictions, field updates |
| `OPENAI_API_KEY` | Recommended | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | AI brain (analysis, decisions, memory) |
| `ANTHROPIC_API_KEY` | Optional | [console.anthropic.com](https://console.anthropic.com) | Course profile extraction from screenshots |
| `ODDS_API_KEY` | Optional | [the-odds-api.com](https://the-odds-api.com) | Live market odds for EV calculations |

Optional config:
- `AI_BRAIN_PROVIDER` — `openai` (default), `anthropic`, or `gemini`
- `OPENAI_MODEL` — default `gpt-4o`, can use `gpt-4o-mini` for lower cost

## How It Works

### Data Pipeline

**Primary: Data Golf API** (automated, no CSVs needed)
1. **Backfill** (one-time): Pull 2-3 years of round-level data (SG, stats, scores) for every PGA Tour player. ~3 API calls.
2. **Weekly sync**: Pull pre-tournament predictions, player decompositions, and field updates. ~3 API calls.
3. **Compute rolling stats**: From stored round data, calculate SG averages over last 8/12/16/24 rounds, course-specific history, and rank within the field.
4. **Auto-results**: After tournament ends, finish positions are pulled from the round data. No manual entry needed.

**Optional supplement: Betsperts CSVs**
Drop CSVs into `data/csvs/` for additional granularity (lie-specific scrambling, approach by yardage, etc.). The parser auto-classifies file types and merges with DG data.

**Optional: Course profile screenshots**
Upload Betsperts course profile screenshots (Course Facts, Off the Tee, Approach, etc.) via the web UI or CLI. Claude Vision extracts structured data (skill difficulty ratings, stat comparisons, correlated courses).

### Models

1. **Course Fit Score** — How well the player fits THIS course. Uses course-specific SG history (from rounds DB) + Data Golf player decompositions (course-adjusted predictions) + course profile difficulty ratings (from screenshots).

2. **Form Score** — How well the player is playing RIGHT NOW. Auto-discovers available round windows (8/12/16/24) and blends SG ranks, plus Data Golf pre-tournament probabilities.

3. **Momentum Score** — Is the player trending up or down? Compares ranks across time windows.

4. **Composite Edge Score** — Weighted combination (default: 40% course, 40% form, 20% momentum). Weights are tunable and improve automatically from results.

### Value vs Odds

Model probabilities (from Data Golf's calibrated model, preferred over softmax approximation) are compared to market odds. Bets with EV > 5% are flagged as value.

### AI Brain

The AI brain (OpenAI, structured outputs) sits on top of the quantitative model:

1. **Pre-tournament analysis** — Qualitative analysis of field + course, player adjustments the numbers might miss.
2. **Betting decisions** — Portfolio-level decisions: which bets to take, stake sizing, correlation management.
3. **Post-tournament review** — What worked, what didn't, learnings stored in persistent memory.

The AI has persistent memory: it remembers what it learned at each course and about each betting strategy. This makes it smarter each week.

### Self-Improving Learning

After each tournament (triggered automatically or via web UI):
- Results auto-ingested from Data Golf data
- Picks scored (hit/miss + profit/loss)
- Predictions logged for calibration tracking
- Global weights nudged based on what was predictive
- Course-specific weight profiles updated
- AI brain runs post-tournament review and stores learnings

Over 10-20 tournaments, the model learns what actually matters at each course.

## CLI Reference

```bash
# Basic analysis with Data Golf sync
python analyze.py -t "Tournament Name" -c "Course Name" --sync

# Full pipeline with AI
python analyze.py -t "Tournament Name" -c "Course Name" --sync --ai

# Backfill historical data (one-time)
python analyze.py -t "Setup" -c "Setup" --backfill 2024 2025 2026

# Specify DG course number for course-specific stats
python analyze.py -t "Tournament" -c "Course" --sync --course-num 5

# Use CSV data instead of (or in addition to) Data Golf
python analyze.py -t "Tournament" -c "Course" --folder data/csvs

# Skip Data Golf sync even if key is set
python analyze.py -t "Tournament" -c "Course" --no-sync --folder data/csvs

# Manual odds
python analyze.py -t "Tournament" -c "Course" --sync --odds data/odds.json
```

## Web API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/analyze` | POST | Run full analysis (CSV upload) |
| `/api/sync-datagolf` | POST | Sync DG predictions + compute rolling stats |
| `/api/backfill` | POST | Backfill historical round data |
| `/api/backfill-status` | GET | Check backfill status |
| `/api/course-profile` | POST | Upload course screenshots |
| `/api/saved-courses` | GET | List saved course profiles |
| `/api/ai-status` | GET | AI brain configuration |
| `/api/ai/pre-analysis` | POST | Run AI pre-tournament analysis |
| `/api/ai/betting-decisions` | POST | Get AI betting decisions |
| `/api/ai/post-review` | POST | Run AI post-tournament review |
| `/api/learn` | POST | Full post-tournament learning cycle |
| `/api/calibration` | GET | Model calibration and ROI data |
| `/api/ai-memories` | GET | View AI brain memories |
| `/api/card` | GET | Latest analysis card |
| `/api/results` | POST | Enter tournament results |
| `/api/dashboard` | GET | Performance dashboard |
| `/api/retune` | POST | Manual weight retune |

## File Structure

```
golf-model/
├── analyze.py               # Main CLI: sync + analyze + AI
├── app.py                   # Web UI (FastAPI)
├── results.py               # Manual results entry
├── course.py                # Course profile CLI
├── src/
│   ├── datagolf.py          # Data Golf API client + backfill
│   ├── rolling_stats.py     # Compute rolling SG windows + rankings
│   ├── ai_brain.py          # AI brain (OpenAI/Claude/Gemini)
│   ├── learning.py          # Self-improving learning system
│   ├── csv_parser.py        # Betsperts CSV parser (fallback)
│   ├── player_normalizer.py # Normalize player names
│   ├── db.py                # SQLite database + all helpers
│   ├── odds.py              # Odds API + manual odds
│   ├── value.py             # EV calculator (DG probs preferred)
│   ├── card.py              # Betting card generator
│   ├── course_profile.py    # Course screenshot extraction
│   └── models/
│       ├── course_fit.py    # Course fit (history + DG decomp)
│       ├── form.py          # Form score (auto-discover windows)
│       ├── momentum.py      # Trend/momentum score
│       ├── composite.py     # Weighted combination
│       └── weights.py       # Weight management + retuning
├── data/
│   ├── golf.db              # SQLite database (auto-created)
│   ├── csvs/                # Optional Betsperts CSVs
│   └── courses/             # Saved course profiles (JSON)
├── output/                  # Generated betting cards
├── .env                     # API keys (not committed)
├── .env.example             # Template for .env
└── requirements.txt
```
