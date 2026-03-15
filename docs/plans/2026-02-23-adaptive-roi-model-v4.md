# Adaptive ROI Model v4 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement automated market adaptation, calibration fixes, real matchup integration, and AI adjustment tracking so the bot improves ROI with full backtesting and validation.

**Architecture:** Add `market_performance` and `calibration_curve` tables; a new `adaptation` module that computes rolling ROI by market and returns graduated EV/stake/suppress rules; update `value.py` for 95% DG blend and adaptation-aware thresholds; integrate DataGolf matchup odds into card pipeline; log AI adjustments and evaluate post-tournament. All numbers trace to DB/API (no hallucinations).

**Tech Stack:** Python 3, SQLite (src/db.py), pytest, existing backtester (backtester/strategy.py), DataGolf API.

**Design reference:** `docs/plans/2026-02-23-adaptive-roi-model-v4-design.md`

---

## Phase 1: Market Performance Tracker

### Task 1.1: Add market_performance table and migration

**Files:**
- Modify: `src/db.py` (init_db schema + _run_migrations)

**Step 1: Add table in init_db**

In `init_db()`, after `prediction_log` CREATE TABLE, add:

```sql
CREATE TABLE IF NOT EXISTS market_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_type TEXT NOT NULL,
    tournament_id INTEGER REFERENCES tournaments(id),
    bets_placed INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    pushes INTEGER NOT NULL DEFAULT 0,
    units_wagered REAL NOT NULL DEFAULT 0,
    units_returned REAL NOT NULL DEFAULT 0,
    roi_pct REAL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_market_perf_type ON market_performance(market_type);
CREATE INDEX IF NOT EXISTS idx_market_perf_tournament ON market_performance(tournament_id);
```

**Step 2: Run init and verify**

Run: `python -c "from src.db import init_db; init_db(); print('ok')"`
Expected: ok, no error.

**Step 3: Commit**

```bash
git add src/db.py
git commit -m "feat: add market_performance table"
```

---

### Task 1.2: Aggregate market performance from prediction_log/pick_outcomes

**Files:**
- Create: `src/adaptation.py`
- Test: `tests/test_adaptation.py`

**Step 1: Write failing test**

In `tests/test_adaptation.py`:

```python
"""Tests for market performance aggregation and adaptation logic."""
import pytest
from src.adaptation import aggregate_market_performance_for_tournament, compute_roi_pct

def test_compute_roi_pct():
    assert compute_roi_pct(10.0, 12.0) == 20.0
    assert compute_roi_pct(10.0, 8.0) == -20.0
    assert compute_roi_pct(0, 0) is None
```

**Step 2: Run test (expect fail)**

Run: `pytest tests/test_adaptation.py -v`
Expected: FAIL (module/function not found).

**Step 3: Implement minimal code**

Create `src/adaptation.py`:

```python
"""Market performance tracking and graduated adaptation."""
from src import db

def compute_roi_pct(wagered: float, returned: float) -> float | None:
    if wagered is None or wagered <= 0:
        return None
    return round((returned - wagered) / wagered * 100.0, 2)
```

**Step 4: Run test**

Run: `pytest tests/test_adaptation.py::test_compute_roi_pct -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/adaptation.py tests/test_adaptation.py
git commit -m "feat: adaptation compute_roi_pct and test"
```

---

### Task 1.3: Implement aggregate_market_performance_for_tournament

**Files:**
- Modify: `src/adaptation.py`
- Modify: `tests/test_adaptation.py`

**Step 1: Write failing test**

Add to `tests/test_adaptation.py`:

```python
def test_aggregate_market_performance_for_tournament_empty():
    from src.adaptation import aggregate_market_performance_for_tournament
    result = aggregate_market_performance_for_tournament(99999)
    assert result == {}
```

**Step 2: Run test**

Run: `pytest tests/test_adaptation.py::test_aggregate_market_performance_for_tournament_empty -v`
Expected: FAIL or pass if you stubbed. Implement so it reads from prediction_log + results (or pick_outcomes), groups by bet_type (map to market_type: outright, top5, top10, top20, matchup), sums wagered/returned, computes ROI, and upserts into market_performance. Return dict of {market_type: {bets_placed, wins, losses, pushes, units_wagered, units_returned, roi_pct}}.

**Step 3: Implement**

- Read prediction_log for tournament_id where actual_outcome is not null; join or use results for outcome.
- Map bet_type to market_type (outright->outright, top5->top5, top10->top10, top20->top20, matchup->matchup).
- For each market: sum profit + stake = returned, count wins/losses/pushes, compute ROI.
- Upsert one row per (market_type, tournament_id) in market_performance.
- Return the summary dict.

**Step 4: Run all adaptation tests**

Run: `pytest tests/test_adaptation.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/adaptation.py tests/test_adaptation.py
git commit -m "feat: aggregate market performance from prediction_log"
```

---

### Task 1.4: Rolling window and get_rolling_market_performance

**Files:**
- Modify: `src/adaptation.py`
- Modify: `tests/test_adaptation.py`

**Step 1: Write failing test**

Add test that get_rolling_market_performance(market_type, last_n=20) returns rows ordered by tournament date, limited to last_n bets across tournaments.

**Step 2: Implement**

- get_rolling_market_performance(market_type, last_n=20): query market_performance for market_type, join tournaments for date, order by date desc, then sum bets_placed until cumulative >= last_n (or take full rows for last N bets). Return list of dicts with tournament_id, bets_placed, wins, losses, pushes, units_wagered, units_returned, roi_pct.

**Step 3: Run tests and commit**

```bash
pytest tests/test_adaptation.py -v
git add src/adaptation.py tests/test_adaptation.py
git commit -m "feat: rolling market performance window"
```

---

## Phase 2: Graduated Response System

### Task 2.1: get_adaptation_state(market_type)

**Files:**
- Modify: `src/adaptation.py`
- Modify: `tests/test_adaptation.py`

**Step 1: Write failing test**

```python
def test_get_adaptation_state_normal():
    # Mock or seed rolling performance with ROI 5% -> state "normal", base_ev_threshold 0.05
    pass
def test_get_adaptation_state_frozen():
    # ROI -50% -> state "frozen", suppress True
    pass
def test_get_adaptation_state_min_sample():
    # Fewer than 15 bets -> state "normal" (no action until 15+ bets)
    pass
```

**Step 2: Implement**

- get_adaptation_state(market_type, min_bets=15): call get_rolling_market_performance(market_type, last_n=20). If total bets < min_bets, return {state: "normal", ev_threshold: 0.05, stake_multiplier: 1.0, suppress: False}.
- Else compute rolling ROI. Apply:
  - ROI >= 0: normal (ev 0.05, mult 1.0, suppress False)
  - -20% < ROI < 0: caution (ev 0.08, mult 1.0, suppress False)
  - -40% < ROI <= -20%: cold (ev 0.12, mult 0.5, suppress False)
  - ROI <= -40%: frozen (suppress True)
  - If 0 wins in last 10+ bets: suppress True (emergency freeze)
- Return dict: state, ev_threshold, stake_multiplier, suppress, roi_pct, total_bets.

**Step 3: Run tests and commit**

```bash
pytest tests/test_adaptation.py -v
git add src/adaptation.py tests/test_adaptation.py
git commit -m "feat: graduated adaptation state by market type"
```

---

### Task 2.2: Recovery logic (unfreeze)

**Files:**
- Modify: `src/adaptation.py`
- Modify: `tests/test_adaptation.py`

**Step 1: Test**

When market is frozen, if in the "tracking" data we would have 2 wins in next 5 bets, unfreeze to "cold". Implement as part of get_adaptation_state (e.g. check recent outcomes from prediction_log for that market).

**Step 2: Implement and commit**

```bash
pytest tests/test_adaptation.py -v
git add src/adaptation.py tests/test_adaptation.py
git commit -m "feat: recovery unfreeze when 2 wins in 5"
```

---

## Phase 3: Probability Calibration

### Task 3.1: DG 95% blend in value.py

**Files:**
- Modify: `src/value.py`

**Step 1: Write failing test**

In `tests/test_value.py`: test that when DG prob is available, blended probability is 0.95 * dg_prob + 0.05 * softmax_prob (or equivalent).

**Step 2: Change BLEND_WEIGHTS**

In `src/value.py`, set all BLEND_WEIGHTS to {"dg": 0.95, "model": 0.05}.

**Step 3: Run tests**

Run: `pytest tests/test_value.py -v`
Expected: Update any test that asserted old blend; then PASS.

**Step 4: Commit**

```bash
git add src/value.py tests/test_value.py
git commit -m "feat: DG probability weight 95% for calibration"
```

---

### Task 3.2: Calibration curve table and logging

**Files:**
- Modify: `src/db.py` (add calibration_curve table)
- Create: `src/calibration.py`
- Test: `tests/test_calibration.py`

**Step 1: Add table**

In `src/db.py`, add:

```sql
CREATE TABLE IF NOT EXISTS calibration_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    probability_bucket TEXT NOT NULL,
    predicted_avg REAL NOT NULL,
    actual_hit_rate REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    correction_factor REAL NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

**Step 2: Implement calibration.py**

- log_calibration_bucket(bucket, predicted_avg, actual_hit_rate, sample_size): compute correction_factor = actual_hit_rate / predicted_avg if predicted_avg > 0 else 1.0; upsert into calibration_curve.
- get_calibration_correction(probability): find bucket containing probability, return correction_factor or 1.0 if sample_size < 50.
- After each tournament (in learning.py or post_tournament_learn), compute buckets from prediction_log and update calibration_curve.

**Step 3: Unit tests and commit**

```bash
pytest tests/test_calibration.py -v
git add src/db.py src/calibration.py tests/test_calibration.py
git commit -m "feat: calibration curve table and correction factor"
```

---

### Task 3.3: Apply correction factor in find_value_bets (optional, after 50+ per bucket)

**Files:**
- Modify: `src/value.py`

**Step 1:** In find_value_bets, after computing model_prob, if calibration has 50+ samples for that bucket, multiply model_prob by get_calibration_correction(model_prob). Use corrected prob for EV.

**Step 2: Test and commit**

```bash
pytest tests/test_value.py tests/test_calibration.py -v
git add src/value.py
git commit -m "feat: apply calibration correction when sample sufficient"
```

---

## Phase 4: Adaptation-Aware EV and Card

### Task 4.1: Use adaptation state in value finding

**Files:**
- Modify: `src/value.py`
- Modify: `run_predictions.py` or entry point that calls find_value_bets

**Step 1:** For each bet_type, call get_adaptation_state(market_type). If suppress, skip that market (return no value bets for it). Else use ev_threshold from state instead of MARKET_EV_THRESHOLDS. Pass stake_multiplier through to card so card can show recommended stake (e.g. 0.5u when cold).

**Step 2: Test**

- Unit test: when suppress=True for outright, find_value_bets returns no outrights.
- Unit test: when ev_threshold=0.12, only bets with EV >= 12% are returned.

**Step 3: Commit**

```bash
git add src/value.py src/adaptation.py run_predictions.py tests/test_value.py tests/test_adaptation.py
git commit -m "feat: apply adaptation state to value bets and stakes"
```

---

### Task 4.2: Ensure market performance is updated after each tournament

**Files:**
- Modify: `src/learning.py`

**Step 1:** In post_tournament_learn, after scoring picks and updating prediction_log, call aggregate_market_performance_for_tournament(tournament_id) and ensure market_performance rows are written.

**Step 2: Test and commit**

```bash
pytest tests/test_learning.py tests/test_adaptation.py -v
git add src/learning.py
git commit -m "feat: update market performance after each tournament"
```

---

## Phase 5: Real Sportsbook Matchup Integration

### Task 5.1: Fetch matchup odds from DataGolf

**Files:**
- Modify: `src/datagolf.py` or `src/odds.py`
- Test: `tests/test_odds.py` or manual

**Step 1:** Add function to fetch matchup odds (e.g. historical-odds/matchups or current odds endpoint). Return list of {player_a, player_b, book, odds_a, odds_b} or equivalent. Check DataGolf API docs for exact endpoint.

**Step 2: Test**

- Unit test or integration test: call fetch, assert structure and non-empty for a known event.

**Step 3: Commit**

```bash
git add src/odds.py src/datagolf.py tests/test_odds.py
git commit -m "feat: fetch real sportsbook matchup odds from DataGolf"
```

---

### Task 5.2: Score matchup EV and filter to bettable only

**Files:**
- Modify: `src/matchups.py` or new `src/matchup_value.py`
- Modify: `src/card.py`

**Step 1:** For each offered matchup (from API), get composite scores for both players. Compute model win prob for player_a; get odds for player_a. Compute EV. Only include matchups where EV >= adaptation ev_threshold for "matchup" market.

**Step 2:** Card: replace or supplement "Core Picks: Matchup Edges" with "Matchup Value Bets" table: Pick, vs, Odds, Model Edge, EV%, Book. No model-only pairings without odds.

**Step 3: Test and commit**

```bash
pytest tests/test_matchups.py tests/test_value.py -v
git add src/matchups.py src/card.py src/adaptation.py
git commit -m "feat: real matchup odds only, EV and card output"
```

---

## Phase 6: AI Adjustment Tracking

### Task 6.1: Log AI adjustments

**Files:**
- Modify: `src/db.py` (add ai_adjustments table if not exists)
- Modify: `src/ai_brain.py` or wherever AI returns player adjustments

**Step 1:** Table: ai_adjustments (id, tournament_id, player_key, adjustment_value, reasoning, created_at). On each AI run that returns adjustments, insert one row per player.

**Step 2:** Ensure every AI adjustment written to the card is also written to ai_adjustments.

**Step 3: Test and commit**

```bash
git add src/db.py src/ai_brain.py
git commit -m "feat: log AI adjustments to ai_adjustments table"
```

---

### Task 6.2: Post-tournament AI adjustment evaluation

**Files:**
- Modify: `src/learning.py`
- Create: `src/adaptation.py` helper or use existing

**Step 1:** After tournament, for each ai_adjustment: compare player's actual finish vs baseline (composite rank). Score whether adjustment was helpful (e.g. +adjustment and player beat baseline, or -adjustment and player missed baseline). Aggregate: total_helpful, total_harmful, net_effect.

**Step 2:** If over 10+ tournaments and 50+ adjustments, net_effect < 0: set ai_adjustment_cap = 2 (in config or db). If after 5 more tournaments still negative: set ai_adjustments_enabled = False. Apply cap/disable in composite or card when applying AI adjustments.

**Step 3: Test and commit**

```bash
pytest tests/test_learning.py tests/test_adaptation.py -v
git add src/learning.py src/adaptation.py src/ai_brain.py
git commit -m "feat: evaluate AI adjustments and auto-disable if harmful"
```

---

## Phase 7: Backtest and Assertions

### Task 7.1: Backtest replay with new logic

**Files:**
- Modify: `backtester/strategy.py` or add `backtester/replay_adaptive.py`
- Test: `tests/test_backtest_adaptive.py`

**Step 1:** Replay Genesis (and WM Phoenix, Pebble Beach if possible) with: 95% DG blend, adaptation state computed from prior data only (no future leakage). Assert Genesis matchups 5-2-1, +2.64u; assert outright would be frozen after ~6 bets.

**Step 2:** Document commands: e.g. `pytest tests/test_backtest_adaptive.py -v` and `python -m backtester.replay_adaptive --event genesis --year 2026`.

**Step 3: Commit**

```bash
git add backtester/ tests/test_backtest_adaptive.py
git commit -m "test: backtest adaptive logic matches Genesis post-mortem"
```

---

### Task 7.2: Shadow mode flag

**Files:**
- Modify: `run_predictions.py` or config

**Step 1:** Add SHADOW_MODE or config: when True, run new adaptation + DG blend and log recommended bets to a separate shadow file (e.g. output/shadow_*.md) but do not change main card. Run for 2 tournaments, then flip to False after validation.

**Step 2: Commit**

```bash
git add run_predictions.py output/
git commit -m "feat: shadow mode for adaptive system validation"
```

---

### Task 7.3: No-hallucination check

**Files:**
- Modify: `src/card.py` (and any place that outputs numbers)

**Step 1:** Audit card output: every number (EV, odds, composite, model prob) must come from a function that reads from DB or API. Add comments or asserts where we use derived values. If any "estimated" value is shown, label it explicitly in the card (e.g. "Estimated EV (uncalibrated)").

**Step 2: Commit**

```bash
git add src/card.py
git commit -m "chore: ensure card numbers trace to DB/API, no unlabeled estimates"
```

---

## Execution Handoff

After saving the plan, offer execution choice:

**Plan complete and saved to `docs/plans/2026-02-23-adaptive-roi-model-v4.md`. Two execution options:**

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task or phase, review between tasks, fast iteration.

**2. Parallel Session (separate)** — Open a new session with executing-plans, batch execution with checkpoints.

Which approach do you want?
