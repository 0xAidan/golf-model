# Research Report: Multi-Tour Data Quality Issues in Golf Prediction Modeling

**Compiled:** 2026-02-28  
**Scope:** Deep research on PGA Tour, DP World Tour (European Tour), and Korn Ferry Tour data quality  
**Purpose:** Inform multi-tour prediction model design and data handling strategies

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Data Quality Differences by Tour](#2-data-quality-differences-by-tour)
3. [Strokes Gained Data Availability by Tour](#3-strokes-gained-data-availability-by-tour)
4. [Event-Level vs Round-Level SG Data](#4-event-level-vs-round-level-sg-data)
5. [Tour-Specific Model Adjustments](#5-tour-specific-model-adjustments)
6. [DataGolf's Multi-Tour Coverage](#6-datagolf-multi-tour-coverage)
7. [Handling Players Across Multiple Tours](#7-handling-players-across-multiple-tours)
8. [European Tour / DP World Tour Specific Data Gaps](#8-european-tour--dp-world-tour-specific-data-gaps)
9. [Recommendations for Multi-Tour Prediction Models](#9-recommendations-for-multi-tour-prediction-models)
10. [Practical Approaches for Golf Betting Models](#10-practical-approaches-for-golf-betting-models)

---

## 1. Executive Summary

Multi-tour golf prediction models face significant data quality asymmetries. The PGA Tour has the richest data ecosystem (ShotLink shot-level data, full SG categories, traditional stats), while the DP World Tour and Korn Ferry Tour rely on round-level data from public sources with partial SG category coverage. Field strength differences are material—players perform ~0.95 strokes better relative to field on the European Tour than on the PGA Tour (≈4 shots per event). Professional modelers use **field-strength-adjusted strokes gained** and **tour-specific baseline standard deviations** rather than applying identical model weights across tours. Event-level SG averages on the European Tour require imputation to round-level values; this is workable but reduces predictive precision compared to PGA Tour ShotLink data.

**Key Takeaways:**
- Same underlying methodology can be applied across tours, but tour-specific calibrations are necessary.
- European Tour SG category data is mostly event-level; round-level values are imputed from PGA Tour regression models.
- Korn Ferry Tour gained ShotLink Select in April 2024; SG category data is planned but not yet fully deployed.
- DataGolf provides the most comprehensive multi-tour coverage; European Tour raw data requires Scratch Plus subscription.
- Players who compete across tours should have all rounds (regardless of tour) included in skill estimates, with proper field-strength adjustment.

---

## 2. Data Quality Differences by Tour

### 2.1 PGA Tour

| Dimension | Availability |
|-----------|---------------|
| **Shot-level data** | Yes — ShotLink partnership (full coverage at most events) |
| **SG categories** | Yes — OTT, APP, ARG, PUTT at round level |
| **Traditional stats** | Yes — DD, DA, GIR, scrambling, proximity (from shot-level) |
| **Great/poor shots** | Yes — ShotLink events only |
| **Tee times** | Yes |
| **Historical depth** | 2004+ for core data |
| **Data source** | Direct PGA Tour partnership + pgatour.com |

### 2.2 DP World Tour (European Tour)

| Dimension | Availability |
|-----------|---------------|
| **Shot-level data** | No — IMG Arena provides SG category data, but not full ShotLink equivalent |
| **SG categories** | Partial — often event-level averages only; round-level requires imputation |
| **Traditional stats** | Limited — DD, DA, GIR primarily from PGA Tour; not derived from shot-level on Euro |
| **Great/poor shots** | No — PGA Tour ShotLink only |
| **Tee times** | Yes |
| **Historical depth** | Late 2017+ for SG categories; 2010+ for OWGR events |
| **Data source** | Public (owgr.com, europeantour.com); IMG Arena for SG categories |

### 2.3 Korn Ferry Tour

| Dimension | Availability |
|-----------|---------------|
| **Shot-level data** | Partial — ShotLink Select added April 2024 (voluntary GPS devices) |
| **SG categories** | Planned — not yet fully incorporated into public stats |
| **Traditional stats** | Limited |
| **Great/poor shots** | No |
| **Tee times** | Yes (where available) |
| **Historical depth** | 2004+ for round scores; SG categories evolving |
| **Data source** | Public (pgatour.com, owgr.com); ShotLink Select for select events |

### 2.4 Field Strength Comparison

DataGolf analysis of 36 players with ≥40 rounds on each tour (2010+, excluding WGCs/majors):

- **PGA Tour fields are ~0.95 strokes per round stronger** than European Tour fields.
- This accumulates to ~4 shots per event.
- All sampled players performed better relative to field on the European Tour than on the PGA Tour.
- Skill breakpoints between elite/average/low tiers differ by ~0.9 strokes between PGA and European tours.

**Source:** [DataGolf Blog — Field Quality US vs European Tours](https://datagolfblogs.ca/a-quick-look-at-differences-in-field-quality-on-the-us-and-european-tours/)

---

## 3. Strokes Gained Data Availability by Tour

### 3.1 Summary Table

| Tour | sg_total | sg_categories (OTT, APP, ARG, PUTT) | traditional_stats | Notes |
|------|----------|-------------------------------------|-------------------|-------|
| **PGA** | All rounds | Yes (ShotLink events) | yes/partial | Gold standard |
| **EUR (DP World)** | All rounds | Partial — often event-level; imputed to round-level | no | See Section 8 |
| **KFT** | All rounds | Evolving (ShotLink Select) | no | Improving post-2024 |
| **LIV** | Stroke play since 2024 | Round-level SG added Feb 2025 | no | Shot-level from LIV website |
| **Challenge Tour** | Yes | Partial | no | Similar to Euro |
| **CAN, SAM, CHAMP** | Yes | Varies | no | Developmental tours |

### 3.2 DataGolf Raw Data Notes (sg_categories)

From [DataGolf Raw Data Notes](https://datagolf.com/raw-data-notes):

- **sg_categories** values: `"yes"` = all rounds have SG category data; `"partial"` = some rounds; `"no"` = none.
- **traditional_stats** values: `"yes"` = shot-level derived; `"partial"` = some rounds; `"basic"` = DD/DA/GIR from non-shot-level; `"no"` = not available.
- Great shots / poor shots: **PGA Tour ShotLink events only**.
- Tee time data: PGA Tour and DP World Tour.

---

## 4. Event-Level vs Round-Level SG Data

### 4.1 Is Event-Level SG Sufficient?

**Short answer: No, but it can be used with imputation.**

- **Round-level SG** is the standard for prediction because:
  - Tournament outcomes are determined by round-by-round scoring.
  - Weighted averages over rounds (with recency decay) require round-level values.
  - SG category predictive power differs by category (OTT > APP > ARG > PUTT); round-level allows proper weighting.

- **Event-level SG** on the European Tour:
  - Euro Tour website typically publishes **event-level SG category averages**, not round-level.
  - DataGolf imputes round-level values using a regression model trained on PGA Tour data (event-level SG category averages + total SG per round → predicted SG category per round).
  - Imputed values: sum to event-level averages; show less variation than true round-level data; put more variation in APP and PUTT than OTT and ARG.

### 4.2 DataGolf FAQ (Euro SG Imputation)

> "For the (few) European Tour events where we have successfully collected the round-level data for each SG category, we obviously just display that. In the other events where only event averages are available, we have to get creative... We fit a regression model using PGA Tour data... to estimate the relationship between the relevant variables... We can then use that model to predict (i.e. impute) our missing round-level data on the European Tour."

**Practical takeaway:** Event-level SG is usable for skill estimation but is noisier than round-level. For prediction, imputation is acceptable; DataGolf slightly decreases the magnitude of SG category adjustments on the European Tour due to uncertainty.

---

## 5. Tour-Specific Model Adjustments

### 5.1 Should the Same Model Weights Apply Across All Tours?

**No.** Professional models use tour-specific adjustments:

1. **Baseline standard deviations** — Different baseline SDs per tour when projecting player consistency (field strength and variance differ).
2. **Low-data predictions** — Rookies/new players are of different quality on different tours; tour is an input for very low-data cases.
3. **Skill breakpoints** — Elite vs average vs low-tier breakpoints differ by ~0.9 strokes between PGA and European tours.
4. **54-hole leader calibration** — Model predicted 37.6% win rate for PGA Tour leaders (actual 39.5%); European Tour predicted 32% (actual 34.9%). Slight underestimation on both; Euro gap slightly larger.

### 5.2 DataGolf Model Talk (2026 Off-Season Tweaks)

- SD modeling now accounts for **skill level** and **driving distance** (longer hitters = higher variance).
- Baseline SD varies by tour.
- Shot-level adjustments (diminishing returns to SG, penalty stroke handling) apply primarily to PGA Tour ShotLink data.

### 5.3 SG Category Coefficients (PGA Tour)

From DataGolf methodology: predictive coefficients for historical SG categories on future total SG:

- β_OTT ≈ 1.2 (OTT also predicts future APP)
- β_APP ≈ 1.0
- β_ARG ≈ 0.9
- β_PUTT ≈ 0.6

These relationships are estimated on PGA Tour data. European Tour SG category usage relies on the assumption that these relationships hold; with only ~4 years of Euro SG category data, validation is limited.

---

## 6. DataGolf Multi-Tour Coverage

### 6.1 What DataGolf Provides for Non-PGA Tours

| Feature | PGA Tour | DP World Tour | Korn Ferry | LIV |
|---------|----------|---------------|------------|-----|
| Pre-tournament predictions | Yes | Yes | Yes | Yes |
| Live predictive model | Yes | Yes | — | — |
| Betting tools (EV, matchups, 3-balls) | Yes | Yes | — | — |
| Course fit adjustments | Yes | Yes (2021+) | — | — |
| Course history | Yes | Yes | — | — |
| Raw data / API | Yes | Yes (Scratch Plus) | Yes | Yes |
| SG category round-level | Yes | Imputed | Evolving | Yes (2024+) |

### 6.2 DataGolf European Tour Limitations

- **Raw European Tour data:** Requires **Scratch Plus** annual subscription.
- **Traditional stats (DD, DA, GIR, scrambling, proximity):** Primarily PGA Tour; limited for other tours.
- **Great shots / poor shots:** PGA Tour ShotLink only.
- **Hole score counts (birdies, pars, bogeys):** Added for EUR, KFT, LIV in Feb 2025.
- **Data sources:** European Tour data from public round-level sources (owgr.com, etc.); no shot-level partnership equivalent to PGA Tour.

### 6.3 Connectivity Requirement

To compare tours, events must be "connected" through overlapping players. E.g.:
- Mackenzie Tour ↔ Web.com ↔ PGA Tour (indirect connection).
- LIV ↔ Majors, DP World Tour, Asian Tour (current overlap).
- Sufficient overlap exists for reasonable field-strength estimates across OWGR-sanctioned tours.

---

## 7. Handling Players Across Multiple Tours

### 7.1 Core Principle

**Include all rounds from all tours in skill estimation**, with proper field-strength adjustment. A single strokes-gained measure (e.g. true SG) normalizes performance across courses and tours.

### 7.2 DataGolf Approach

- One **dg_id** per player; all rounds (PGA, Euro, KFT, etc.) contribute to skill estimate.
- Adjusted strokes-gained allows direct comparison: beating a Euro field by 2 strokes and a PGA field by 1 stroke can be expressed on a common scale.
- Field strength estimated via player overlap: if Player A beats PGA field by 0.5 and Euro field by 1.5, Euro field is ~1 stroke weaker (aggregated over many such comparisons).

### 7.3 Edge Cases: Sparse Data and Layoffs

For players with irregular schedules or long layoffs across tours:

- **Dual weighting:** Blend sequence-weighted (order of play) and time-weighted (days elapsed) averages.
- **Sparse data / layoffs:** More weight on sequence-weighted (recent rounds matter more).
- **Consistent schedule:** More weight on time-weighted.

### 7.4 Geographic Performance Effects

DataGolf research shows:
- DP World Tour players (non-American) underperform in U.S. events (e.g. Spanish -0.18, English -0.16 strokes).
- Same players overperform at The Open (links courses).
- American PGA Tour players underperform at The Open (-0.12 strokes).
- Consider geography/course type when interpreting cross-tour performance.

---

## 8. European Tour / DP World Tour Specific Data Gaps

### 8.1 SG Category Data

| Issue | Detail |
|------|--------|
| **Event-level vs round-level** | Euro Tour website publishes event-level SG averages; round-level often unavailable unless scraped immediately post-round (and often has errors). |
| **Missing players** | SG category data typically missing for a few players per event. |
| **Imputation** | Regression model (PGA Tour) used to impute round-level from event-level + total SG. |
| **Historical depth** | SG categories from late 2017; ~4 years of data limits validation of category-based adjustments. |
| **Shot location quality** | DP World Tour SG from IMG Arena; green locations may not use lasers, leading to minor putt inaccuracies (similar to LIV). |

### 8.2 Traditional Stats

- Driving distance, driving accuracy, GIR, scrambling, proximity: **PGA Tour only** (or basic/non-shot-level elsewhere).
- Added to PGA Tour data in 2022.

### 8.3 Course Fit

- European Tour course fit added in 2021; previously only course history.
- Less historical data than PGA Tour for course-specific parameter estimation.

---

## 9. Recommendations for Multi-Tour Prediction Models

### 9.1 Data Architecture

1. **Unified player ID** — Single ID across all tours (e.g. dg_id) to merge rounds.
2. **Field-strength adjustment** — All rounds converted to a common benchmark (e.g. average PGA Tour field or 125–175 ranked players) before aggregation.
3. **Tour-specific flags** — Retain tour and event metadata for filtering and tour-specific logic.

### 9.2 Model Design

1. **Tour-specific baselines** — Use different baseline SDs and skill breakpoints per tour.
2. **SG category usage** — Use categories where available (PGA, LIV); for Euro, apply smaller SG category adjustments due to imputation uncertainty.
3. **Fallback to total SG** — When SG categories unavailable, use total strokes-gained only.
4. **Low-data handling** — Tour is an input for rookies; consider sequence vs time weighting for irregular players.

### 9.3 Weighting and Adjustments

| Factor | Recommendation |
|--------|-----------------|
| **Recency** | Weight recent rounds more; ~70% on last 50 rounds for full-schedule players. |
| **SG category predictive power** | OTT > APP > ARG > PUTT; weight ball-striking more than short game in skill updates. |
| **Cross-tour normalization** | Always adjust for field strength; never compare raw SG across tours. |
| **Geographic/course effects** | Optional: adjust for U.S. vs international events, links vs parkland. |

### 9.4 Data Quality Tiers

| Tier | Tours | Use case |
|------|-------|----------|
| **Tier 1** | PGA (ShotLink) | Full model: SG categories, course fit, shot-level adjustments. |
| **Tier 2** | DP World, LIV | SG categories (imputed or from LIV); course history; no shot-level. |
| **Tier 3** | Korn Ferry, Challenge | Total SG only; tour-specific SD; limited course fit. |
| **Tier 4** | Developmental (CAN, SAM, etc.) | Total SG; strong regression to mean for low-data players. |

---

## 10. Practical Approaches for Golf Betting Models

### 10.1 If Building from Scratch

1. **Use DataGolf API** (Scratch Plus) for raw round-level data across 22+ tours.
2. **Implement field-strength adjustment** — Use player overlap method or DataGolf’s pre-computed field strengths.
3. **Start with total SG** — Add SG categories only for PGA Tour (and LIV if available).
4. **Tour-specific SDs** — Calibrate baseline variance per tour from historical residuals.

### 10.2 If Using DataGolf Predictions

- Use baseline + course history + fit model for PGA and DP World Tour.
- Expect slightly lower calibration on European Tour (e.g. 54-hole leaders).
- For Korn Ferry, use predictions but be aware of evolving data quality.

### 10.3 Handling Multi-Tour Players

- **Do not** restrict to one tour; include all OWGR + LIV rounds.
- Apply same weighting scheme (sequence + time) regardless of tour.
- For players with mostly Euro/KFT data playing a PGA event, increase uncertainty (wider confidence intervals).

### 10.4 Betting-Specific Considerations

- **EV thresholds** — Consider slightly higher thresholds for Euro/KFT events due to data quality.
- **Low-data cutoff** — Avoid matchups/3-balls when any player has &lt;~50 rounds (DataGolf’s approach).
- **Course fit** — Trust course fit more on PGA Tour; use cautiously on Euro.

---

## Sources

- DataGolf: [Predictive Model Methodology](https://datagolf.com/predictive-model-methodology/)
- DataGolf: [Raw Data Notes](https://datagolf.com/raw-data-notes)
- DataGolf: [FAQ](https://datagolf.com/frequently-asked-questions)
- DataGolf: [Comparing Pro Tours](https://datagolf.com/comparing-pro-tours/)
- DataGolf: [Model Talk — 2026 Off-Season Tweaks](https://datagolf.com/model-talk/2026-offseason-tweaks)
- DataGolf: [Model Talk — Weighting Rounds](https://datagolf.com/model-talk/weighting-rounds-sequence-or-time)
- DataGolf Blog: [Field Quality US vs European Tours](https://datagolfblogs.ca/a-quick-look-at-differences-in-field-quality-on-the-us-and-european-tours/)
- PGA Tour: [Korn Ferry Tour ShotLink Select](https://www.pgatour.com/korn-ferry-tour/article/news/latest/2024/04/19/korn-ferry-tour-tourcast-product-will-provide-real-time-shotlink-select-data)
- Sports Business Journal: [Korn Ferry ShotLink Select](https://www.sportsbusinessjournal.com/Articles/2024/04/19/pga-tour-korn-ferry-tour-shotlink-tourcast-data)
