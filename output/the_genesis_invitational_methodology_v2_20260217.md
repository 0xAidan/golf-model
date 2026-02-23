# The Genesis Invitational — Methodology Breakdown (v2)
**Course:** The Riviera Country Club, Pacific Palisades, CA
**Generated:** 2026-02-17
**Event Start:** 2026-02-19
**Field Size:** 83 players scored
**Model Version:** 2.0 (post logic/accuracy overhaul — 22 issues fixed)

---

## Table of Contents

1. [Algorithm Overview](#algorithm-overview)
2. [Changes Since v1 (Logic Overhaul)](#changes-since-v1)
3. [Data Sources & Pipeline](#data-sources--pipeline)
4. [Component 1: Course Fit (40%)](#component-1-course-fit-40)
5. [Component 2: Form (40%)](#component-2-form-40)
6. [Component 3: Momentum (20%)](#component-3-momentum-20)
7. [Weather Module](#weather-module)
8. [Final Composite Score](#final-composite-score)
9. [Probability Conversion & Blending](#probability-conversion--blending)
10. [Value Bet Calculation](#value-bet-calculation)
11. [Scoring & Dead-Heat Rules](#scoring--dead-heat-rules)
12. [AI Adjustments](#ai-adjustments)
13. [Course Profile: Riviera Country Club](#course-profile-riviera-country-club)
14. [Worked Examples: Top 5 Players](#worked-examples-top-5-players)
15. [This Week's Picks & Rationale](#this-weeks-picks--rationale)
16. [Known Limitations & Future Work](#known-limitations--future-work)

---

## Algorithm Overview

The model produces a **composite score (0-100)** for each player by combining three independent components:

```
COMPOSITE = (Course Fit x 0.40) + (Form x 0.40) + (Momentum x 0.20)
```

- **50 = neutral baseline** (average/unknown player)
- **>50 = positive signal** (good fit, good form, improving)
- **<50 = negative signal** (bad fit, bad form, declining)

Each component is a weighted blend of multiple sub-signals, all normalized to 0-100. The composite score is then converted to a probability via softmax and **blended with Data Golf's calibrated probability** (70% DG + 30% model) to produce a final model probability. This probability is compared against live sportsbook odds to find value bets.

### High-Level Flow

```
Data Golf API  -->  SQLite Database  -->  Rolling Stats Engine
                                              |
                    Course Profile  -->  Course Fit Model --+
                                                           |
                    Rolling Stats   -->  Form Model --------+---> Composite Score
                                                           |         |
                    Rolling Stats   -->  Momentum Model ----+     Softmax Prob (30%)
                                                           |         |
                    Weather API     -->  Weather Module ----+     DG Prob (70%)
                                                                     |
                                         AI Analysis --------> Blended Probability
                                              |                      |
                                              |              Value Bet Detection
                                              |                      |
                                         Betting Card (output .md file)
                                              |
                                         Post-Tournament Review --> Learning Cycle
```

---

## Changes Since v1

This run uses model v2.0 after a comprehensive logic and accuracy overhaul that fixed 22 distinct issues. The most impactful changes:

### Critical Fixes

| Fix | Impact |
|-----|--------|
| **Unified scoring module** (`src/scoring.py`) | Eliminated 7 duplicated scoring paths that had divergent logic. All bet outcome determination now goes through one function. |
| **Dead-heat rules** | Ties at market boundaries (e.g., 3 players at T5 for top-5) now pay fractional payouts instead of counting as full wins. Previously overstated hit rates and profit. |
| **Matchup push handling** | Matchup ties now return stake (push) instead of counting as losses. |
| **PIT stats data leakage fix** | Backtester temporal boundary no longer uses circular date reference. Added event_id exclusion guard to prevent current-event data from leaking into "historical" stats. |

### Probability & Value Fixes

| Fix | Impact |
|-----|--------|
| **Probability blending** | Final model probability is now 70% DG + 30% composite softmax (previously used DG exclusively when available, ignoring model signals entirely). |
| **Softmax renormalization** | Probability clamping [0.001, 0.95] now preserves target_sum by renormalizing after clamping. Previously, clamped probabilities could sum to wrong totals. |
| **Consistent softmax temperatures** | Backtester now uses the same market-specific temperatures as the live model (8.0 for outright, 10.0 for top5, 12.0 for top10, 15.0 for top20, 20.0 for make_cut). |

### Weather & Misc Fixes

| Fix | Impact |
|-----|--------|
| **Weather AM/PM flip** | Tee times now correctly flip between rounds (R1 morning = R2 afternoon). |
| **Tournament completion check** | Post-review no longer triggers mid-tournament. |
| **Duplicate result handling** | `store_results` uses `INSERT OR IGNORE` to handle re-runs safely. |
| **Division-by-zero guards** | Added in course_fit weight normalization, softmax field_size=0, and bootstrap empty list. |

---

## Data Sources & Pipeline

### Primary Data Source: Data Golf API

All data comes from the Data Golf API ("Scratch Plus" tier).

| Endpoint | Data Retrieved | Metrics Stored |
|----------|---------------|----------------|
| `get-schedule` | Current event detection (The Genesis Invitational, Event ID: 7) | -- |
| `historical-raw-data/rounds` | Round-level SG data, 2019-2026 (127,420 total rounds) | Stored in `rounds` table |
| `preds/pre-tournament` | Baseline + course-history win/top5/top10/top20/make-cut probabilities | 360 baseline + 432 course-history metrics |
| `preds/player-decompositions` | Course-adjusted SG predictions per category | 648 metrics |
| `field-updates` | Field list, DraftKings/FanDuel salaries, tee times | 72 metrics |
| `preds/skill-ratings` | True SG per category (field-strength adjusted) | 581 metrics |
| `preds/get-dg-rankings` | DG global rank + OWGR rank + skill estimate | 249 metrics |
| `preds/approach-skill` | SG by yardage bucket (50-100, 100-150, 150-200, 200+) and lie type | 824 metrics |
| `betting-tools/outrights` | Live odds from 16 sportsbooks for win/top5/top10/top20/FRL markets | 72 players x 5 markets |

### Rolling Stats Computation

From the 127,420 stored rounds, the model computes rolling statistics for each player in the field:

- **Windows:** 8, 12, 16, 24 rounds + "all" (full career)
- **SG categories:** SG:TOT, SG:OTT, SG:APP, SG:ARG, SG:P, SG:T2G
- **Traditional stats:** Driving Distance, Driving Accuracy %, GIR %, Scrambling %, Proximity
- **Course-specific stats:** Recency-weighted (exponential decay, 365-day half-life) averages at course #500 (Riviera)

**Result:** 5,868 total metrics computed (1,992 SG + 498 traditional + 498 course-specific + remaining from other categories)

---

## Component 1: Course Fit (40%)

**Question answered:** "How well does this player's game suit this specific course?"

### Base SG Sub-Weights (Before Course Profile Adjustment)

| Category | Base Weight | Description |
|----------|------------|-------------|
| SG:Total | 30% | Overall strokes-gained at this course |
| SG:Approach | 25% | Iron play / approach shots |
| SG:Off-the-Tee | 20% | Driving (distance + accuracy) |
| SG:Putting | 15% | Putting performance at this course |
| Par Efficiency | 10% | Birdie-or-better % on par 3s/4s/5s |

### Course Profile Adjustments (Riviera-Specific)

The course profile was **auto-generated from DG decomposition data** (variance in SG categories across the field).

| Category | Difficulty | Multiplier | Adjusted Weight |
|----------|-----------|------------|-----------------|
| SG:OTT | Very Difficult | 1.5x | 0.20 x 1.5 = 0.300 |
| SG:APP | Very Difficult | 1.5x | 0.25 x 1.5 = 0.375 |
| SG:ARG | Very Easy | 0.6x | Rolled into par_eff |
| SG:Putting | Difficult | 1.0x | 0.15 x 1.0 = 0.150 |

**After re-normalization** (weights sum to 1.0, with division-by-zero guard):

| Category | Final Weight |
|----------|-------------|
| SG:Total | ~24.0% |
| SG:Approach | ~30.0% |
| SG:Off-the-Tee | ~24.0% |
| SG:Putting | ~12.0% |
| Par Efficiency | ~8.0% |

**Interpretation:** At Riviera, approach play and driving are weighted ~50% more heavily than baseline. Riviera is a ball-striker's paradise with tight fairways, small greens, and demanding angles.

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

3. **Confidence adjustment** (based on rounds played at course):
   ```
   confidence = min(1.0, 0.3 + 0.7 x (rounds_played / 30))
   adjusted_score = 50 + confidence x (base_score - 50)
   ```
   - 0 rounds: confidence 0.3 (pulled heavily toward 50)
   - 10 rounds: confidence 0.53
   - 20 rounds: confidence 0.77
   - 30+ rounds: confidence 1.0 (full signal)

4. **DG Decomposition Blend:**
   - Ranks player's DG-predicted SG:Total (course-adjusted) as a percentile
   - High confidence (>=0.5): 30% DG + 70% course history
   - Low confidence (<0.5): 70% DG + 30% course history
   - External blend capped at 60% max to preserve course-specific signal

5. **DG Skill Ratings Blend (15%):**
   - True SG by category (field-strength adjusted) with course profile weights
   - Ranked as percentile among field

6. **DG Approach Skill Blend (up to 12%):**
   - Yardage-bucket SG (50-100yd, 100-150yd, 150-200yd, 200+yd)
   - At Riviera with high approach weight: ~12% blend

---

## Component 2: Form (40%)

**Question answered:** "How well is this player playing RIGHT NOW across all courses?"

### Sub-Component Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| Sim Probabilities | 25% | DG pre-tournament win/top5/top10/top20/make-cut probabilities |
| Recent Windows | 25% | SG:TOT ranks in most recent rounds (8, 12, 16 round windows) |
| Baseline Windows | 15% | SG:TOT ranks in larger windows (24 rounds, "all") |
| Multi-SG Breakdown | 15% | Weighted SG by category from best available window |
| DG Skill Ratings | 15% | True player ability (field-strength adjusted SG) |
| DG Rankings | 5% | Global DG rank signal |

Weights normalize to 1.0 based on available data per player.

### Sim Probability Scoring

DG's pre-tournament probabilities are converted to 0-100 scores:

```
score = clamp(50 + probability x scale, 0, 100)
```

| Market | Scale Factor | Weight |
|--------|-------------|--------|
| Win % | 300 | 30% |
| Top 10 % | 120 | 30% |
| Top 20 % | 80 | 25% |
| Make Cut % | 60 | 15% |

The `_pct_to_score` function auto-detects whether the input is a percentage (>1.0) or decimal (<=1.0) and normalizes before scaling.

### Recent Window Scoring

- Windows <= 20 rounds classified as "recent"
- Most recent window gets highest weight: `weight_i = (n - i) / sum(1..n)`
- For 3 windows (8r, 12r, 16r): weights = 50%, 33%, 17%

---

## Component 3: Momentum (20%)

**Question answered:** "Is this player trending up or down?"

### Trend Calculation

1. **Percentage-based improvement** (treats elite and non-elite fairly):
   ```
   pct_improvement = clamp((oldest_rank - newest_rank) / oldest_rank, -1.0, 1.0)
   ```

2. **Position signal** (current absolute strength):
   ```
   position_signal = (field_size - newest_rank) / (field_size - 1)
   ```

3. **Blended trend:**
   ```
   blended = 0.6 x pct_improvement x 100 + 0.4 x (position_signal - 0.5) x 100
   ```

4. **Consistency bonus** (3+ windows):
   - >60% of pairs same direction: +30% consistency bonus
   - <=60% consistent: -15% penalty

### Score Normalization (Relative Thresholds)

```
max_trend = max(|all_trends|)   // if 0, set to 1.0 to avoid division by zero
raw_score = 50 + (player_trend / max_trend) x 40
score = clamp(raw_score, 5, 95)
```

Then confidence adjustment: `final_score = 50 + confidence x (score - 50)`

### Direction Thresholds

Thresholds are now **relative** to the field's max trend (not absolute):

| Relative Position | Direction | Symbol |
|-------------------|-----------|--------|
| > 25th pctl of max_trend | Hot | Up-Up |
| > 5th pctl | Warming | Up |
| > -25th pctl | Cooling | Down |
| <= -25th pctl | Cold | Down-Down |

---

## Weather Module

The weather module integrates Open-Meteo forecasts to adjust composite scores. **This week, the forecast API returned an error** (date 2026-02-19 may be beyond the forecast horizon), so no weather adjustments were applied.

### When Available, the Weather Module:

1. **Fetches hourly forecast** for the course location (lat/long)
2. **Computes AM vs PM wave advantage** for each round day
3. **Accounts for tee time flips** (NEW in v2): R1 morning tee = R2 afternoon tee, R3 = morning again, R4 = afternoon
4. **Builds player weather resilience profiles** from historical data:
   - Wind performance: SG difference in windy vs calm conditions (min 8 rounds required)
   - Rain performance: SG difference in wet vs dry conditions
5. **Applies adjustments** (capped at +/- 5 points for resilience, +/- 3 points for wave advantage)

### Severity Thresholds

| Condition | Threshold | Impact |
|-----------|-----------|--------|
| Windy | > 25 km/h average | Wind resilience profile activated |
| Rainy | > 10mm total precip over tournament | Rain resilience profile activated |
| Cold | < 10C average | Cold weather profile activated |

---

## Final Composite Score

```
COMPOSITE = 0.40 x Course_Fit + 0.40 x Form + 0.20 x Momentum + Weather_Adj
```

Weather adjustment is applied post-composite and clamped to [0, 100].

### This Week's Top 10

| Rank | Player | Composite | Course Fit (40%) | Form (40%) | Momentum (20%) | Trend |
|------|--------|-----------|------------------|------------|-----------------|-------|
| 1 | Scottie Scheffler | 85.9 | 79.2 | 98.4 | 59.4 | Up |
| 2 | Hideki Matsuyama | 82.2 | 77.0 | 88.0 | 70.8 | Up-Up |
| 3 | Tommy Fleetwood | 77.6 | 68.1 | 91.3 | 69.1 | Up-Up |
| 4 | Si Woo Kim | 74.5 | 65.1 | 84.4 | 73.6 | Up-Up |
| 5 | Russell Henley | 72.5 | 71.4 | 84.2 | 51.5 | Down |
| 6 | Justin Rose | 72.3 | 58.9 | 79.2 | 85.0 | Up-Up |
| 7 | Collin Morikawa | 70.2 | 76.0 | 80.5 | 28.2 | Down-Down |
| 8 | Matt Fitzpatrick | 70.0 | 54.2 | 85.3 | 71.0 | Up-Up |
| 9 | Jake Knapp | 69.8 | 52.8 | 79.7 | 84.1 | Up-Up |
| 10 | Patrick Cantlay | 69.3 | 82.4 | 78.3 | 25.4 | Down-Down |

### Verification: Scottie Scheffler

```
Composite = 0.40 x 79.2 + 0.40 x 98.4 + 0.20 x 59.4
         = 31.68 + 39.36 + 11.88
         = 82.92
```

The displayed 85.9 includes AI adjustment (+3.0) applied post-composite.

### Missing Data Handling

If a player has no course-specific data (course_fit is empty dict):
- Course weight redistributed: 70% to Form, 30% to Momentum
- Effective weights: Form = 68%, Momentum = 32%

If a component returns 50.0 (neutral), the player still gets scored but gets no edge from that component.

---

## Probability Conversion & Blending

### NEW in v2: Probability Blending

Previously, when Data Golf probabilities were available, they were used exclusively (100% DG). The model's own composite scores had **zero influence** on the final probability used for betting. This meant course_fit, weather, and momentum signals were computed but never affected betting decisions when DG data existed.

**v2 Fix:** The final probability is now a weighted blend:

```
model_prob = 0.70 x DG_probability + 0.30 x composite_softmax_probability
```

This ensures the model's signals influence the final probability while still anchoring to DG's superior calibration.

### Softmax Probability Conversion

When DG probabilities are not available (or for the 30% model component), composite scores are converted to probabilities via softmax:

```
prob_i = (exp(score_i / temperature) / sum(exp(score_j / temperature))) x target_sum
```

| Market | Temperature | Target Sum | Rationale |
|--------|------------|------------|-----------|
| Outright | 8.0 | 1.0 | Very peaked (one winner) |
| Top 5 | 10.0 | 5.0 | Moderately peaked |
| Top 10 | 12.0 | 10.0 | Moderate |
| Top 20 | 15.0 | 20.0 | Flatter |
| Make Cut | 20.0 | 0.65 x field | Very flat |
| FRL | 7.0 | 1.0 | Very peaked |

### NEW in v2: Renormalized Clamping

Individual probabilities are clamped to [0.001, 0.95] then **renormalized** so the sum of all probabilities still equals `target_sum`. Previously, clamping was applied per-player without renormalization, breaking the probability distribution.

```
1. Compute raw softmax probabilities for all players
2. Clamp each to [0.001, 0.95]
3. Renormalize: clamped_i * (target_sum / sum(clamped))
```

---

## Value Bet Calculation

### Expected Value Formula

```
EV = (model_prob x decimal_odds) - 1
```

Where:
- `decimal_odds = (american_odds / 100) + 1` for positive odds
- `decimal_odds = (100 / |american_odds|) + 1` for negative odds
- A bet is flagged as **value** when EV > 2% (configurable via `EV_THRESHOLD` env variable)

### This Week's Value Assessment

| Market | Players Priced | Value Plays (EV > 2%) | Best Value |
|--------|---------------|----------------------|------------|
| Outright | 72 | 1 | Hideki Matsuyama: +31.4% EV @ +2200 |
| Top 5 | 72 | 3 | Hideki Matsuyama: +31.5% EV @ +450 |
| Top 10 | 72 | 2 | Hideki Matsuyama: +26.3% EV @ +210 |
| Top 20 | 72 | 2 | Hideki Matsuyama: +12.9% EV @ -120 |
| FRL | 72 | 2 | Hideki Matsuyama: +58.1% EV @ +2500 |

**Key Difference from v1:** The probability blending (70% DG + 30% model) has significantly shifted value detection. v1 found almost no value because it used DG probabilities exclusively, and DG probabilities are already well-reflected in market odds. By blending in the model's composite-based probability (which captures course-specific momentum, weather, and form signals DG may underweight), the model now identifies edges where its proprietary signals diverge from DG consensus.

### Quality Filters Applied

- **Max Credible EV:** 200% (anything higher = data error)
- **Min Market Probability:** 0.5% (lower = stale/bad odds)
- **Suspicious Flag:** model prob > 10x or < 0.1x market prob

---

## Scoring & Dead-Heat Rules

### NEW in v2: Unified Scoring Module

All bet outcome determination now goes through `src/scoring.py`. This eliminates 7 previously duplicated code paths that had divergent logic (missing bet types, inconsistent null checks, different market name formats).

### Dead-Heat Rules

When players tie at a market boundary, sportsbooks pay fractional payouts:

```
remaining_spots = threshold - (finish_position - 1)
fraction = remaining_spots / num_tied_at_position
```

**Example:** 3 players tie at T5 for a top-5 market:
- 4 positions are clearly inside (1st through 4th)
- 1 remaining spot for 3 tied players
- Fraction = 1/3
- Payout = stake x (1/3 x (odds - 1) - 2/3)

| Scenario | Previous (v1) | Current (v2) |
|----------|--------------|--------------|
| T5 for top-5, 3 tied | Full win (+$500 on $100 @ +500) | Dead-heat ($66.67 on $100 @ +500) |
| T10 for top-10, 4 tied | Full win | 1/4 fractional payout |
| T20 for top-20, solo | Full win | Full win (no tie = no dead-heat) |

### Matchup Push Rules

| Scenario | Previous (v1) | Current (v2) |
|----------|--------------|--------------|
| Both players finish T15 | Loss (-$100) | Push ($0) |
| Player finishes, opponent WD | Win | Win |
| Both players miss cut | Loss | Push |

---

## AI Adjustments

### Pre-Tournament Analysis (GPT-4o)

The AI received:
- Full field composite scores
- Course profile (Riviera: Very Difficult OTT/APP, Difficult putting)
- 3 persistent memory items from prior tournament reviews

### AI Confidence: 85%

### AI Adjustments Applied

| Player | Adjustment | Reason |
|--------|-----------|--------|
| Scottie Scheffler | +3.0 | Exceptional form and warming momentum align with course demands |
| Hideki Matsuyama | +2.0 | Hot form and strong course fit, particularly in ball-striking |
| Collin Morikawa | +2.0 | Despite cold momentum, strong course fit suggests upside |
| Viktor Hovland | -3.0 | Cold momentum and less favorable course fit on demanding setup |
| Rory McIlroy | -2.0 | Cold momentum and potential for big mistakes |

### AI Betting Decision: 7.5 Units

The AI recommended 5 bets totaling 7.5 units, concentrated on Hideki Matsuyama across multiple markets:

| Player | Market | Odds | Stake | Confidence |
|--------|--------|------|-------|------------|
| Hideki Matsuyama | Outright | +2200 | 1.5u | High |
| Hideki Matsuyama | Top 5 | +450 | 1.5u | High |
| Hideki Matsuyama | Top 10 | +210 | 1.5u | High |
| Hideki Matsuyama | Top 20 | -120 | 2.0u | Medium |
| Scottie Scheffler | FRL | +900 | 1.0u | Medium |

**Portfolio Risk:** High concentration on one player (6.5 of 7.5 units on Matsuyama). If he underperforms, the entire card loses. The AI justified this based on Matsuyama showing consistent positive EV across all markets.

---

## Course Profile: Riviera Country Club

### Auto-Generated Profile

| Metric | Value | Meaning |
|--------|-------|---------|
| OTT Impact | 0.2675 | High — driving makes a big difference |
| APP Impact | 0.2756 | Highest — approach play is the biggest differentiator |
| ARG Impact | 0.0033 | Minimal — around-green play barely matters |
| Putt Impact | 0.1606 | Moderate — putting matters but less than ball-striking |

### Best Course Fits This Week

| Player | Course Fit | Rounds at Course |
|--------|-----------|-----------------|
| Xander Schauffele | 83.3 | 24 |
| Patrick Cantlay | 82.4 | 24 |
| Scottie Scheffler | 79.2 | 20 |
| Hideki Matsuyama | 77.0 | 20 |
| Collin Morikawa | 76.0 | 20 |

**Key Insight:** Riviera is a **ball-striker's course**. Combined OTT + APP impact (0.54) dwarfs ARG (0.003). Players who hit it well off the tee and into greens have a massive advantage.

---

## Worked Examples: Top 5 Players

### #1 Scottie Scheffler — Composite 85.9

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 79.2 | 40% | 31.68 |
| Form | 98.4 | 40% | 39.36 |
| Momentum | 59.4 | 20% | 11.88 |
| **Sub-total** | | | **82.92** |
| AI Adjustment | +3.0 | | +3.0 |
| **Final Composite** | | | **85.9** |

- **Course Fit (79.2):** 20 rounds at Riviera, confidence = 0.77. Strong historical SG. High DG decomposition percentile. Elite approach skill.
- **Form (98.4):** DG Win% 18.8%, Top10% 62.2% = near-max sim score. #1 SG:TOT across all windows. #1 DG skill and ranking globally.
- **Momentum (59.4):** Slight upward trend. Limited room to improve when already at the top.
- **Probability (blended):** Outright = 0.70 x 18.8% (DG) + 0.30 x softmax = ~14.6%. Market at +700 = 12.5% implied. EV positive but not at bet365 after vig.

### #2 Hideki Matsuyama — Composite 82.2

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 77.0 | 40% | 30.80 |
| Form | 88.0 | 40% | 35.20 |
| Momentum | 70.8 | 20% | 14.16 |
| **Sub-total** | | | **80.16** |
| AI Adjustment | +2.0 | | +2.0 |
| **Final Composite** | | | **82.2** |

- **Course Fit (77.0):** 20 rounds at Riviera. Elite ball-striker who fits the course profile perfectly.
- **Form (88.0):** DG Win% 2.9%, Top10% 26.1%. Strong but not Scheffler-level.
- **Momentum (70.8):** Solidly trending upward. Consistent improvement across windows.
- **Why he's the primary bet:** His blended probability significantly exceeds the market's implied probability across ALL markets. Outright: model 5.7% vs market 4.3% (+31% EV). Top 5: 23.9% vs 18.2%. Top 10: 40.7% vs 32.3%.

### #14 Xander Schauffele — Composite 67.9

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 83.3 | 40% | 33.32 |
| Form | 80.5 | 40% | 32.20 |
| Momentum | 12.1 | 20% | 2.42 |
| **Final Composite** | | | **67.9** |

- **Course Fit (83.3):** BEST in the field (24 rounds, elite history at Riviera)
- **Form (80.5):** Strong (DG Win% 4.4%, Top10% 31.0%)
- **Momentum (12.1):** COLD. Sharp decline across recent windows. This is the anchor.
- **Key Takeaway:** Market has Xander at +2000 (4.8% implied). DG says 4.4%. The model agrees he's talented but the cold momentum is a red flag. No value bet despite elite course fit.

### #26 Rory McIlroy — Composite 61.5

| Component | Score | Weight | Contribution |
|-----------|-------|--------|-------------|
| Course Fit | 72.5 | 40% | 29.00 |
| Form | 81.3 | 40% | 32.52 |
| Momentum | 10.0 | 20% | 2.00 |
| **Final Composite** | | | **63.5** |
| AI Adjustment | -2.0 | | -2.0 |
| **Final Composite** | | | **61.5** |

- **Form (81.3):** DG Win% 5.8%, Top10% 35.8%. Market darling with highest DG win probability.
- **Momentum (10.0):** COLDEST in the field. Severe decline across all windows.
- **Key Takeaway:** DG gives Rory the highest win probability in the field, but the model's momentum component heavily penalizes his downtrend. At +1000, the model sees him as overpriced.

---

## This Week's Picks & Rationale

### Summary: 10 Value Bets Found, 5 Recommended by AI

| Player | Market | Odds | Model% | Market% | EV | Bet? |
|--------|--------|------|--------|---------|-----|------|
| Hideki Matsuyama | Outright | +2200 | 5.7% | 4.3% | +31.4% | YES (1.5u) |
| Hideki Matsuyama | Top 5 | +450 | 23.9% | 18.2% | +31.5% | YES (1.5u) |
| Hideki Matsuyama | Top 10 | +210 | 40.7% | 32.3% | +26.3% | YES (1.5u) |
| Hideki Matsuyama | Top 20 | -120 | 61.6% | 54.5% | +12.9% | YES (2.0u) |
| Hideki Matsuyama | FRL | +2500 | 6.1% | 3.9% | +58.1% | Not selected |
| Scottie Scheffler | FRL | +900 | 12.6% | 10.0% | +26.1% | YES (1.0u) |
| Justin Rose | Top 5 | +750 | 12.1% | 11.8% | +2.8% | No (thin edge) |
| Ryan Gerard | Top 5 | +1100 | 8.5% | 8.3% | +2.5% | No (thin edge) |
| Si Woo Kim | Top 10 | +260 | 28.7% | 27.8% | +3.4% | No (thin edge) |
| Si Woo Kim | Top 20 | +100 | 51.7% | 50.0% | +3.4% | No (thin edge) |

### Why Matsuyama Dominates

The concentration on Matsuyama comes from a consistent positive gap between the blended model probability and market odds across every market:
- The 30% composite softmax component boosts his probability because he ranks #2 overall (strong course fit + form + momentum)
- DG's probabilities already rate him well, but the model's additional signals push him further
- This creates a consistent edge that the AI identified and built a portfolio around

### Best Available Odds

| Player | Market | bet365 | Better Price | Better Book |
|--------|--------|--------|-------------|-------------|
| Matsuyama | Outright | +2200 | +2522 | Pinnacle |
| Matsuyama | Top 5 | +450 | +500 | BetOnline |
| Matsuyama | Top 10 | +210 | +215 | BetOnline |
| Matsuyama | Top 20 | -120 | -113 | Pinnacle |
| Scheffler | FRL | +900 | +1200 | BetOnline |

---

## Known Limitations & Future Work

### Current Limitations

1. **Backtester model divergence:** The backtester uses a simplified SG-weighted model, not the full course_fit+form+momentum live model. Backtest results validate a different model than what runs live. Aligning would require building full sub-model scores from PIT stats.

2. **Weather API limitation:** Open-Meteo could not provide forecasts for 2026-02-19 (likely beyond their forecast horizon). No weather adjustments were applied this week.

3. **Momentum may over-penalize elite players:** Xander Schauffele (#14 despite best course fit) and Rory McIlroy (#26 despite highest DG win probability) are being dragged down significantly by cold momentum. Elite players have less room to show rank improvement.

4. **No sample size adjustment in form:** A player with 1 recent round gets the same weight as a player with 20 rounds in the form model's windowed scoring.

5. **No time decay in course fit:** A T60 finish at Riviera 3 years ago weighs the same as one from last year. Recency weighting exists for course-specific stats but not for the rank-based scoring.

6. **Heavy portfolio concentration:** The AI concentrated 87% of units on one player. If Matsuyama has an off week (injury, bad draw, just not his week), the entire card fails. This is a structural risk.

### Future Improvements (Prioritized)

1. **Align backtester with live model** — Build course_fit, form, momentum scores from PIT stats so backtests validate the actual model
2. **Add form sample size adjustment** — Weight based on rounds available, not just window classification
3. **Add course fit time decay** — Weight recent course results more heavily
4. **Portfolio diversification rules** — Cap maximum exposure to any single player (e.g., 40% of total units)
5. **Momentum model refinement** — Reduce penalty for elite players whose rank can't improve much

### Database State After Run

- **Total rounds stored:** 127,420
- **2026 rounds:** 2,074
- **Predictions logged:** 354 for post-tournament scoring
- **Picks logged:** 5 AI-recommended bets
- **Course profile saved:** `data/courses/the_riviera_country_club.json`

---

*Generated by the Golf Betting Model v2.0. All scores, weights, and formulas documented here reflect the exact configuration used for this prediction run. Post-tournament review will automatically run next week to score all predictions and update the learning system.*
