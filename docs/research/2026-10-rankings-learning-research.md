# Rankings and a measurable learning system

Research date: 2026-10-15. Scope: preserve the existing model and history, develop an independently evaluated challenger, and make weekly improvement inspectable. This note proposes experiments; it does not establish a betting edge or promise positive ROI or CLV.

## Recommendation

Make **rankings the front door**, with a player’s projected ability, movement, confidence, and component breakdown. Put price-sensitive decisions beside those rankings, then provide a separate record of what the forecasts and decisions actually achieved. A high rank and a good available bet are different quantities.

The highest-value next model is a **small, auditable distributional challenger**: shrink recent strokes-gained estimates toward a longer-term player baseline; learn recency and component weights using only earlier events; estimate residual variance; then derive probabilities for each market. Compare it against both the preserved model and an available market/DataGolf benchmark on the same events. Data Golf’s published method similarly predicts adjusted performance distributions and simulates finish outcomes, rather than treating a rank score as a probability. Its foundational methodology is dated 2021, with later changes documented separately. [Data Golf methodology](https://datagolf.com/predictive-model-methodology/)

## Current implementation: useful foundations and material gaps

These are source observations, not a claim about current production data coverage:

| Existing hook | What to build on or address |
| --- | --- |
| [`src/models/composite.py`](../../src/models/composite.py), [`src/models/v5_probabilities.py`](../../src/models/v5_probabilities.py) | Baseline/v5 isolation already exists. Current v5 uncertainty is a bounded feature-based heuristic, not an estimated predictive interval. Preserve its name and outputs; give new uncertainty a separately versioned meaning. |
| [`src/calibration.py`](../../src/calibration.py) | Bucket corrections use a 50-row floor and fall back to a pooled cross-market curve. A multiplier can create discontinuities and transfer calibration from a different event type. Fit a candidate-specific calibrator on earlier, disjoint data and report market sample counts. |
| [`src/clv.py`](../../src/clv.py) | `record_clv` stores `(1/taken - 1/close) * 100`: taking 3.0 before a 2.5 close gives **−6.67 pp** despite receiving the better price. The helper for de-vigging is not called by this recorder. Preserve raw historical values and label their convention; calculate corrected measures from the recorded odds in a new version. |
| [`backtester/model_registry.py`](../../backtester/model_registry.py) | Promotion reads pooled `prediction_log` and `clv_log`; the current read is not filtered to one candidate or evaluation cohort. A candidate should earn promotion with its own frozen, comparable evidence. A fixed row count alone does not establish statistical significance. |
| [`backtester/pit_models.py`](../../backtester/pit_models.py) | PIT form explicitly redistributes live weights because live DG/simulation inputs are unavailable. Record feature parity and missing inputs instead of assuming the replay validates every live path. |
| [`backtester/research_lab/canonical.py`](../../backtester/research_lab/canonical.py), [`src/run_provenance.py`](../../src/run_provenance.py) | Reuse evaluation contracts, frozen strategy identities and provenance. Extend them with forecast cutoff, data fingerprint, calibrator version, market rules and cohort identity. |

Implementation follow-through: `src/clv.py` now adds `quote_price_clv_pct`, `legacy_signed_clv_pct`, explicit metric provenance and recorded-row quote coverage. It derives the corrected series from original prices without rewriting `clv_log`; legacy fields and promotion gates retain their existing convention. No no-vig fair-close EV is inferred from a lone closing quote. `src/autoresearch_operator.py` now reads era evidence before closing its connection and attributes it only within bounded activation intervals with matching lab lane, configuration hash and model variant. It reports excluded provenance explicitly, chooses one authoritative/latest outcome per pick, and excludes unknown stake/profit from ROI. Creation-time attribution cannot reconstruct edited picks or rollback reactivations lacking a new activation record; those limitations remain visible.

## Experiments in order

1. **Establish honest baselines.** Freeze the existing model/configuration and its pre-event outputs. Evaluate baseline, v5, challenger and available market/DataGolf predictions on a common forecast cohort, while retaining separate coverage. Do not fill absent historical predictions with today’s ratings. Data Golf exposes round history, current predictions, historical prediction archives, and historical opening/closing odds, but archives and live endpoints differ in coverage; verify each source before admitting it to a backtest. [Data Golf API](https://datagolf.com/api-access)

2. **Learn ability before betting rules.** Estimate next-round adjusted SG with regularized component weights and calendar-time decay, with player-level shrinkage for sparse histories. Use absolute SG units where available; avoid making ability change merely because the current field changes. Test course effects and momentum as incremental additions. The specific decay, shrinkage and feature choices here are proposed experiments, not established optimal settings.

3. **Learn variance as well as mean.** Start with a pooled residual variance, blend toward player-specific residual variance as evidence grows, and test tour/course/skill interactions. Reuse stored round data first. Data Golf’s 2026 update explicitly models SD using skill, distance and tour, blends with observed player variance, and adjusts for course variance. It also describes shot-level adjustments; those cannot be reproduced from round totals alone. Keep shot-level research gated on acquiring and validating the required data. [2026 model update](https://datagolf.com/model-talk/2026-offseason-tweaks)

4. **Generate rule-aware probabilities.** A common simulation should produce finish, cut and matchup outcomes, with shared course/wave effects tested against an independent-round baseline. Model ties explicitly. A push-returned H2H’s conditional win probability differs from its unconditional win probability, while dead-heat payouts need their own return calculation. Data Golf’s matchup explainer makes its displayed tie-excluded convention explicit. [Matchup conventions](https://datagolf.com/static/dg_matchups_explainer2.pdf), [return conventions](https://datagolf.com/static/dg_results_note.pdf)

5. **Calibrate separately from fitting.** Use chronological out-of-fold predictions for fitting a small sigmoid calibrator, by market when supported. Retain an uncalibrated comparator. Consider isotonic only with substantial independent evidence: scikit-learn warns that it overfits small samples and describes approximately 1,000 observations as a useful scale, not a universal guarantee. Brier/log loss measure more than calibration alone, so show a reliability plot too. [Calibration documentation](https://scikit-learn.org/stable/modules/calibration.html)

6. **Test economic decisions last.** Freeze market thresholds, quote-age limits and stake policy before evaluation. Report flat-stake and chosen-stake results, executable book/price coverage, costs where applicable, and exposure by golfer/event. Testing many weights and thresholds can select noise; record all trials and reserve future events that search cannot repeatedly inspect. The backtest-overfitting literature motivates this constraint, but does not validate a golf-specific threshold. [Bailey et al.](https://escholarship.org/uc/item/4w1110bb)

## Weekly learning contract

After verified results arrive: append outcomes → freeze a weekly evidence artifact → update diagnostics → train candidates using prior events → evaluate candidates → retain the champion or record a justified promotion. Preserve original predictions, source history, parameters, and evaluation results; corrections append a reason and version.

Split by complete event in chronological order, with all rows from an event in the same partition. Fit preprocessing, feature selection and calibration inside the earlier partition. Account for source publication delay, not just event date. This is a golf-specific implementation recommendation based on scikit-learn’s warning that ordinary random cross-validation is unsuitable for temporally dependent samples. Its stock `TimeSeriesSplit` expects equally spaced observations; event boundaries and durations should therefore be handled explicitly here. [Temporal validation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)

Promotion should require paired future-event improvement in forecast quality, acceptable risk and sufficient evidence for the enabled markets. Persist the candidate/configuration hash, data cutoff, event IDs, evaluation contract, full search count, benchmark, metric deltas and uncertainty. Use event-cluster resampling for intervals as a proposed way to respect shared tournament outcomes. If evidence is thin or intervals cross zero, display **inconclusive** and keep learning. A scheduled run that found no improvement is still a successful research run.

## Analytics that make improvement visible

Use one filter contract everywhere: season/date, tour, event, market, model version, forecast timing, evidence class, and book. Distinguish real recorded decisions, simulated decisions, and uncorroborated recovered rows. Do not combine them into one ROI.

| View | Required measures |
| --- | --- |
| Rankings | Current rank and change from a frozen prior snapshot; projected SG; confidence/data coverage; form/course/skill contributions. No synthetic movement when a prior snapshot is absent. |
| Forecast quality | Paired Brier and log loss; same-cohort market/model deltas; reliability chart with counts; SG prediction error; per-market coverage and uncertainty. |
| Economic history | Settled profit, total staked, ROI, chronological drawdown, result statuses; flat-stake comparator; missing-stake exclusion counts. |
| Closing prices | Positive-is-better quoted price CLV, close coverage, reference book/source and cutoff; by-week/by-market series. Missing closes stay missing. |
| Learning ledger | Weekly changes, candidates tested, accepted/rejected/inconclusive outcome, benchmark deltas, unchanged champion, next scheduled evaluation. |

Use an explicit, versioned definition:

```text
quoted_price_clv_pct = 100 × (decimal_taken / decimal_close − 1)
fair_close_ev_pct    = 100 × (decimal_taken × fair_close_probability − 1)
```

These are arithmetic definitions proposed for the new analytics. For 3.0 taken and 2.5 close, quoted price CLV is **+20%**. It compares offered payouts and is not a margin-free estimate of profitability. Calculate fair-close EV only when there is a defensible no-vig probability and matching settlement rules. Normalize opposing probabilities only for a complete mutually exclusive market; top-10/top-20 field outcomes overlap and must not be normalized to sum to one. Neither a favorable price comparison nor a profitable historical sample proves future returns.

Market controls should separately express **show**, **research**, and **decision eligible**, with explicit unavailable/stale/unsupported states. Enable each market only when forecast, odds timing and settlement support exist. Keep the preserved model reachable by name, and make model comparisons inspectable without rewriting history.

## Delivery boundaries

This research did not run a candidate backtest, verify vendor entitlements, measure current database coverage, or establish live predictive improvement. First ship trustworthy rankings, cohort-aware analytics and the weekly evidence ledger. Then earn a better model through prospective comparisons. A smooth interface can reveal evidence immediately; sustained +ROI/+CLV remains an empirical outcome to measure.
