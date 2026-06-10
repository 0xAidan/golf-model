# Experiment: Trial 327 revalidation (H-1)

**Status:** harness committed; production numbers PENDING (requires the production DB).
**Created:** 2026-06-10 · engine-scale Wave 3.
**Owner gate:** robust constrained winner — primary n ≥ 300, holdout n ≥ 200, holdout ROI ≥ 8%.

## Why this exists

The promoted lab champion `config/lab_matchup_champion_trial327.json` claims
**primary ROI +13.8% / holdout +9.05%** (`matchup_lab_max_roi_enterprise_v1` Optuna study).
That study DB is gitignored and there is **no committed per-trial dossier**, while the
committed frozen evidence is negative:

- Frozen E0 baseline (`docs/research/matchup_tuning_20260601_summary.md`): primary ROI
  **−4.72%**, holdout **−9.32%**; every matrix row was holdout-negative.
- 2019–2026 benchmark (`output/audits/matchup_baseline_20260601.json`): overall ROI **−6.12%**.
- Live +EV value-bet audit (`output/audits/value_bet_audit_20260531.md`): live matchups
  −5.73% over 61 bets; placement +EV −16.25% over 80 bets vs +29.97% in backtest
  (the canonical sim-to-live red flag).

Until this experiment fills in reproducible numbers, the product labels the lab track
**"challenger (validation pending)"** and promotion stays gated/off.

## How to run (production)

```bash
# On the VPS, against the real DB:
python3 scripts/revalidate_trial327.py --db-path /opt/golf-model/data/golf.db --write
```

This replays the trial-327 `StrategyConfig` (v5 variant, Platt −0.1/0.18, min gap 1.5,
EV floor 0.03, win-prob cap 0.81, form-dominated SG weights, 80/20 DG blend) on the pinned
windows and writes `docs/research/experiments/trial_327_revalidation_<date>.json` with the
robust-gate verdict. Exit code is non-zero unless the robust gate passes.

The authoritative max-ROI reproduction remains:
```bash
python3 scripts/run_matchup_lab_research.py --only-max-roi --run-max-roi-trials 0
```
(re-summarizes the persistent study; this dossier's harness is the lighter gate-checked
sanity replay using the shared frozen-baseline primitives.)

Caveat: `scripts/revalidate_trial327.py` maps the bundle to `StrategyConfig` fields that
walk-forward replay honors. The bundle's `matchup_filters` (tier_floor STRONG,
max_positive_odds +400) and `sg_weights` are applied by the full lab pipeline /
`run_matchup_lab_research.py`, not by the thin replay — so treat a borderline pass here as
"needs the full matrix run" rather than definitive.

## Results

| Window | n | hit % | ROI % | Brier |
|--------|---|-------|-------|-------|
| Primary (2024–2025) | _pending_ | _pending_ | _pending_ | _pending_ |
| Holdout (2026) | _pending_ | _pending_ | _pending_ | _pending_ |

**Robust gate:** _pending_ (fill from the committed JSON, record the git SHA the JSON
captured).

## Decision

- If the gate **passes** on production data: trial 327 is eligible to remain the lab slot
  bundle and is a promotion candidate (still requires the human-approved `/eval` promotion
  flow + documented AB/soak per `docs/research/LAB_PROMOTION_GATES.md`).
- If it **fails**: replace the lab slot with the best gate-passing alternative from the
  matrix, or fall the lab lane back to a documented baseline; do NOT promote.

## Live shadow corroboration (H-6)

Independently, set `LAB_CHALLENGER_SHADOW_ENABLED=1` to register the lab bundle as a
`BaseModel` challenger (`src/models/lab_challenger.py`). It shadow-prices the SAME matchups
the champion prices into `challenger_predictions`, so `GET /api/champion-challenger/summary`
accumulates live Brier/CLV for the challenger without it ever pricing a live bet.
