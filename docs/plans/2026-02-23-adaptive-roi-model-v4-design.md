# Adaptive ROI-Focused Golf Model v4 — Design Document

**Date:** 2026-02-23  
**Status:** Approved  
**Goal:** Improve bot edge, prediction accuracy, and ROI through automated market adaptation, calibration fixes, real matchup integration, and AI adjustment tracking — with heavy oversight, testing, backtesting, and validation.

---

## 1. Market Performance Tracker

**Purpose:** Track wins, losses, and ROI by market type with rolling windows so the system can adapt automatically.

**Data model:**

| Column | Type | Description |
|--------|------|-------------|
| market_type | TEXT | outright, top5, top10, top20, matchup |
| tournament_id | INTEGER | FK to tournaments |
| bets_placed | INTEGER | Count of bets in this market for this tournament |
| wins | INTEGER | Full wins |
| losses | INTEGER | Full losses |
| pushes | INTEGER | Dead heats / pushes |
| units_wagered | REAL | Total units staked |
| units_returned | REAL | Total units returned (including stake) |
| roi_pct | REAL | (returned - wagered) / wagered * 100 |
| updated_at | TEXT | ISO timestamp |

**Rolling window:** Last 20 bets per market (configurable). Enough sample for signal, responsive to recent performance.

**Validation requirements:**
- Unit tests for ROI calculation (dead heats, pushes included)
- Backtest against historical data; calculations must match manual post-mortems
- Assert Genesis matchups replay as 5-2-1, +2.64u

---

## 2. Graduated Response System

**Purpose:** Automatically raise EV thresholds, reduce stakes, or suppress markets when a market type underperforms. Minimum 15-bet sample before any action.

**Thresholds (configurable):**

| Condition | Action |
|-----------|--------|
| ROI ≥ 0% | Normal: base EV threshold (e.g. 5%) |
| ROI -1% to -20% | Caution: raise EV threshold to 8% |
| ROI -21% to -40% | Cold: raise EV to 12%, recommend 0.5u stake |
| ROI < -40% | Frozen: suppress market entirely |
| 0 wins in 10+ consecutive bets | Emergency freeze regardless of ROI |

**Recovery:** When a frozen market would have 2 wins in next 5 bets (from tracking only), unfreeze to "Cold" status.

**Validation requirements:**
- Simulate graduated responses against backtested data
- Verify suppression would have prevented outright losses (0-8 → suppressed after ~5–6 losses)
- Test recovery logic for stability (no rapid freeze/unfreeze oscillation)

---

## 3. Probability Calibration

**Purpose:** Reduce overconfident model probabilities and improve EV accuracy.

**Immediate change:**
- DG probability weight: 80–90% → **95%**
- Model softmax weight: 10–20% → **5%**

**Empirical calibration curve (built over time):**

| Column | Description |
|--------|-------------|
| probability_bucket | 0–5%, 5–10%, 10–20%, etc. |
| predicted_avg | Average model-predicted probability in bucket |
| actual_hit_rate | Actual outcome rate |
| sample_size | Number of predictions in bucket |
| correction_factor | actual_hit_rate / predicted_avg |

After 50+ predictions per bucket, apply correction factors to future probability estimates.

**Validation requirements:**
- Backtest: confirm DG-heavy blend would have been more accurate historically
- Unit tests for calibration curve math
- Assert correction application (e.g. 10% predicted × 0.5 correction → 5% output)

---

## 4. Real Sportsbook Matchup Integration

**Purpose:** Only show matchup edges that are actually bettable.

**Changes:**
- Pull actual matchup odds from DataGolf `historical-odds/matchups` (and live equivalent for current events)
- Only display matchups offered by sportsbooks
- Compute EV using model composite edge + DG probability blend
- Apply graduated response system to matchup market

**Card output format:**
- Section "Matchup Value Bets" with: Pick, Opponent, Odds, Model Edge, EV%, Book
- No model-generated pairings without corresponding odds

**Validation requirements:**
- Spot-check matchup odds against live API
- Backtest matchup EV vs Genesis/Phoenix actual outcomes
- Confirm only bettable matchups appear on card

---

## 5. AI Adjustment Tracking

**Purpose:** Measure whether AI qualitative adjustments help or hurt; auto-reduce or disable if net negative.

**Changes:**
- Log every AI adjustment: player, tournament, adjustment value, reasoning
- Post-tournament: compare AI-adjusted players’ actual performance vs baseline
- Track cumulative AI adjustment accuracy

**Auto-disable logic:**
- If AI adjustments are net negative over 10+ tournaments AND 50+ adjustments: reduce cap from ±5 to ±2
- If still negative after 5 more tournaments: disable AI adjustments entirely

**Validation requirements:**
- Backtest Genesis AI adjustments (e.g. Rose -5, Fitzpatrick +3) vs outcomes
- Verify all adjustments are logged
- Unit tests for auto-disable threshold logic

---

## 6. Testing & Validation Framework

**Policy:** No code ships without passing the following.

1. **Unit tests** for every new calculation (ROI, EV, calibration, graduated response).
2. **Backtest replay** of WM Phoenix, Pebble Beach, Genesis with new logic; results must align with manual post-mortems.
3. **Assertion suite:**
   - Genesis matchups: 5-2-1, +2.64u
   - Pebble Beach AI picks: +2.50u
   - Outright market would be frozen after ~6 bets under new rules
4. **Shadow mode:** First 2 tournaments after release — run new system alongside old; compare outputs; do not act on new system until validated.
5. **No hallucinations:** Every number on the card must trace to a database value or API response. No "estimated" or "approximated" figures without explicit labeling.

---

## 7. Implementation Order (High Level)

1. Market performance tracker (schema + aggregation from existing results/picks)
2. Probability calibration (DG 95% blend + calibration curve schema and logging)
3. Graduated response system (threshold logic + minimum sample guardrails)
4. Real matchup integration (odds fetch + EV + card output)
5. AI adjustment tracking (logging + evaluation + auto-disable)
6. Full test suite and backtest assertions
7. Shadow mode wiring and validation period

---

## 8. References

- Brainstorming summary: Approach 2 (full automation) with minimum 15-bet sample guardrails
- Performance baseline: Genesis -4.19u (matchups +2.64u), Pebble Beach AI +2.50u, WM Phoenix -6.57u
- Existing: `prediction_log`, `picks`, `pick_outcomes`, `results`; `src/value.py` BLEND_WEIGHTS; `backtester/strategy.py`
