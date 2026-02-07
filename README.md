# Golf Betting Model

Quantitative golf betting system that ingests Betsperts Rabbit Hole CSV data, builds player scores (course fit + form + momentum), compares to market odds for EV, and continuously improves by retuning weights from results.

**Bet types:** Outright, Top 5, Top 10, Top 20, Matchups, 72-hole groups. No DFS.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# 1. Drop your Betsperts CSVs into data/csvs/
#    (cheat sheet, sim, 12r, 24r, course-specific data, rolling averages, etc.)

# 2. Run the model
python analyze.py --tournament "WM Phoenix Open" --course "TPC Scottsdale"

# 3. Open the betting card
#    → output/wm_phoenix_open_YYYYMMDD.md

# 4. After the tournament, enter results
python results.py --tournament "WM Phoenix Open"

# 5. View performance and retune
python dashboard.py
python dashboard.py --retune
```

## How It Works

### Data Pipeline
Drop any Betsperts CSV into `data/csvs/`. The parser auto-classifies the file type (strokes gained, OTT, approach, putting, sim, etc.), detects the round window (all/8/12/16/24), and whether it's course-specific or recent form. Player names are normalized so all sources join correctly.

### Models

1. **Course Fit Score** — How well the player fits THIS specific course based on course-specific historical data (SG:TOT, OTT, APP, putting, par efficiency). More rounds at the course = more confidence.

2. **Form Score** — How well the player is playing RIGHT NOW across multiple timeframes (16-round, 12-month, rolling averages) plus Betsperts sim probabilities.

3. **Momentum Score** — Is the player trending up or down? Compares ranks across windows (L8 vs L16 vs L24 vs all). Catches players getting hot and avoids declining ones.

4. **Composite Edge Score** — Weighted combination of all three (default: 40% course, 40% form, 20% momentum). Weights are tunable and improve over time from results.

### Value vs Odds
When odds are available (via The Odds API or manual entry), the model compares its implied probabilities to market odds. Bets with positive expected value (EV > 5%) are flagged as value plays.

### Continuous Improvement
After each tournament:
- Enter results (finish positions)
- System scores picks (hit/miss)
- `dashboard.py --retune` analyzes which factors predicted well and adjusts weights

Over 10-20 tournaments, the model learns what actually matters.

## CSV Data You Can Feed

From Betsperts Rabbit Hole, the system handles:

- **Tournament:** cheat sheet, tournament sim, all rounds, 12r, 24r
- **Course-specific:** SG, OTT, approach, putting, par efficiency, finish, floor/ceiling, rolling averages (filtered to specific course)
- **Recent form:** 12-month and 16-round versions of all metrics, plus rolling averages (L4/L8/L20/L50)

Just dump them all in `data/csvs/` — the parser figures out what each file is.

## Odds Setup (Optional)

```bash
# Get a free API key from https://the-odds-api.com
export ODDS_API_KEY=your_key_here

# Or create a manual odds file (data/odds.json):
{
    "market": "outrights",
    "bookmaker": "bet365",
    "odds": {
        "Scottie Scheffler": "+450",
        "Xander Schauffele": "+1000"
    }
}

# Then run with:
python analyze.py -t "WM Phoenix Open" -c "TPC Scottsdale" --odds data/odds.json
```

## File Structure

```
golf-model/
├── analyze.py           # Main: ingest CSVs → run models → output card
├── results.py           # Enter results, score picks
├── dashboard.py         # View performance, retune weights
├── src/
│   ├── csv_parser.py    # Auto-classify and parse any Betsperts CSV
│   ├── player_normalizer.py  # Normalize player names
│   ├── db.py            # SQLite database
│   ├── odds.py          # Odds API + manual odds
│   ├── value.py         # EV calculator
│   ├── card.py          # Betting card generator
│   └── models/
│       ├── course_fit.py    # Course fit score
│       ├── form.py          # Form score (multi-timeframe)
│       ├── momentum.py      # Trend/momentum score
│       ├── composite.py     # Weighted combination
│       └── weights.py       # Weight management + retuning
├── data/
│   ├── golf.db          # SQLite database (auto-created)
│   └── csvs/            # Drop Betsperts CSVs here
├── output/              # Generated betting cards
└── requirements.txt
```
