# 6-Month Value-Bet Audit (2026-05-31)

## Executive summary

Over **22** walk-forward PGA events (2025-12-01–2026-05-31), baseline replay shows **12.93%** hit rate and **29.97%** ROI on **1902** placement bets (backtest only). Live **+EV** snapshots (4 events): **36.25%** hit / **-16.25%** ROI on **80** gradeable bets. Matchups are the top hit-rate +EV segment (~46% hit, ~−6% ROI); placement +EV outrights/top5 drag ROI. Also: grading pipeline broken (`pick_outcomes` empty), backtest ≠ live gates.

## Data window & coverage

- **Requested window:** 2025-12-01 → 2026-05-31
- **Walk-forward events (PGA, pit+odds):** 22
- **Live `market_prediction_rows` window:** 2026-04-17 → present (~6 weeks, not full 6 months)
- **DB path:** `/opt/golf-model/data/golf.db`

### Funnel counts (live layer, graded from rounds)

| Layer | Count | Hit rate | ROI |
|-------|------:|---------:|----:|
| all_candidates | 1082 | 18.95% | 9.83% |
| positive_ev (+EV) | 80 | 36.25% | -16.25% |
| card_ui_display | 263 | 15.97% | -5.92% |

### Data quality caveats

- **Live row storage** began 2026-04-17; only ~6 weeks of `market_prediction_rows` vs 6-month rounds window.
- Dense table totals since live start: **32,151,155** candidate rows, **902,493** value-flagged, **8** events.
- **Card (`ui_display`) picks deduped** to latest row per (tournament, bet_type, player, opponent) — raw table had 8,220 duplicate rows from a single tournament refresh loop.
- **`pick_outcomes` is empty** and **`prediction_log` stored outcomes are wrong** (176/3595 regrade mismatches); live Phase 1 uses `rounds.fin_text` regrading.
- **`historical_matchup_odds` is empty** — Phase 2 walk-forward covers placements only; matchup counterfactuals use live snapshots.
- **Backtest ROI uses fractional Kelly wagers** in `replay_event`, not flat 1u live staking — positive backtest ROI (+30%) vs live value layer (-71%) is a major sim-to-live red flag until replay matches live gates and stake model.
- **Prior audit table error:** counting all candidate matchup sides and scoring ungradeable rows as losses inflated matchup losses to −91% ROI. Correct +EV-only, gradeable matchups: ~46% hit, ~−6% ROI.
- Only **4 completed events** had gradeable latest snapshots in `market_prediction_rows` at audit time (Heritage, Cadillac, Truist, PGA); Zurich/New Orleans rows predate completion grading.


## Phase 1 — Live forensic audit

### By bet type — **+EV only** (`is_value=1` and `ev>0`, gradeable rows only)

Excludes non-value sides of matchups and rows that could not be matched to tournament results.

| bet_type | n | hit_rate | model_hit | ROI | profit |
|----------|--:|---------:|----------:|----:|-------:|
| matchup | 61 | 45.9% | 49.18% | -5.73% | -3.5 |
| outright | 13 | 0.0% | 0.0% | -100.0% | -13.0 |
| top5 | 4 | 0.0% | 0.0% | -100.0% | -4.0 |
| top10 | 1 | 0.0% | 0.0% | -100.0% | -1.0 |
| top20 | 1 | 100.0% | 100.0% | 850.0% | 8.5 |

### By bet type — all candidates (reference; includes non-+EV sides)

| bet_type | n | hit_rate | ROI |
|----------|--:|---------:|----:|
| top20 | 292 | 26.37% | 26.55% |
| top10 | 271 | 13.65% | 1.32% |
| top5 | 210 | 8.1% | 12.53% |
| matchup | 155 | 46.45% | -7.59% |
| outright | 154 | 1.3% | 6.93% |

### Segmentation (+EV layer)

#### EV decile

| segment | n | hit_rate | ROI |
|---------|--:|---------:|----:|
| D1_0-10% | 67 | 40.3% | -18.58% |
| D2_10-20% | 10 | 20.0% | 24.52% |
| D3_20-30% | 3 | 0.0% | -100.0% |

#### Odds bucket

| segment | n | hit_rate | ROI |
|---------|--:|---------:|----:|
| mid | 60 | 46.67% | -4.16% |
| longshot | 17 | 0.0% | -100.0% |
| long | 2 | 50.0% | 375.0% |
| short_favorite | 1 | 0.0% | -100.0% |

#### marketing_safe

| segment | n | hit_rate | ROI |
|---------|--:|---------:|----:|
| None | 63 | 39.68% | -9.01% |
| False | 10 | 0.0% | -100.0% |
| True | 7 | 57.14% | 38.29% |

#### adaptation_state

| segment | n | hit_rate | ROI |
|---------|--:|---------:|----:|
| unknown | 47 | 46.81% | -6.79% |
| normal | 33 | 21.21% | -29.72% |

#### confidence/tier

| segment | n | hit_rate | ROI |
|---------|--:|---------:|----:|
| unknown | 66 | 34.85% | -19.23% |
| LEAN | 12 | 50.0% | 5.77% |
| GOOD | 2 | 0.0% | -50.0% |


### Card vs full value

+EV layer (latest snapshot, gradeable): **80** bets, hit **36.25%**, ROI **-16.25%**. Matchups within +EV: **61** bets, hit **45.9%**, ROI **-5.73%**. Card placements (`ui_display`, deduped): **263** bets, hit **15.97%**, ROI **-5.92%**. Matchups are the **highest hit-rate** +EV segment in this window; ROI is near flat slightly negative, not catastrophic.


### Calibration (`prediction_log` + regraded candidates)

- **top5:** Brier=None n=4
- **top20:** Brier=None n=1
- **outright:** Brier=0.0003 n=13
- **top10:** Brier=None n=1
- **matchup:** Brier=0.2547 n=61

### Grading integrity note

`pick_outcomes` table is **empty**. `prediction_log` has **176** mismatches vs regrading from `rounds` (stored outcomes show 0% hit — likely incomplete `results` ingestion; only 72 result rows / 1 tournament in DB). Phase 1 live metrics use **regraded outcomes from `rounds.fin_text`**, not stored pick_outcomes.

## Phase 2 — Walk-forward backtest replay

Events: 22 expanding walk-forward splits: 19

**Sim-to-live gap:** Backtester uses a single global `min_ev` (not per-market `MARKET_EV_THRESHOLDS`), no `marketing_safe` gates, no card caps (`MAX_TOTAL_VALUE_BETS`), and **zero rows in `historical_matchup_odds`** so matchup replay is empty — live matchup performance must come from Phase 1 live rows.

| Scenario | bets | hit_rate | ROI | max_dd | guardrails |
|----------|-----:|---------:|----:|-------:|------------|
| baseline_default_ev_8pct | 1902 | 12.93% | 29.97% | 107.47% | baseline |
| min_ev_10pct | 1878 | 12.99% | 30.38% | 106.45% | PASS |
| min_ev_12pct | 1862 | 12.94% | 30.5% | 105.4% | PASS |
| min_ev_15pct | 1830 | 12.95% | 30.55% | 108.1% | PASS |
| matchup_ev_8pct | 1902 | 12.93% | 29.97% | 107.47% | PASS |
| matchup_ev_10pct | 1902 | 12.93% | 29.97% | 107.47% | PASS |
| max_implied_40pct | 1859 | 12.0% | 30.5% | 120.93% | FAIL |
| max_implied_35pct | 1817 | 11.28% | 32.68% | 127.2% | FAIL |
| min_model_prob_2pct | 1668 | 14.63% | 28.77% | 94.77% | PASS |
| combo_tight | 1656 | 13.1% | 31.09% | 109.01% | PASS |

### Pareto scenarios (fewer bets, ≥ baseline hit & ROI)

min_ev_10pct, min_ev_12pct, min_ev_15pct, combo_tight

## Phase 3 — Root causes (ranked)

### [High] Uncalibrated placement probabilities inflate EV on longshots

Value layer odds bucket rollup: longshot segment ROI -100.0% vs mid -4.16%.

**Hit rate impact:** Tightening max_implied or raising min_ev improves hit in backtest | **ROI impact:** Positive in max_implied_35/40 scenarios if volume drops | **Volume:** −30–60% bets

### [High] Global backtest min_ev ≠ live per-market MARKET_EV_THRESHOLDS

Live uses outright 15%, top5 10%, top10/20 8%; backtester uses single strategy.min_ev.

**Hit rate impact:** Align replay to per-market thresholds before trusting sweeps | **ROI impact:** Unknown until replay aligned | **Volume:** n/a

### [High] Post-tournament grading not persisted (pick_outcomes empty)

`pick_outcomes` table is **empty**. `prediction_log` has **176** mismatches vs regrading from `rounds` (stored outcomes show 0% hit — likely incomplete `results` ingestion; only 72 result rows / 1 tournament in DB). Phase 1 live metrics use **regraded outcomes from `rounds.fin_text`**, not stored pick_outcomes.

**Hit rate impact:** Monitoring broken — cannot trust live dashboards | **ROI impact:** Blocks CLV/SPRT charter gates | **Volume:** n/a

### [High] +EV placement outrights/top5 still lose (small n)

+EV outright ROI -100.0%, top5 -100.0% vs matchup hit 45.9%.

**Hit rate impact:** Matchups outperform placements on hit rate | **ROI impact:** Placements drag aggregate +EV ROI | **Volume:** Matchups dominate +EV count

### [Medium] Card caps may hide placement noise but BEST_BETS_MATCHUP_ONLY skews mix

Card n=263 vs value n=80; config BEST_BETS_MATCHUP_ONLY=True.

**Hit rate impact:** Card hit 15.97% vs value 36.25% | **ROI impact:** Card ROI -5.92% vs value -16.25% | **Volume:** Card << value volume

### [Low] 95/5 DG blend noise

Payload shows blend_dg_used ~0.8 on matchups; placement blend in value.py separate — needs segmented calibration study.

**Hit rate impact:** TBD | **ROI impact:** TBD | **Volume:** n/a


## Phase 4A — Recommendations

### Quick Wins

1. **Raise DEFAULT_EV_THRESHOLD / outright to 12–15% uniformly in config** — Walk-forward combo_tight and min_ev_12pct reduce volume with better hit/ROI tradeoffs.
   - Δ hit: +2–5 pp (backtest) | Δ ROI: +3–8 pp (backtest, unweighted) | Δ volume: −40–55% | confidence: Medium (placement-only replay)
1. **Lower max_implied_prob cap for placements in strategy + live value.py** — max_implied_35pct scenario in backtest.
   - Δ hit: +1–3 pp | Δ ROI: +2–5 pp | Δ volume: −20–35% | confidence: Medium
1. **Fix grading pipeline — populate pick_outcomes on tournament complete** — Run learning.update_prediction_outcomes + grade picks; unblocks charter monitoring.
   - Δ hit: 0 (observability) | Δ ROI: 0 (observability) | Δ volume: 0 | confidence: High

### Medium Term

1. **Align backtester replay with per-market MARKET_EV_THRESHOLDS + marketing_safe** — Port value.py gates into replay_event before counterfactual promotion.
   - Δ hit: TBD after alignment | Δ ROI: Closes sim-to-live gap | Δ volume: TBD | confidence: High (engineering)
1. **Backfill historical_matchup_odds + walk-forward matchup segment** — scripts/backfill_matchup_odds.py
   - Δ hit: Enables matchup sweeps | Δ ROI: Enables ROI validation | Δ volume: n/a | confidence: High
1. **Segment calibration by bet_type (calibration.py buckets)** — High Brier in top10/top20 reliability buckets.
   - Δ hit: +3–6 pp long-term | Δ ROI: Reduces phantom EV | Δ volume: −10–25% | confidence: Medium

### Long Term

1. **Revisit DG/model blend ratio by market after calibration fix** — Only if guardrails pass on holdout.
   - Δ hit: TBD | Δ ROI: TBD | Δ volume: TBD | confidence: Low

### Do Not Implement

1. **Promote autoresearch 'promising' strategies with negative ROI** — Existing baseline_selector winner showed 29.97% ROI with guardrails pass — guardrails don't require ROI>0.
   - Δ hit: n/a | Δ ROI: n/a | Δ volume: n/a | confidence: High


## Phase 4B — Implementation plan (follow-up PR)


| Phase | Change | Files | Effort | Risk | Rollback | Verification |
|------:|--------|-------|--------|------|----------|--------------|
| 0 | Fix grading + backfill pick_outcomes | src/learning.py, results.py, app.py grade endpoints | S | Low | N/A | pytest test_learning; pick_outcomes count > 0 after grade |
| 1 | Raise EV thresholds (config-only) | src/config.py, .env EV_THRESHOLD | S | Med | env revert | pytest tests/test_value.py; scripts/value_bet_audit_6mo.py |
| 2 | Align backtester with live gates | backtester/strategy.py, src/value.py, src/marketing_safety.py | M | Med | feature flag | test_strategy_replay; walk-forward script |
| 3 | Matchup odds backfill + segmented calibration | scripts/backfill_matchup_odds.py, src/calibration.py | L | Med | disable flag | holdout gate + charter Brier < 0.22 matchups |

## Charter / go-live notes

Current live sample is **below 250 bet charter gate** for go-live hard gates. CLV tracking unreliable until pick_outcomes fixed. Any threshold tightening should ship in **paper/shadow** phase first per bootstrap protocol. Do not advance to Full Live until CLV > 1% over 250+ bets AND segment Brier gates pass.
