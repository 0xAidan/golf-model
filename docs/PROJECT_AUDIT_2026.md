# Golf Model — Full Project Audit (March 2026)

**Purpose:** Identify what’s missing, why +EV strategies are slow to find, and whether the flow is logical. Recommend concrete improvements.

**Scope:** Pipeline flow, value detection, calibration, learning, backtester/research, and card grading evidence.

---

## 1. Executive Summary

| Finding | Severity |
|--------|----------|
| **Placement calibration is never applied** — curve is updated post-tournament but `value.py` never uses `get_calibration_correction()` for EV | **High** |
| **Placement “value” underperforms; matchups outperform** — card grading shows placement Best Bets 0–3 repeatedly; matchup-heavy cards ~10–4, +46% ROI | **High** |
| **Model is 95% DG / 5% composite** — we add little edge on placements; DG is already efficient there | **Medium** |
| **Research cycle is slow** — 3 cycles × 3 candidates, holdout gates, walk-forward = many events before a strategy can promote | **Medium** |
| **Flow is logical** — sync → rolling → composite → value (blend vs market) → portfolio → card; learning and adaptation close the loop | **OK** |

**Bottom line:** The process is coherent. The main gaps are: (1) calibration is computed but not used when finding value, and (2) placement markets are structurally harder for us than matchups, so progress will feel slow until we either apply calibration, lean further into matchups, or both.

---

## 2. What Is Missing

### 2.1 Calibration not applied in the value path

- **Intended design (from `docs/plans/2026-02-23-adaptive-roi-model-v4.md`):**  
  *“In find_value_bets, after computing model_prob, if calibration has 50+ samples for that bucket, multiply model_prob by get_calibration_correction(model_prob). Use corrected prob for EV.”*
- **Current behavior:**  
  - `learning.post_tournament_learn()` → `update_calibration_curve()` → `calibration_curve` table is updated.  
  - `calibration.get_calibration_correction(probability)` exists and is tested.  
  - **`value.find_value_bets()` never calls `get_calibration_correction()`.**  
- **Effect:** Placement probabilities are not corrected by our empirical hit rates, so EV and “value” flags are based on uncorrected probs. We’re leaving the main feedback lever unused.

**Recommendation:** In `find_value_bets()`, after computing `model_prob` (and before blending with DG if desired), apply calibration when the bucket has ≥50 samples:

- `corrected_prob = model_prob * get_calibration_correction(model_prob)` (or apply to the blended prob if that’s the one used for EV).
- Use the corrected probability for EV and for the `is_value` gate. Optionally keep `model_prob` in the card for transparency and add a `calibration_corrected` flag or field.

### 2.2 Other gaps (lower priority)

- **Placement calibration by market:**  
  `calibration_curve` is global. If we want placement-specific correction (e.g. top10 vs top20), we’d need bucket keys by `bet_type` and enough samples per (bucket, bet_type). Not blocking.
- **Full pipeline integration test:**  
  AGENTS_KNOWLEDGE notes there’s no end-to-end pipeline test. Adding one would catch regressions when touching value/learning.
- **Prompts in code:**  
  `prompts.py` is string literals; externalizing or versioning would help iteration. Not blocking for +EV.

---

## 3. Why It’s Taking So Long to Find +EV Strategies

### 3.1 Structural factors

1. **Blend is 95% DG / 5% model**  
   Placement probabilities are dominated by Data Golf. Our composite adds a small tilt. So most “value” we see is either (a) DG vs market (already efficient) or (b) noise from the 5% model component. Until we’re well-calibrated or increase model weight with evidence, placement edge will be rare.

2. **EV thresholds are high**  
   Defaults (e.g. 8% placement, 15% outright) were raised to filter noise. That correctly reduces bad bets but also reduces the number of bets that surface. So “finding +EV” feels slow because we’re deliberately strict.

3. **Placement markets are efficient**  
   Card grading (e.g. `docs/card_grading_report_2026.md`) shows placement-heavy “Best Bets” going 0–3 repeatedly (Arnold Palmer 20260308, Cognizant 20260228). The market is tough on top5/top10/top20; our edge there is limited.

4. **Matchups perform better**  
   Same grading: matchup-heavy cards (e.g. Arnold Palmer 20260304 archive, Cognizant 20260226) go ~10–4 and ~6–7–2 with strong ROI. So +EV is being “found” more in matchups than in placements. The system is already biased toward matchups (`BEST_BETS_MATCHUP_ONLY = True`); the slowness is mostly on the placement side.

### 3.2 Process / feedback factors

5. **Calibration not used**  
   We build a calibration curve from results but don’t use it when computing EV. So we don’t correct for systematic over/under-confidence. That lengthens the time to “believe” our own edges.

6. **Research cycle is heavy**  
   Autoresearch: 3 cycles, 3 candidates per cycle, holdout gates, walk-forward backtests. Promotion requires enough events and passing guardrails. So strategy discovery is intentionally slow and conservative.

7. **Weight retune needs data**  
   `retune()` only saves new weights when `total_picks >= 10`. Early on, few tournaments mean slow weight updates. Once you have enough scored picks, the loop does close (retune → save_new_weights → get_active_weights → next composite).

---

## 4. Flow and Process — Is It Logical?

### 4.1 Pipeline (run_predictions / GolfModelService)

Flow is **logical**:

1. Detect event → backfill rounds (if enabled).  
2. Sync DG (predictions, decompositions, field, skill, rankings, approach).  
3. Rolling stats (8/12/16/24/all windows).  
4. Course profile load (or auto-generate from decompositions).  
5. Composite (course_fit + form + momentum; optional weather).  
6. Optional AI pre-tournament → adjustments applied to composite.  
7. Value: blend DG + model probs, EV vs market, threshold + phantom-EV/speculative filters.  
8. Matchup value (Platt-style, DG/model blend, agreement rule).  
9. Portfolio/diversification, exposure caps.  
10. Card + methodology output.

Order is correct: no future data, single orchestration in `GolfModelService`, shared code paths for CLI and app.

### 4.2 Post-tournament learning

Also **logical**:

1. Ingest results → score picks → update `prediction_log` outcomes.  
2. Aggregate market performance (adaptation).  
3. Evaluate AI adjustments.  
4. Course-specific weight updates (when applicable).  
5. Global retune → suggest_weight_adjustment → save when ≥10 scored picks.  
6. Update calibration curve (and matchup Platt params when 100+ samples).  
7. Bankroll/CLV when feature flags on.

Missing piece: **nothing in this pipeline feeds “corrected probability” back into the next run’s value step**, because `value.find_value_bets()` doesn’t call calibration.

### 4.3 Backtester / research

- Walk-forward, PIT data, same model code as live → **correct**.  
- Proposals → backtest → evaluation → dossier → promotion gates → **coherent**.  
- Slow discovery is by design (holdout, significance, guardrails).

---

## 5. Recommended Improvements

### 5.1 High impact

1. **Use calibration in value (placement)**  
   - In `value.find_value_bets()`, after final `model_prob` (or blended prob) is set:  
     - `corrected = model_prob * get_calibration_correction(model_prob)` (clamp to a sane range if needed).  
     - Use `corrected` for `compute_ev()` and for `is_value`.  
   - Only apply when the bucket has ≥50 samples (already enforced inside `get_calibration_correction`).  
   - Document in methodology when calibration was applied (e.g. “placement probs corrected by empirical calibration”).

2. **Double down on matchups in product and messaging**  
   - Card grading already supports: “prioritize cards that include Matchup Value Bets (real odds)” and methodology that produces them.  
   - Ensure matchup odds are always fetched when available (no silent skip).  
   - Consider a dashboard or summary that separates placement vs matchup ROI so you can see that +EV is coming from matchups first.

### 5.2 Medium impact

3. **Optional: relax matchup EV threshold for more candidates**  
   - `MATCHUP_EV_THRESHOLD` is 5%; placement is 8%+. If matchups are the main edge, you could test a slightly lower matchup threshold (e.g. 4%) and rely on diversification/cap to limit exposure.  
   - Do this as an A/B or shadow run so you don’t increase noise.

4. **Increase model blend for placements only when calibrated**  
   - Right now 95/5 is safe. When calibration shows model Brier ≤ DG (or similar) on placements, consider a small increase in model weight for that market (e.g. 90/10) in config, with a feature flag or profile.  
   - Keep outright/top5 more conservative until evidence supports it.

5. **Research cycle speed (optional)**  
   - If autoresearch is too slow: reduce holdout size or max candidates per cycle in `autoresearch/cycle_config.json`, or run more candidates in parallel.  
   - Trade-off: faster iteration vs higher risk of overfitting; document any config change.

### 5.3 Lower priority

6. **Add an end-to-end pipeline test**  
   - One test that runs GolfModelService (or run_predictions) with minimal data and checks that value_bets and card are produced (and optionally that calibration is applied when curve is populated).  
   - Helps avoid regressions when changing value/learning.

7. **Segment calibration by bet_type later**  
   - If we ever have 50+ samples per (bucket, bet_type), we could add `get_calibration_correction(probability, bet_type)` and use it in `find_value_bets` per market.  
   - Not necessary for the first calibration fix.

---

## 6. Summary Table

| Area | Status | Action |
|------|--------|--------|
| Pipeline flow | Logical | No change needed |
| Post-tournament learning | Logical | No change needed |
| Calibration curve | Updated but unused in value | **Apply in find_value_bets** |
| Placement vs matchup | Matchups outperform | Lean into matchups; treat placement as secondary until calibrated |
| EV thresholds | High by design | Keep; optionally test lower for matchups only |
| Research cycle | Slow by design | Optional tuning if you need faster strategy discovery |
| Weight retune | Closes loop at ≥10 picks | No change |

Implementing **calibration in the value path** and **clear separation of matchup vs placement performance** in reporting will address the main “missing” piece and set expectations that +EV will show up more in matchups than in placements until the model is better calibrated.
