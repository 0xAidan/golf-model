# The Genesis Invitational — Methodology Breakdown
**Course:** The Riviera Country Club, Pacific Palisades, CA
**Generated:** 2026-02-17
**Event Start:** 2026-02-19
**Field Size:** 83 players scored

---

## Table of Contents

1. [Algorithm Overview](#algorithm-overview)
2. [Data Sources & Pipeline](#data-sources--pipeline)
3. [Component 1: Course Fit (40%)](#component-1-course-fit-40)
4. [Component 2: Form (40%)](#component-2-form-40)
5. [Component 3: Momentum (20%)](#component-3-momentum-20)
6. [Final Composite Score](#final-composite-score)
7. [Value Bet Calculation](#value-bet-calculation)
8. [AI Adjustments](#ai-adjustments)
9. [Course Profile: Riviera Country Club](#course-profile-riviera-country-club)
10. [Worked Examples: Top 5 Players](#worked-examples-top-5-players)
11. [Observations & Model Quality Notes](#observations--model-quality-notes)

---

## Algorithm Overview

The model produces a **composite score (0-100)** for each player by combining three independent components:

```
COMPOSITE = (Course Fit × 0.40) + (Form × 0.40) + (Momentum × 0.20)
```

- **50 = neutral baseline** (average/unknown player)
- **>50 = positive signal** (good fit, good form, improving)
- **<50 = negative signal** (bad fit, bad form, declining)

Each component is itself a weighted blend of multiple sub-signals, all normalized to the same 0-100 scale. The model then compares its implied probabilities against live sportsbook odds to find value bets (positive expected value).

### High-Level Flow

```
Data Golf API  ──→  SQLite Database  ──→  Rolling Stats Engine
                                              │
                    Course Profile  ──→  Course Fit Model ─┐
                                                           │
                    Rolling Stats   ──→  Form Model ───────┤──→ Composite Score ──→ Value Bets
                                                           │
                    Rolling Stats   ──→  Momentum Model ───┘
                                                           │
                                         AI Analysis ──────┘
                                              │
                                         Betting Card (output .md file)
```

---

## Data Sources & Pipeline

### Primary Data Source: Data Golf API

All data comes from the Data Golf API (paid subscription, "Scratch Plus" tier). The following endpoints were called for this prediction run:

| Endpoint | Data Retrieved | Metrics Stored |
|----------|---------------|----------------|
| `get-schedule` | Current event detection (The Genesis Invitational, Event ID: 7) | — |
| `historical-raw-data/rounds` | Round-level SG data, 2019-2026 (127,420 total rounds, 320 new for 2026) | Stored in `rounds` table |
| `preds/pre-tournament` | Baseline + course-history win/top5/top10/top20/make-cut probabilities | 360 baseline + 432 course-history metrics |
| `preds/player-decompositions` | Course-adjusted SG predictions per category | 648 metrics |
| `field-updates` | Field list, DraftKings/FanDuel salaries, tee times | 72 metrics |
| `preds/skill-ratings` | True SG per category (field-strength adjusted) | 581 metrics |
| `preds/get-dg-rankings` | DG global rank + OWGR rank + skill estimate | 249 metrics |
| `preds/approach-skill` | SG by yardage bucket (50-100, 100-150, 150-200, 200+) and lie type | 824 metrics |
| `betting-tools/outrights` | Live odds from 16 sportsbooks for win/top5/top10/top20/FRL markets | 72 players × 5 markets |

### Rolling Stats Computation

From the 127,420 stored rounds, the model computes rolling statistics for each player in the field:

- **Windows:** 8, 12, 16, 24 rounds + "all" (full career)
- **SG categories:** SG:TOT, SG:OTT, SG:APP, SG:ARG, SG:P, SG:T2G
- **Traditional stats:** Driving Distance, Driving Accuracy %, GIR %, Scrambling %, Proximity
- **Course-specific stats:** Recency-weighted (exponential decay, 365-day half-life) averages for rounds played at course #500 (Riviera)

**Result:** 5,868 total metrics computed (1,992 SG + 498 traditional + 498 course-specific + remaining from other categories)

---

## Component 1: Course Fit (40%)

The course fit component answers: **"How well does this player's game suit this specific course?"**

### Base SG Sub-Weights (Before Course Profile Adjustment)

| Category | Base Weight | Description |
|----------|------------|-------------|
| SG:Total | 30% | Overall strokes-gained at this course |
| SG:Approach | 25% | Iron play / approach shots |
| SG:Off-the-Tee | 20% | Driving (distance + accuracy) |
| SG:Putting | 15% | Putting performance at this course |
| Par Efficiency | 10% | Birdie-or-better % on par 3s/4s/5s |

### Course Profile Adjustments (Riviera-Specific)

The course profile was **auto-generated from DG decomposition data** (variance in SG categories across the field). Riviera's profile:

| Category | Difficulty Rating | Weight Multiplier | Adjusted Weight |
|----------|------------------|-------------------|-----------------|
| SG:OTT | Very Difficult | 1.5× | 0.20 × 1.5 = 0.300 |
| SG:APP | Very Difficult | 1.5× | 0.25 × 1.5 = 0.375 |
| SG:ARG | Very Easy | 0.6× (no adjustment, only OTT/APP/Putt are adjusted) | 0.10 (unchanged in par_eff) |
| SG:Putting | Difficult | 1.0× (no multiplier for "Difficult") | 0.15 × 1.0 = 0.150 |

**After re-normalization** (weights must sum to 1.0):

| Category | Final Weight |
|----------|-------------|
| SG:Total | ~24.0% |
| SG:Approach | ~30.0% |
| SG:Off-the-Tee | ~24.0% |
| SG:Putting | ~12.0% |
| Par Efficiency | ~8.0% |

**Interpretation:** At Riviera, approach play and driving are weighted ~50% more heavily than baseline. This makes sense — Riviera is a ball-striker's paradise with tight fairways, small greens, and demanding angles.

### Scoring Formula

For each player:

1. **Rank-to-Score conversion:**
   ```
   score = 100 × (1 - (rank - 1) / (field_size - 1))
   ```
   Rank 1 → 100, last place → 0, missing data → 50 (neutral)

2. **Weighted base score:**
   ```
   base_score = w_tot × sg_tot_score + w_app × sg_app_score + w_ott × sg_ott_score + w_putt × sg_putt_score + w_par × par_eff_score
   ```

3. **Confidence adjustment** (based on rounds played at course):
   ```
   confidence = min(1.0, 0.3 + 0.7 × (rounds_played / 30))
   adjusted_score = 50 + confidence × (base_score - 50)
   ```
   - 0 rounds → confidence 0.3 (pulled heavily toward 50)
   - 10 rounds → confidence 0.53
   - 20 rounds → confidence 0.77
   - 30+ rounds → confidence 1.0 (full signal)

4. **DG Decomposition Blend:**
   - Ranks player's DG-predicted SG:Total (course-adjusted) as a percentile among all players
   - If confidence ≥ 0.5: blend weight = 30% DG, 70% course history
   - If confidence < 0.5: blend weight = 70% DG, 30% course history (trust DG more when we have less course data)

5. **DG Skill Ratings Blend (15%):**
   - Takes player's true SG by category (field-strength adjusted)
   - Applies course profile weights (emphasizes APP/OTT at Riviera)
   - Ranks as percentile among field
   - Blended in at 15% of total score

6. **DG Approach Skill Blend (up to 12%):**
   - Uses detailed yardage-bucket SG (50-100yd, 100-150yd, 150-200yd, 200+yd)
   - Composite approach SG ranked as percentile
   - Blend weight = min(12%, approach_weight × 40%)
   - At Riviera with high approach weight: ~12% blend

### Example: Xander Schauffele (Course Fit = 86.0, highest in field)

- 24 rounds at Riviera → confidence = min(1.0, 0.3 + 0.7 × 24/30) = 0.86
- Historically ranks near top in all SG categories at Riviera
- High DG decomposition percentile (predicts strong SG at this course)
- Strong DG approach skill percentile
- Result: 86.0 (elite course fit)

---

## Component 2: Form (40%)

The form component answers: **"How well is this player playing RIGHT NOW across all courses?"**

### Sub-Component Weights

| Component | Raw Weight | Description |
|-----------|-----------|-------------|
| Sim Probabilities | 0.25 | DG pre-tournament win/top5/top10/top20/make-cut probabilities |
| Recent Windows | 0.25 | SG:TOT ranks in most recent rounds (8, 12, 16 round windows) |
| Baseline Windows | 0.15 | SG:TOT ranks in larger windows (24 rounds, "all") |
| Multi-SG Breakdown | 0.15 | Weighted SG by category from best available window |
| DG Skill Ratings | 0.15 | True player ability (field-strength adjusted SG) |
| DG Rankings | 0.05 | Global DG rank signal |

**Note:** Weights are normalized to sum to 1.0 based on which components have data available for each player. If a component is missing, its weight gets redistributed proportionally.

### Sim Probability Scoring

DG's pre-tournament probabilities are converted to 0-100 scores using:

```
score = 50 + probability × scale
```

| Market | Scale Factor | Weight in Sim Score |
|--------|-------------|-------------------|
| Win % | 300 | 30% |
| Top 10 % | 120 | 30% |
| Top 20 % | 80 | 25% |
| Make Cut % | 60 | 15% |

Example: Scottie Scheffler with Win%=18.8%, Top10%=62.2%
- Win component: 50 + 0.188 × 300 = 106.4 → clamped to 100
- Top10 component: 50 + 0.622 × 120 = 124.6 → clamped to 100
- These are averaged with their weights → sim_score near 100

### Recent Window Scoring

- Windows ≤ 20 rounds are classified as "recent"
- Most recent window gets highest weight: weight_i = (n - i) / sum(1..n)
- For 3 windows (8r, 12r, 16r): weights = 3/6, 2/6, 1/6 = 50%, 33%, 17%
- Each window's SG:TOT rank is converted to 0-100 score via rank-to-score formula

### Multi-SG Breakdown Weights

From the best available recent window:

| Category | Weight |
|----------|--------|
| SG:Total | 40% |
| SG:Approach | 25% |
| SG:Off-the-Tee | 15% |
| SG:Putting | 10% |
| SG:Around-Green | 10% |

### DG Skill Score

- Player's DG `sg_total` (true SG per round, field-strength adjusted) is ranked as a percentile among all players in the field who have data
- Formula: `score = 100 × (players_below) / (total_players - 1)`

### DG Ranking Score

- Player's DG global rank inverted: rank 1 → 100, max rank → 0
- Formula: `score = 100 × (1 - (rank - 1) / (max_rank - 1))`

### Example: Scottie Scheffler (Form = 98.4, highest in field)

- Sim probabilities: Win 18.8%, Top10 62.2% → near-max scores across all components
- Recent SG:TOT windows: ranked #1 in most windows → score ~100
- Multi-SG: top in every category → ~100
- DG Skill: highest `sg_total` in field → ~100
- DG Ranking: #1 globally → 100
- Weighted total: ~98.4

---

## Component 3: Momentum (20%)

The momentum component answers: **"Is this player trending up or down?"**

### Trend Calculation

1. **Percentage-based improvement** (not raw rank change, to avoid penalizing elite players):
   ```
   pct_improvement = clamp((oldest_rank - newest_rank) / oldest_rank, -1.0, 1.0)
   ```
   This means going from rank 5→1 (80% improvement) is comparable to 50→10 (80% improvement).

2. **Position signal** (current strength):
   ```
   position_signal = (field_size - newest_rank) / (field_size - 1)
   ```
   Centered at 0.5 for mid-field. Rank 1 = ~1.0, last place = ~0.0.

3. **Blended trend:**
   ```
   blended = 0.6 × pct_improvement × 100 + 0.4 × (position_signal - 0.5) × 100
   ```
   60% directional change + 40% absolute position strength.

4. **Consistency bonus** (if 3+ windows available):
   - Checks if trend is consistent across all intermediate window pairs
   - If >60% of pairs are in same direction: +30% × consistency bonus
   - If ≤60% consistent: -15% penalty (noisy/unreliable trend)
   - Final: `trend = blended × (1 + consistency_bonus)`

### Score Normalization

```
max_trend = max(|all_trends|)
raw_score = 50 + (player_trend / max_trend) × 40
score = clamp(raw_score, 5, 95)
```

Then confidence adjustment based on number of available windows:
```
confidence = min(1.0, windows_count / 4.0)
final_score = 50 + confidence × (score - 50)
```

### Direction Thresholds

| Raw Trend | Direction | Symbol |
|-----------|-----------|--------|
| > 10 | Hot | ↑↑ |
| > 2 | Warming | ↑ |
| > -10 | Cooling | ↓ |
| ≤ -10 | Cold | ↓↓ |

### Example: Justin Rose (Momentum = 85.0, trending hot)

- Oldest window rank: high (poor recent results historically)
- Newest window rank: low (strong recent play)
- Large percentage improvement + good current position
- Consistent across windows → consistency bonus applied
- Result: 85.0 (strong upward trend)

### Example: Xander Schauffele (Momentum = 12.1, trending cold)

- Recent SG:TOT ranks declining across windows
- Despite strong absolute position, directional trend is sharply negative
- Result: 12.1 (significant decline, ↓↓)

---

## Final Composite Score

The three components are combined with top-level weights:

```
COMPOSITE = 0.40 × Course_Fit + 0.40 × Form + 0.20 × Momentum
```

### This Week's Top 5 Composites

| Rank | Player | Composite | Course Fit (40%) | Form (40%) | Momentum (20%) | Trend |
|------|--------|-----------|------------------|------------|-----------------|-------|
| 1 | Scottie Scheffler | 87.2 | 84.8 | 98.4 | 59.4 | ↑↑ |
| 2 | Hideki Matsuyama | 83.8 | 81.1 | 88.0 | 70.8 | ↑↑ |
| 3 | Tommy Fleetwood | 80.9 | 76.3 | 91.3 | 69.1 | ↑↑ |
| 4 | Justin Rose | 77.3 | 71.4 | 79.2 | 85.0 | ↑↑ |
| 5 | Si Woo Kim | 76.1 | 69.1 | 84.4 | 73.6 | ↑↑ |

### Verification: Scottie Scheffler

```
Composite = 0.40 × 84.8 + 0.40 × 98.4 + 0.20 × 59.4
         = 33.92 + 39.36 + 11.88
         = 85.16
```

Note: The displayed 87.2 includes AI adjustments (+2.0 applied post-composite).

### Missing Data Handling

If a player has no course-specific data at all (course_fit component is empty):
- Course weight redistributed: 70% → Form, 30% → Momentum
- Effective weights become: Form = 68%, Momentum = 32%

If a component returns neutral (50.0), the player still gets scored — they just get no edge from that component.

---

## Value Bet Calculation

### Probability Source Priority

The model uses the **best available probability** when calculating expected value:

1. **DG Course-History Model** (best calibrated — adjusts for course fit)
2. **DG Baseline Model** (next best — pure skill-based)
3. **Softmax Approximation** from composite scores (fallback only)

### Expected Value Formula

```
EV = (model_probability × decimal_odds) - 1
```

Where:
- `decimal_odds = (american_odds / 100) + 1` for positive odds
- `decimal_odds = (100 / |american_odds|) + 1` for negative odds

### This Week's Value Assessment

| Market | Players Priced | Value Plays (EV > 2%) | Best Value |
|--------|---------------|----------------------|------------|
| Outright | 72 | 0 | Harris English: -3.5% EV |
| Top 5 | 72 | 2 | Max McGreevy: +7.7% EV |
| Top 10 | 72 | 1 | Max McGreevy: +7.6% EV |
| Top 20 | 72 | 0 | Harris English: -3.4% EV |
| FRL | 72 | 0 | — |

The market is pricing Riviera efficiently this week. Very few edges found, and the AI correctly recommended **no bets** — the risk-reward ratio doesn't justify wagering given the thin margins and Riviera's high variance.

### Quality Filters Applied

- **Max Credible EV:** 200% (anything higher = data error, not real edge)
- **Min Market Probability:** 0.5% (lower = likely stale/bad odds)
- **Suspicious Flag:** model prob > 10× or < 0.1× market prob

---

## AI Adjustments

### Pre-Tournament Analysis (GPT-4o)

The AI received:
- Full field composite scores
- Course profile (Riviera: Very Difficult OTT/APP, Difficult putting)
- No persistent memories (first run with this configuration)

### AI Adjustments Applied

| Player | Adjustment | Reason |
|--------|-----------|--------|
| Scottie Scheffler | +2.0 | Exceptional form and momentum, strong overall composite score |
| Hideki Matsuyama | +2.0 | Excellent course fit and current form, suited for difficult conditions |
| Patrick Cantlay | -3.0 | Despite high course fit (84.6), momentum is very low (25.4) |
| Xander Schauffele | -3.0 | Cold momentum (12.1) detrimental despite elite course fit (86.0) |

### AI Confidence: 80%

The AI assessed the model's output as 80% reliable this week. It noted that Riviera's challenging conditions increase variance, which makes predictions less certain.

### AI Betting Decision: Pass This Week

The AI reviewed all value bets and recommended **0 units wagered**. Reasoning:
- No positive-EV bets within top-35 composite rankings
- The few marginal value plays (Max McGreevy, Harris English) don't justify exposure given course variance
- Better to preserve bankroll for weeks with clearer edges

---

## Course Profile: Riviera Country Club

### Auto-Generated Profile

The course profile was generated from analyzing the **variance in DG's player decompositions** (how much each SG category varies across the field at this course).

| Metric | Value | Meaning |
|--------|-------|---------|
| OTT Impact | 0.2675 | High — driving makes a big difference here |
| APP Impact | 0.2756 | Highest — approach play is the biggest differentiator |
| ARG Impact | 0.0033 | Minimal — around-green play barely matters |
| Putt Impact | 0.1606 | Moderate — putting matters but less than ball-striking |
| Total Fit Spread | 0.2904 | Overall spread of course fit across field |

### Difficulty Ratings

| Category | Rating | Weight Multiplier |
|----------|--------|-------------------|
| SG:Off-the-Tee | Very Difficult | 1.5× |
| SG:Approach | Very Difficult | 1.5× |
| SG:Around Green | Very Easy | 0.6× |
| SG:Putting | Difficult | 1.0× |

**Key Insight:** Riviera is a **ball-striker's course**. The combined OTT + APP impact (0.54) dwarfs ARG (0.003). Players who hit it well off the tee and into greens have a massive advantage. Scrambling is nearly irrelevant because if you're missing greens at Riviera, you're likely in such bad positions that recovery skill can't save you.

### Best Course Fits This Week

| Player | Course Fit | Rounds at Course |
|--------|-----------|-----------------|
| Xander Schauffele | 86.0 | 24 |
| Scottie Scheffler | 84.8 | 20 |
| Patrick Cantlay | 84.6 | 24 |
| Hideki Matsuyama | 81.1 | 20 |
| Collin Morikawa | 80.0 | 20 |

---

## Worked Examples: Top 5 Players

### #1 Scottie Scheffler — Composite 87.2

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 84.8 | 40% | 33.92 |
| Form | 98.4 | 40% | 39.36 |
| Momentum | 59.4 | 20% | 11.88 |
| **Sub-total** | | | **85.16** |
| AI Adjustment | +2.0 | | +2.0 |
| **Final Composite** | | | **87.2** |

- **Course Fit (84.8):** 20 rounds at Riviera, strong historical SG. Confidence = 0.77. High DG decomposition percentile. Elite approach skill.
- **Form (98.4):** DG Win% 18.8%, Top10% 62.2% → near-max sim score. #1 in SG:TOT across all windows. #1 DG skill rating and ranking globally.
- **Momentum (59.4):** Slight upward trend (↑↑). Small positive because he's already at the top with limited room to improve in rank.
- **DG Market Odds:** +700 to win (implies ~12.5% probability). DG model says 18.8%. Not quite enough edge at bet365 after vig.

### #2 Hideki Matsuyama — Composite 83.8

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 81.1 | 40% | 32.44 |
| Form | 88.0 | 40% | 35.20 |
| Momentum | 70.8 | 20% | 14.16 |
| **Sub-total** | | | **81.80** |
| AI Adjustment | +2.0 | | +2.0 |
| **Final Composite** | | | **83.8** |

- **Course Fit (81.1):** 20 rounds at Riviera with strong results. Elite ball-striker who fits the course profile perfectly.
- **Form (88.0):** DG Win% 2.9%, Top10% 26.1%. Strong but not Scheffler-level.
- **Momentum (70.8):** Solidly trending upward (↑↑). Consistent improvement across windows.

### #20 Xander Schauffele — Composite 66.0

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 86.0 | 40% | 34.40 |
| Form | 80.5 | 40% | 32.20 |
| Momentum | 12.1 | 20% | 2.42 |
| **Sub-total** | | | **69.02** |
| AI Adjustment | -3.0 | | -3.0 |
| **Final Composite** | | | **66.0** |

- **Course Fit (86.0):** BEST in the field (24 rounds, elite history at Riviera)
- **Form (80.5):** Strong (DG Win% 4.4%, Top10% 31.0%)
- **Momentum (12.1):** COLD (↓↓). Sharp decline across recent windows. This is the anchor dragging his composite down.
- **Key Takeaway:** The market has Xander at +2000 (4.8% implied). The model agrees he's talented but the cold momentum is a red flag. The AI further penalized him -3.0.

### #22 Rory McIlroy — Composite 64.6

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 75.0 | 40% | 30.00 |
| Form | 81.3 | 40% | 32.52 |
| Momentum | 10.0 | 20% | 2.00 |
| **Final Composite** | | | **64.6** |

- **Course Fit (75.0):** Good but not elite. Riviera historically suits him moderately.
- **Form (81.3):** DG Win% 5.8%, Top10% 35.8%. Market darling.
- **Momentum (10.0):** COLDEST in the field. Severe decline across all windows.
- **Key Takeaway:** DG gives Rory the highest win probability (5.8%) and Top10 probability (35.8%) in the field, but the model's momentum component punishes his recent downtrend heavily. At +1000 outright, the model sees this as fairly priced to slightly overpriced.

---

## Observations & Model Quality Notes

### What Worked Well

1. **Course profile auto-generation** correctly identified Riviera as a ball-striker's course (Very Difficult OTT/APP, Very Easy ARG)
2. **Data quality** was clean — 83 players scored, 5,868 metrics computed, no API errors
3. **AI analysis** provided reasonable narrative and identified meaningful edges/fades
4. **Market efficiency** correctly detected — very few value bets, AI appropriately recommended passing

### Areas for Improvement

1. **Momentum component may be too punitive:** Xander Schauffele (rank #20 despite best course fit and strong form) and Rory McIlroy (rank #22 despite highest DG win probability) are both being dragged down significantly by cold momentum. A 20% weight on momentum may be overweighting short-term noise for elite players.

2. **No weather integration:** The model has a `tournament_weather` table in the database but no active weather data collection. Morning vs afternoon wave advantages can create 2-3 stroke swings. This is the biggest missing data source.

3. **Post-tournament review gap:** The AT&T Pebble Beach Pro-Am post-review could not run (results not yet available in DG API). This means the model hasn't learned from last week's performance yet.

4. **Value bet scarcity:** Only 3 value plays found (2 Top 5, 1 Top 10), all on lower-ranked players (Max McGreevy #38, Harris English #16). This could mean:
   - The market is efficient at Riviera (lots of historical data)
   - DG probabilities are already well-reflected in market odds
   - The model needs more independent signals to find edges the market misses

5. **Max McGreevy at #38 showing value:** The model's DG probabilities (4.1% Top 5) differ from market (3.9%) for a player ranked 38th. This is a very thin edge and may not be reliable. The AI correctly passed on this.

### Database State After Run

- **Total rounds stored:** 127,420
- **2026 rounds:** 2,074 (320 new this week)
- **Predictions logged:** 352 for post-tournament scoring
- **Course profile saved:** `data/courses/the_riviera_country_club.json`

---

---

## Appendix: Free API Evaluation

We evaluated all APIs from [public-apis](https://github.com/public-apis/public-apis) (Sports & Fitness, Weather, and other relevant sections) for potential integration with this model.

### Recommended: Weather APIs (High Value)

Golf is one of the most weather-sensitive sports. Wind, rain, and temperature directly affect scoring. The model already has a `tournament_weather` table in its database but **no active weather data collection**.

| API | Auth | HTTPS | Cost | Potential Use |
|-----|------|-------|------|---------------|
| **Open-Meteo** (open-meteo.com) | None | Yes | Free, no key needed | Hourly forecasts for tournament venue. Best option — free, no auth, good accuracy. |
| **OpenWeatherMap** (openweathermap.org) | API Key | Yes | Free tier: 1000 calls/day | Current weather + 5-day forecast. Reliable fallback. |
| **WeatherAPI** (weatherapi.com) | API Key | Yes | Free tier: 1M calls/month | Astronomy data too (sunrise/sunset for tee time analysis). |
| **US Weather** (weather.gov) | None | Yes | Free | US-only. Great for PGA Tour domestic events. |

**Specific integration opportunity:** Morning vs afternoon wave analysis. In multi-round tournaments, one wave often gets significantly better weather conditions. A 2-3 stroke advantage from weather can dwarf model edges. We could:
1. Fetch hourly wind/rain forecast for tournament Thursday-Friday
2. Cross-reference with tee times (already stored from `field-updates`)
3. Adjust model probabilities based on wave advantage
4. Flag "weather edge" bets when conditions diverge significantly between waves

### Potentially Useful (Medium Value)

| API | Description | Why It Might Help |
|-----|-------------|-------------------|
| **Oddsmagnet** (data.oddsmagnet.com) | Free historical odds from UK bookmakers | Supplement DG odds for calibration and line shopping. No auth required. |
| **Cloudbet** (cloudbet.com/api) | Sports betting odds API | Additional odds source for crypto sportsbooks. API key required. |

### Not Useful for This Model

| API | Why Not |
|-----|---------|
| API-FOOTBALL, balldontlie, NHL, NBA, MLB, etc. | Wrong sport entirely |
| Fitbit, Strava, Wger | Fitness tracking, not golf analytics |
| Sport Vision (Decathlon) | Image analysis for sport gear ID — not relevant |
| TheSportsDB | Golf data exists but DG is vastly more detailed and accurate |
| SuredBits | No golf data |

### Recommendation Summary

The **single highest-value free API integration** is **Open-Meteo** for weather data. It requires:
- No API key
- No rate limits for non-commercial use
- Provides hourly wind speed, direction, precipitation, and temperature
- Can be queried by latitude/longitude (course coordinates)

This would fill the biggest gap in the current model and could be implemented with ~50 lines of code to fetch forecasts and store them in the existing `tournament_weather` table.

---

*Generated by the Golf Betting Model v1.0. All scores, weights, and formulas documented here reflect the exact configuration used for this prediction run.*
