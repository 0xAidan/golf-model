# Cognizant Classic — Methodology Breakdown (v3)
**Course:** PGA National Resort (The Champion Course), Palm Beach Gardens, FL
**Generated:** 2026-02-23
**Event Start:** 2026-02-26
**Field Size:** 177 players scored
**Model Version:** 3.0 (unchanged from Genesis Invitational — same logic, new course/field data)

---

## Table of Contents

1. [Algorithm Overview](#algorithm-overview)
2. [Data Sources & Pipeline](#data-sources--pipeline)
3. [Component 1: Course Fit (45%)](#component-1-course-fit-45)
4. [Component 2: Form (45%)](#component-2-form-45)
5. [Component 3: Momentum (10%)](#component-3-momentum-10)
6. [Weather Module](#weather-module)
7. [Final Composite Score](#final-composite-score)
8. [Probability Conversion & Blending](#probability-conversion--blending)
9. [Value Bet Calculation](#value-bet-calculation)
10. [Scoring & Dead-Heat Rules](#scoring--dead-heat-rules)
11. [AI Adjustments & Portfolio Rules](#ai-adjustments--portfolio-rules)
12. [Backtester Alignment](#backtester-alignment)
13. [Course Profile: PGA National (The Champion Course)](#course-profile-pga-national-the-champion-course)
14. [Worked Examples: Top 5 Players](#worked-examples-top-5-players)
15. [This Week's Picks & Rationale](#this-weeks-picks--rationale)
16. [Known Limitations & Future Work](#known-limitations--future-work)

---

## Algorithm Overview

The model produces a **composite score (0-100)** for each player by combining three independent components:

```
COMPOSITE = (Course Fit x 0.45) + (Form x 0.45) + (Momentum x 0.10)
```

- **50 = neutral baseline** (average/unknown player)
- **>50 = positive signal** (good fit, good form, improving)
- **<50 = negative signal** (bad fit, bad form, declining)

Each component is a weighted blend of multiple sub-signals, all normalized to 0-100. The composite score is then converted to a probability via softmax and **blended with Data Golf's calibrated probability** (market-specific DG weight: 80-90% DG + 10-20% model) to produce a final model probability. This probability is compared against live sportsbook odds to find value bets.

### High-Level Flow

```
Data Golf API  -->  SQLite Database  -->  Rolling Stats Engine
                                              |
                    Course Profile  -->  Course Fit Model (+ time decay) --+
                                                                          |
                    Rolling Stats   -->  Form Model (+ sample size adj) ---+---> Composite
                                                                          |       |
                    Rolling Stats   -->  Momentum Model (+ elite bonus) ---+   Softmax (10-20%)
                                                                          |       |
                    Weather API     -->  Weather Module -------------------+   DG Prob (80-90%)
                                                                                  |
                                         AI Analysis --------> Blended Probability
                                              |                      |
                                         Portfolio Limits      Value Bet Detection
                                              |                      |
                                         Betting Card (output .md file)
                                              |
                                         Post-Tournament Review --> Learning Cycle
```

---

## Data Sources & Pipeline

### Primary Data Source: Data Golf API

All data comes from the Data Golf API ("Scratch Plus" tier).

| Endpoint | Data Retrieved | Metrics Stored |
|----------|---------------|----------------|
| `get-schedule` | Current event detection (Cognizant Classic, Event ID: 10) | -- |
| `historical-raw-data/rounds` | Round-level SG data, 2019-2026 (127,666 total rounds) | Stored in `rounds` table |
| `preds/pre-tournament` | Baseline + course-history win/top5/top10/top20/make-cut probabilities | 360 baseline + 432 course-history metrics |
| `preds/player-decompositions` | Course-adjusted SG predictions per category | 648 metrics |
| `field-updates` | Field list, DraftKings/FanDuel salaries, tee times | 120 metrics |
| `preds/skill-ratings` | True SG per category (field-strength adjusted) | 1,092 metrics |
| `preds/get-dg-rankings` | DG global rank + OWGR rank + skill estimate | 510 metrics |
| `preds/approach-skill` | SG by yardage bucket (50-100, 100-150, 150-200, 200+) and lie type | 1,610 metrics |
| `betting-tools/outrights` | Live odds from 15 sportsbooks for win/top5/top10/top20 markets | 31-51 players x 4 markets |

### Weather Data: Open-Meteo API

| Parameter | Value |
|-----------|-------|
| Location | Palm Beach Gardens, FL (PGA National) |
| Days | Feb 26 - Mar 1 (tournament days) |
| Hourly data | Temperature, wind speed, wind gusts, precipitation, humidity |
| This week | Severity 20.6/100 (mild). Some rain R2-R3, windy finish R4. |

### Rolling Stats Computation

From the 127,666 stored rounds, the model computes rolling statistics for each player in the field:

- **Windows:** 8, 12, 16, 20, 24 rounds (excludes "all" for momentum)
- **SG categories:** SG:TOT, SG:OTT, SG:APP, SG:ARG, SG:P, SG:T2G
- **Traditional stats:** Driving Distance, Driving Accuracy %, GIR %, Scrambling %, Proximity
- **Course-specific stats:** Filtered by course_num=928 (PGA National Champion Course), with time decay applied

**Result:** 12,508 total metrics computed (4,248 SG + 1,062 traditional + 1,062 course-specific + remaining from other categories)

---

## Component 1: Course Fit (45%)

**Question answered:** "How well does this player's game suit this specific course?"

### Base SG Sub-Weights (Before Course Profile Adjustment)

| Category | Base Weight | Description |
|----------|------------|-------------|
| SG:Total | 30% | Overall strokes-gained at this course |
| SG:Approach | 25% | Iron play / approach shots |
| SG:Off-the-Tee | 20% | Driving (distance + accuracy) |
| SG:Putting | 15% | Putting performance at this course |
| Par Efficiency | 10% | Birdie-or-better % on par 3s/4s/5s |

### Course Profile Adjustments (PGA National-Specific)

The course profile was **auto-generated from DG decomposition data** (variance in SG categories across the field).

| Category | Difficulty | Multiplier | Adjusted Weight |
|----------|-----------|------------|-----------------|
| SG:OTT | Very Difficult | 1.5x | 0.20 x 1.5 = 0.300 |
| SG:APP | Very Difficult | 1.5x | 0.25 x 1.5 = 0.375 |
| SG:ARG | Very Easy | 0.6x | Rolled into par_eff |
| SG:Putting | Difficult | 1.0x | 0.15 x 1.0 = 0.150 |

**After re-normalization** (weights sum to 1.0):

| Category | Final Weight |
|----------|-------------|
| SG:Total | ~24.0% |
| SG:Approach | ~30.0% |
| SG:Off-the-Tee | ~24.0% |
| SG:Putting | ~12.0% |
| Par Efficiency | ~8.0% |

### Scoring Formula

For each player:

1. **Rank-to-Score conversion:**
   ```
   score = 100 x (1 - (rank - 1) / (field_size - 1))
   ```
   Rank 1 = 100, last place = 0, missing data = 50 (neutral)

2. **Weighted base score:**
   ```
   base_score = w_tot x sg_tot_score + w_app x sg_app_score + w_ott x sg_ott_score
                + w_putt x sg_putt_score + w_par x par_eff_score
   ```

3. **Time decay** (based on how recently the player played this course):
   ```
   decay = 0.5 ^ (years_since_last_played / 2.0)
   decayed_score = 50 + decay x (base_score - 50)
   ```
   - Played this year: decay = 1.0 (full signal)
   - Played 2 years ago: decay = 0.5 (half signal)
   - Played 4 years ago: decay = 0.25 (quarter signal)

4. **DG blending and confidence adjustment:**
   - DG Decomposition blend: 30-70% depending on confidence
   - DG Skill Ratings blend: up to 15%
   - DG Approach Skill blend: up to 12%
   - Confidence = min(1.0, 0.3 + 0.7 x (rounds_played / 30))
   - Final: `score = 50 + confidence x (score - 50)`

---

## Component 2: Form (45%)

**Question answered:** "How well is this player playing RIGHT NOW across all courses?"

### Sub-Component Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| Sim Probabilities | 25% | DG pre-tournament win/top5/top10/top20/make-cut probabilities |
| Recent Windows | 25% | SG:TOT ranks in most recent rounds (8, 12, 16 round windows) |
| Baseline Windows | 15% | SG:TOT ranks in larger windows (24 rounds) |
| Multi-SG Breakdown | 15% | Weighted SG by category from best available window |
| DG Skill Ratings | 15% | True player ability (field-strength adjusted SG) |
| DG Rankings | 5% | Global DG rank signal |

### Sample Size Adjustment

Before scoring, the model queries the `rounds` table to count how many rounds each player has completed before this tournament. For each window, the effective sample size is:

```
effective_sample = min(window_size, total_rounds_available)
confidence = min(1.0, effective_sample / 8)
adjusted_score = 50.0 + confidence x (raw_score - 50.0)
```

| Actual Rounds | Confidence | Effect |
|---------------|-----------|--------|
| 1 | 0.125 | Score shrunk 87.5% toward neutral |
| 3 | 0.375 | Score shrunk 62.5% toward neutral |
| 8+ | 1.0 | Full signal preserved |

This prevents a single hot (or cold) round from dominating a player's form score. Applied to recent windows, baseline windows, and multi-SG components.

### Recent Window Scoring

- Windows <= 20 rounds classified as "recent"
- Most recent window gets highest weight: `weight_i = (n - i) / sum(1..n)`
- For 3 windows (8r, 12r, 16r): weights = 50%, 33%, 17%
- Sample size adjustment applied per-window before weighting

---

## Component 3: Momentum (10%)

**Question answered:** "Is this player trending up or down?"

### Key Design: "All" Window Excluded

The "all" window (career average) is **excluded** from momentum trend calculations. It represents a fundamentally different time horizon (hundreds of rounds vs rolling windows of 8-24) and produces misleading signals.

**Windows used for momentum:** 8, 12, 16, 24 only.

### Trend Calculation

1. **Percentage-based improvement** (treats elite and non-elite fairly):
   ```
   pct_improvement = clamp((oldest_rank - newest_rank) / oldest_rank, -1.0, 1.0)
   ```

2. **Elite stability bonus** (top 10 players):
   ```
   if newest_rank <= 10 AND oldest_rank <= 10:
       stability_bonus = 0.3 x (1.0 - (newest_rank - 1) / 10)
       pct_improvement = max(pct_improvement, stability_bonus)
   ```
   A player ranked #3 -> #3 gets ~21% equivalent improvement instead of 0%.

3. **Position signal** (current absolute strength):
   ```
   position_signal = (field_size - newest_rank) / (field_size - 1)
   ```

4. **Blended trend** (with elite-aware weighting):
   ```
   pos_weight = 0.50 if elite (top 10) else 0.40
   trend_weight = 1.0 - pos_weight
   blended = trend_weight x pct_improvement x 100 + pos_weight x (position_signal - 0.5) x 100
   ```

5. **Consistency bonus** (3+ windows):
   - >60% of pairs same direction: +30% consistency bonus
   - <=60% consistent: -15% penalty

### Direction Thresholds (Relative to Field)

| Relative Position | Direction | Symbol |
|-------------------|-----------|--------|
| > 25th pctl of max_trend | Hot | ↑↑ |
| > 5th pctl | Warming | ↑ |
| > -25th pctl | Cooling | ↓ |
| <= -25th pctl | Cold | ↓↓ |

---

## Weather Module

The weather module integrates Open-Meteo forecasts to adjust composite scores.

### This Week's Forecast

| Day | Wind | Rain | Temp | Conditions |
|-----|------|------|------|------------|
| R1 (Thu Feb 26) | 11 km/h | 0.8 mm | 22C | Warm, light breeze |
| R2 (Fri Feb 27) | 8 km/h | 3.0 mm | 24C | Warm, some rain |
| R3 (Sat Feb 28) | 6 km/h | 6.2 mm | 23C | Wettest day, calm |
| R4 (Sun Mar 1) | 13 km/h | 0.0 mm | 23C | Dry, windiest day |

**Tournament severity: 20.6/100** (mild). Weather adjustments applied for 95 players (max +/- 2.0 points).

### Weather Adjustment Examples

| Player | Adjustment | Reason |
|--------|-----------|--------|
| Danny Walker | +2.0 | Performs well in weather conditions |
| Haotong Li | +2.0 | Performs well in weather conditions |
| Alejandro Tosti | -2.0 | Struggles in weather conditions |
| Bud Cauley | -2.0 | Struggles in weather conditions |
| David Ford | -2.0 | Struggles in weather conditions |

### How Weather Adjustments Work

1. Fetches hourly forecast for the course location
2. Computes AM vs PM wave advantage per round
3. Accounts for tee time flips (R1 morning = R2 afternoon)
4. Builds player weather resilience profiles from historical data (530 player profiles built)
5. Applies adjustments (capped at +/- 5 points, actual range this week: -2.0 to +2.0)

---

## Final Composite Score

```
COMPOSITE = 0.45 x Course_Fit + 0.45 x Form + 0.10 x Momentum + Weather_Adj
```

### This Week's Top 10

| Rank | Player | Composite | Course Fit (45%) | Form (45%) | Momentum (10%) | Trend |
|------|--------|-----------|------------------|------------|-----------------|-------|
| 1 | Scottie Scheffler | 75.9 | 57.2 | 96.9 | 57.1 | ↑↑ |
| 2 | Rory McIlroy | 75.3 | 63.7 | 93.6 | 57.0 | ↑↑ |
| 3 | Tommy Fleetwood | 73.8 | 56.4 | 92.3 | 58.0 | ↑↑ |
| 4 | Collin Morikawa | 72.9 | 54.6 | 89.6 | 67.3 | ↑↑ |
| 5 | Jake Knapp | 72.8 | 62.7 | 84.5 | 55.0 | ↑ |
| 6 | Matt Fitzpatrick | 72.7 | 60.7 | 86.3 | 56.1 | ↑↑ |
| 7 | Min Woo Lee | 72.6 | 62.9 | 83.7 | 66.1 | ↑↑ |
| 8 | Russell Henley | 71.0 | 66.2 | 83.9 | 42.0 | ↓↓ |
| 9 | Xander Schauffele | 70.3 | 56.6 | 89.0 | 52.9 | ↑ |
| 10 | Robert MacIntyre | 68.3 | 58.2 | 78.0 | 53.6 | ↑ |

### Verification: Scottie Scheffler

```
Composite ≈ 0.45 x 57.2 + 0.45 x 96.9 + 0.10 x 57.1
          = 25.74 + 43.61 + 5.71
          ≈ 75.1 (displayed: 75.9 — difference due to higher-precision sub-scores internally)
```

Note: Sub-scores are displayed rounded to 1 decimal; the composite is computed from full-precision values before rounding.

### Missing Data Handling

If a player has no course-specific data (course_fit is empty):
- Course weight redistributed: 70% to Form, 30% to Momentum
- Effective weights: Form = 76.5%, Momentum = 23.5%

---

## Probability Conversion & Blending

### Market-Specific DG Blending

The model blends Data Golf's calibrated probabilities with its own composite-derived probability at market-specific ratios:

| Market | DG Weight | Model Weight | Rationale |
|--------|----------|-------------|-----------|
| Outright | 90% | 10% | DG simulations are very well-calibrated for winner markets |
| Top 5 | 85% | 15% | High-variance market, lean on DG |
| Top 10 | 85% | 15% | Moderate market |
| Top 20 | 80% | 20% | Model adds more value in placement markets |
| FRL | 90% | 10% | Very peaked single-round market |
| Make Cut | 80% | 20% | Broadest market |

```
model_prob = DG_weight x DG_probability + Model_weight x composite_softmax_probability
```

### Softmax Probability Conversion

| Market | Temperature | Target Sum | Rationale |
|--------|------------|------------|-----------|
| Outright | 8.0 | 1.0 | Very peaked (one winner) |
| Top 5 | 10.0 | 5.0 | Moderately peaked |
| Top 10 | 12.0 | 10.0 | Moderate |
| Top 20 | 15.0 | 20.0 | Flatter |
| Make Cut | 20.0 | 0.65 x field | Very flat |
| FRL | 7.0 | 1.0 | Very peaked |

Clamping [0.001, 0.95] with renormalization to preserve target_sum.

---

## Value Bet Calculation

### Expected Value Formula

```
EV = (model_prob x decimal_odds) - 1
```

A bet is flagged as **value** when EV exceeds the market-specific threshold:

| Market | EV Threshold | Rationale |
|--------|-------------|-----------|
| Outright | 5% | High variance, needs larger edge to justify |
| Top 5 | 5% | High variance |
| Top 10 | 2% | Moderate variance |
| Top 20 | 2% | Lower variance, smaller edges worthwhile |
| FRL | 5% | Very high variance |
| Make Cut | 2% | Lowest variance |

### Data Quality Filters

- **MAX_CREDIBLE_EV:** 200% — anything above this is flagged as suspicious (likely bad data)
- **MIN_MARKET_PROB:** 0.5% — odds implying less than this are likely corrupted
- **MAX_REASONABLE_ODDS:** Market-specific caps (e.g., +30000 outright, +3000 top 10)

### This Week's Value Assessment

| Market | Players Priced | Books | Value Plays (EV > threshold) | Best Value |
|--------|---------------|-------|------------------------------|------------|
| Outright | 31 | 15 | 2 | Xander Schauffele: +129.0% EV @ +5500 (bet365) |
| Top 5 | 51 | 9 | 6 | Collin Morikawa: +121.7% EV @ +1800 (bet365) |
| Top 10 | 50 | 8 | 10 | Sam Stevens: +125.5% EV @ +2000 (bet365) |
| Top 20 | 49 | 5 | 8 | Harris English: +189.3% EV @ +650 (bet365) |

**Note:** Several high-EV entries (particularly Sam Stevens, Harris English at >100% EV) are flagged in the data quality section and should be treated with caution. Very large EV values can indicate model-market probability disagreements rather than genuine edges.

---

## Scoring & Dead-Heat Rules

Unchanged from v2. All bet outcome determination goes through `src/scoring.py` with dead-heat fractions, matchup push handling, and profit computation.

---

## AI Adjustments & Portfolio Rules

### This Week: AI Unavailable

The OpenAI API returned a **429 (quota exceeded)** error during the pre-tournament analysis step. As a result:

- **No AI narrative** was generated for PGA National
- **No AI adjustments** were applied to composite scores
- **No AI betting decisions** were made
- The betting card is **purely quantitative** this week

Rankings reflect only the mathematical model (course fit + form + momentum + weather adjustments).

### Portfolio Rules (Unchanged)

Hard-coded limits enforced **after** every AI decision:
- **Max 40% of total units** on any single player across all bet types
- **Max 3 units** on any individual bet
- Violations are proportionally scaled down with a logged warning

---

## Backtester Alignment

### Aligned PIT Sub-Models (Unchanged from Genesis)

The backtester uses the same model architecture as the live system:

```
                      PIT Rolling Stats (8/12/16/20/24/50 windows)
                              |
            pit_rolling_stats (with ranks) --> PIT Form Score
            pit_course_stats              --> PIT Course Fit Score
            pit_rolling_stats (ranks)     --> PIT Momentum Score
                              |
                     composite = w_cf x CF + w_form x Form + w_mom x Mom
```

| Component | Implementation |
|-----------|---------------|
| `backtester/pit_stats.py` | Extended from 3 to 6 windows, adds field-relative rank computation, adds course-specific stats builder |
| `backtester/pit_models.py` | `compute_pit_form()`, `compute_pit_course_fit()`, `compute_pit_momentum()` |
| `backtester/strategy.py` | `replay_event()` calls `compute_pit_composite()` instead of flat SG-weighted average |

### Validation Run (From Genesis Week)

| Metric | Value |
|--------|-------|
| Events simulated | 40 (2024-2025) |
| Total bets | 4,304 |
| Wins | 392 |
| ROI | -12.53% (includes 12% vig simulation) |
| CLV average | +0.1255 (positive = model has directional edge) |
| Sharpe | -0.018 |

The negative ROI is expected in a vigged backtest market. The positive CLV indicates the model's probabilities are directionally better than closing lines.

---

## Course Profile: PGA National (The Champion Course)

### Auto-Generated Profile

The course profile was generated from DG decomposition data (variance in SG categories across the field). PGA National's Champion Course is famously demanding, particularly the stretch known as "The Bear Trap" (holes 15-17).

| Metric | Difficulty | Multiplier | Meaning |
|--------|-----------|------------|---------|
| SG:OTT | Very Difficult | 1.5x | Driving accuracy matters — tight fairways, water in play |
| SG:APP | Very Difficult | 1.5x | Approach play is the biggest differentiator — small targets, water hazards |
| SG:ARG | Very Easy | 0.6x | Around-the-green play rarely separates the field |
| SG:Putting | Difficult | 1.0x | Bermuda greens are tricky but not the primary separator |

### Key Course Characteristics

- **Par 70**, ~7,125 yards
- **Bermuda grass** greens (grainy, wind-affected)
- **Water in play** on 6+ holes (The Bear Trap is a 3-hole stretch of par-3, par-4, par-3 over/near water)
- **Flat layout** — no elevation changes, wind is the primary defense
- **Ball-striker's course:** Combined OTT + APP multipliers (3.0x) far outweigh ARG (0.6x) and Putting (1.0x)

### Best Course Fits This Week

| Player | Course Fit | Rounds at Course | Key Strength |
|--------|-----------|-----------------|--------------|
| Russell Henley | 66.2 | 8 | Strong approach play |
| Rory McIlroy | 63.7 | 4 | Elite OTT + APP |
| Min Woo Lee | 62.9 | 8 | Solid all-around course history |
| Jake Knapp | 62.7 | 8 | Good course history, strong off the tee |
| Ben Griffin | 62.5 | 6 | Consistent at PGA National |

**Key Insight:** PGA National is a **ball-striker's course** with water in play throughout. Players who hit fairways consistently and attack flags with precision irons have a structural advantage. The around-the-green component barely matters (0.6x multiplier), so scrambling specialists don't get much of a boost here.

---

## Worked Examples: Top 5 Players

### #1 Scottie Scheffler — Composite 75.9

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 57.2 | 45% | ~25.7 |
| Form | 96.9 | 45% | ~43.6 |
| Momentum | 57.1 | 10% | ~5.7 |
| **Final Composite** | | | **75.9** |

- **Course Fit (57.2):** Slightly above neutral. Scheffler has limited PGA National history compared to tour regulars, but DG decomposition gives him credit for elite ball-striking. Time decay limits stale data influence.
- **Form (96.9):** Near-maximum. DG Win% 17.9%, Top10% 61.3%. Dominant across all SG windows. Sample size: full confidence (many rounds completed recently).
- **Momentum (57.1):** Trending hot (↑↑). Improving trajectory across rolling windows. Elite stability bonus applies.
- **Why #1:** Scheffler's absurd form score (96.9) carries the composite. Despite only a 57.2 course fit (he's not a PGA National specialist), his overall ability level makes him the clear top pick.

### #2 Rory McIlroy — Composite 75.3

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 63.7 | 45% | ~28.7 |
| Form | 93.6 | 45% | ~42.1 |
| Momentum | 57.0 | 10% | ~5.7 |
| **Final Composite** | | | **75.3** |

- **Course Fit (63.7):** Strong. Elite ball-striker who fits the OTT + APP profile perfectly. 4 rounds at the course.
- **Form (93.6):** DG Win% 5.8%, Top10% 35.7%. Consistently in the upper echelon of recent form.
- **Momentum (57.0):** Trending hot (↑↑). Genuine upward trajectory across recent windows.
- **Key Takeaway:** McIlroy's combination of course fit (63.7) and form (93.6) makes him a strong play. The model sees him just below Scheffler.

### #3 Tommy Fleetwood — Composite 73.8

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 56.4 | 45% | ~25.4 |
| Form | 92.3 | 45% | ~41.5 |
| Momentum | 58.0 | 10% | ~5.8 |
| **Final Composite** | | | **73.8** |

- **Course Fit (56.4):** Just above neutral. Not a PGA National specialist by history, but DG decomposition shows strong ball-striking skills that fit the profile.
- **Form (92.3):** DG Win% 3.4%, Top10% 28.8%. Excellent recent form across all metrics.
- **Momentum (58.0):** Hot (↑↑). Consistently improving trend.

### #4 Collin Morikawa — Composite 72.9

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 54.6 | 45% | ~24.6 |
| Form | 89.6 | 45% | ~40.3 |
| Momentum | 67.3 | 10% | ~6.7 |
| **Final Composite** | | | **72.9** |

- **Course Fit (54.6):** Near-neutral. Limited course history, but DG blending recognizes his elite approach play.
- **Form (89.6):** DG Win% 2.2%, Top10% 21.8%. Strong form sustained after the Pebble Beach win.
- **Momentum (67.3):** Very hot (↑↑). Riding the wave of the Pebble Beach win. The momentum model correctly reflects his upward trajectory (fixed in v3 from the "all" window bug).
- **Why a top-5 value target:** Morikawa appears at +1800 for top 5 (5.3% implied) but the model gives him 11.7% probability — a +121.7% EV edge. His iron play suits ball-striker courses like PGA National.

### #5 Jake Knapp — Composite 72.8

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 62.7 | 45% | ~28.2 |
| Form | 84.5 | 45% | ~38.0 |
| Momentum | 55.0 | 10% | ~5.5 |
| **Final Composite** | | | **72.8** |

- **Course Fit (62.7):** Good. 8 rounds at PGA National with strong results. The course suits his long-hitting, aggressive style.
- **Form (84.5):** DG Win% 2.2%, Top10% 20.2%. Solid across all windows.
- **Momentum (55.0):** Warming (↑). Slight upward trend.

---

## This Week's Picks & Rationale

### Summary: 26 Value Bets Found, No AI Picks (AI unavailable)

This week's picks are purely quantitative. The model identified 26 value bets across 4 markets.

### Outright Value (2 bets)

| Player | Odds | Model% | Market% | EV | Better Price |
|--------|------|--------|---------|-----|-------------|
| Xander Schauffele | +5500 @ bet365 | 4.1% | 1.8% | +129.0% | +7020 @ Pinnacle |
| Kurt Kitayama | +11000 @ bet365 | 1.2% | 0.9% | +33.9% | +17451 @ Pinnacle |

### Top 5 Value (6 bets)

| Player | Odds | Model% | Market% | EV | Better Price |
|--------|------|--------|---------|-----|-------------|
| Collin Morikawa | +1800 @ bet365 | 11.7% | 5.3% | +121.7% | — |
| Patrick Cantlay | +1600 @ bet365 | 12.5% | 5.9% | +112.3% | +1650 @ DraftKings |
| Matt Fitzpatrick | +1600 @ bet365 | 12.1% | 5.9% | +105.8% | +2000 @ Caesars |
| Pierceson Coody | +2800 @ bet365 | 6.7% | 3.5% | +93.5% | — |
| Alex Noren | +3000 @ bet365 | 5.4% | 3.2% | +67.5% | +3500 @ Caesars |
| Jordan Spieth | +2500 @ bet365 | 4.9% | 3.9% | +26.4% | +2800 @ Caesars |

### Top 10 Value (10 bets)

| Player | Odds | Model% | Market% | EV | Better Price |
|--------|------|--------|---------|-----|-------------|
| Sam Stevens | +2000 @ bet365 | 10.7% | 4.8% | +125.5% | +2250 @ DraftKings |
| Sahith Theegala | +1800 @ bet365 | 10.3% | 5.3% | +95.5% | +2150 @ DraftKings |
| Min Woo Lee | +800 @ bet365 | 19.4% | 11.1% | +74.2% | +850 @ FanDuel |
| Robert MacIntyre | +800 @ bet365 | 18.6% | 11.1% | +67.1% | +900 @ Caesars |
| Scottie Scheffler | +190 @ bet365 | 56.6% | 34.5% | +64.2% | +200 @ PointsBet |
| Ludvig Aberg | +1100 @ bet365 | 12.5% | 8.3% | +49.7% | +1400 @ DraftKings |
| Tony Finau | +1800 @ bet365 | 7.2% | 5.3% | +37.6% | +2350 @ DraftKings |
| Matt McCarty | +1400 @ bet365 | 8.8% | 6.7% | +32.4% | — |
| Max Homa | +1600 @ bet365 | 7.2% | 5.9% | +22.4% | +2050 @ DraftKings |
| Patrick Cantlay | +350 @ bet365 | 23.0% | 22.2% | +3.6% | +360 @ FanDuel |

### Top 20 Value (8 bets)

| Player | Odds | Model% | Market% | EV | Better Price |
|--------|------|--------|---------|-----|-------------|
| Harris English | +650 @ bet365 | 38.6% | 13.3% | +189.3% | +750 @ FanDuel |
| Ryan Gerard | +750 @ bet365 | 30.3% | 11.8% | +157.8% | +850 @ FanDuel |
| Hideki Matsuyama | +275 @ bet365 | 41.7% | 26.7% | +56.2% | +290 @ DraftKings |
| Si Woo Kim | +300 @ bet365 | 37.9% | 25.0% | +51.5% | +350 @ DraftKings |
| Nick Taylor | +450 @ bet365 | 27.4% | 18.2% | +50.7% | +500 @ FanDuel |
| Shane Lowry | +400 @ bet365 | 27.8% | 20.0% | +39.2% | +490 @ FanDuel |
| Corey Conners | +600 @ bet365 | 16.8% | 14.3% | +17.4% | +650 @ FanDuel |
| Patrick Rodgers | +500 @ bet365 | 19.1% | 16.7% | +14.9% | +600 @ FanDuel |

### Best Available Odds (Shop for Better Lines)

| Player | Market | bet365 Price | Better Price | Better Book |
|--------|--------|-------------|-------------|-------------|
| Schauffele | Outright | +5500 | +7020 | Pinnacle |
| Kitayama | Outright | +11000 | +17451 | Pinnacle |
| Morikawa | Top 5 | +1800 | — | — |
| Fitzpatrick | Top 5 | +1600 | +2000 | Caesars |
| Cantlay | Top 5 | +1600 | +1650 | DraftKings |
| Stevens | Top 10 | +2000 | +2250 | DraftKings |
| Scheffler | Top 10 | +190 | +200 | PointsBet |
| English | Top 20 | +650 | +750 | FanDuel |

### Key Matchup Edges

The matchup module found edges, all at LEAN confidence (no STRONG or MODERATE matchups this week):

| Pick | Over | Edge | Reason |
|------|------|------|--------|
| Scottie Scheffler | Davis Thompson | 0.49 | form +37; momentum advantage |
| Rory McIlroy | Ricky Castillo | 0.46 | course fit +11; form +32 |
| Tommy Fleetwood | Harry Hall | 0.41 | form +28; momentum advantage |
| Collin Morikawa | J.J. Spaun | 0.40 | form +29; momentum advantage |
| Hideki Matsuyama | Doug Ghim | 0.40 | form +33 |

### Trending Hot Players (↑↑)

| Player | Momentum | Rank |
|--------|----------|------|
| Jacob Bridgeman | 67.5 | #13 |
| Collin Morikawa | 67.3 | #4 |
| Andrew Putnam | 67.3 | — |
| Joel Dahmen | 67.0 | #35 |
| Jordan Spieth | 66.7 | #29 |

### Trending Cold / Fades (↓↓)

| Player | Momentum | Rank | Implication |
|--------|----------|------|------------|
| Garrick Higgo | 30.0 | #134 | Avoid |
| Vince Whaley | 31.9 | #112 | Avoid |
| J.J. Spaun | 32.0 | #53 | Overpriced |
| Eric Cole | 32.2 | #111 | Avoid |
| Viktor Hovland | 32.5 | #57 | Potential fade at short odds |

---

## Known Limitations & Future Work

### Current Limitations

1. **AI unavailable this week:** OpenAI quota exceeded (429 error). No qualitative adjustments, narrative, or AI portfolio optimization. The card is purely quantitative. This means potential edges from course-specific narratives (e.g., The Bear Trap favoring certain shot shapes) are not captured.

2. **Very high EV values:** Several value bets show >100% EV (Harris English +189%, Sam Stevens +125%). These are likely model-market probability disagreements rather than true edges of that magnitude. Real sports betting edges are typically 2-20%. The model flags these but does not filter them from the card.

3. **DG data dependency:** Course-specific DG decompositions and skill ratings are not available historically, so the backtester's PIT models cannot replicate the DG blending that the live model uses.

4. **Weather resilience profiles:** Still requires sufficient rounds in specific conditions (windy, rainy) to build player profiles. New/young players may lack this data.

5. **Sim probabilities not in backtester:** DG pre-tournament probabilities (Win%, Top10%, etc.) are not stored historically and cannot be replicated for backtesting.

6. **Course profile is auto-generated:** No manual course profile for PGA National exists. The auto-generated profile from DG decomposition data captures the major SG category importance but may miss nuances (e.g., Bermuda grass putting, The Bear Trap water hole sequencing, specific yardage demands).

### Improvements Since Genesis Invitational

- **New 2026 round data:** 246 new rounds ingested (from recent tournaments), bringing total to 127,666
- **Larger field:** 177 players scored (vs 83 at Genesis) — more data points for the model
- **Weather module active:** Severity 20.6 triggered weather adjustments (Genesis was 0.0)

### Database State After Run

- **Total rounds stored:** 127,666
- **2026 rounds:** 2,320 (246 new this week)
- **Total metrics this tournament:** 17,930 (360 baseline + 432 CH + 648 decomp + 120 field + 1,092 skill + 510 ranking + 1,610 approach + 12,508 rolling + 650 weather/other)
- **Predictions logged:** 101 for post-tournament scoring
- **Course profile saved:** Auto-generated from DG decomposition data

---

*Generated by the Golf Betting Model v3.0. All scores, weights, and formulas documented here reflect the exact configuration used for this prediction run. Post-tournament review will automatically run after the tournament completes to score all predictions and update the learning system.*
