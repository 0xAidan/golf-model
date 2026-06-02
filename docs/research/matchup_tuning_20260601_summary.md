# Matchup lab tuning summary (2026-06-01)

This summary captures the committed outcome of the Phase 2/3 matchup-lab sweep run.
The full machine artifact was generated at runtime under `output/research/matchup_tuning_20260601.json` (gitignored by repo policy).

## Run command

```bash
./.venv/bin/python scripts/run_matchup_lab_research.py \
  --db-path /opt/golf-model/data/golf.db \
  --out-dir output/research \
  --run-optuna-trials 20
```

## Windows

- Primary window: `2024, 2025`
- Holdout window: `2026`
- Stake mode: `flat 1u`
- Candidate gates: `n >= 200` for evaluation, `n >= 250` before wire-up

## Baseline E0

- Primary: `n=1378`, `hit=48.33%`, `ROI=-4.72%`, `Brier=0.3249`
- Holdout: `n=815`, `hit=45.64%`, `ROI=-9.32%`, `Brier=0.3308`

## Best tested rows (primary ranking snapshot)

1. `H9_exposure_cap_2`: primary `ROI=+0.65%`, holdout `ROI=-3.98%`, brier `0.3672`
2. `H9_exposure_cap_3`: primary `ROI=-1.47%`, holdout `ROI=-8.14%`, brier `0.3659`
3. `E8` / `H4_tieaware_on`: primary `ROI=-2.60%`, holdout `ROI=-7.56%`, brier `0.2527`
4. `H5_sigmoid_a-0.03`: primary `ROI=-3.35%`, holdout `ROI=-7.74%`, brier `0.2869`

## Selected holdout-confirmed winner (strict gate rule)

- Winner: `H5_sigmoid_a-0.03`
- Primary: `n=1256`, `hit=48.73%`, `ROI=-3.35%`, `Brier=0.2869`
- Holdout: `n=751`, `hit=46.21%`, `ROI=-7.74%`, `Brier=0.2897`
- Reason selected over higher-ROI rows: better Brier than baseline while improving ROI/hit direction on both windows.

## MO Optuna pass (matchup objective vector)

- Trials run: `20`
- Objective directions: maximize `(ROI, hit rate)`, minimize `(Brier, drawdown)`
- Pareto trials discovered: `2` (stored in generated JSON and appended to `output/research/ledger.jsonl`)

## Notes

- Blend sweeps (`E5a/E5b`, `H2*`) are marked non-identifiable in replay-only mode because historical matchup replay rows do not carry DG matchup probabilities.
- No live baseline/operator route changes were applied. Results are research-only and remain in lab workflow scope.
