# Lab experiment baseline (`/lab` / `v5`)

**Purpose:** frozen measurement contract for comparing lab (`lab_sandbox` → `v5`) vs operator dashboard snapshot variant (`COCKPIT_SNAPSHOT_MODEL_VARIANT`, typically `baseline`).

**Scope:** Research-backed changes ship behind `model_variant == "v5"` and lab snapshot lanes (`lab_live_tournament`, `lab_upcoming_tournament`). Operator `/` boards remain unchanged unless explicitly promoted.

## Metrics (minimum set)

| Metric | Where computed | Notes |
|--------|----------------|-------|
| Calibration | AB / grading pipelines | Brier, reliability slope where applicable |
| Value quality | `backtester/weighted_walkforward.py`, CLV tracking | ROI, weighted ROI, hit rate |
| Stability | Segment splits | Tail behaviour by uncertainty decile & field strength |
| Data health | `src/lab_data_integrity.py`, `backtester/autoresearch_data_health.py` | Rows dropped / warnings |

## Benchmark windows

Pin **two independent calendar windows** before comparing experiments (example placeholders — replace with your live evaluation spans):

1. **Primary:** last full PGA Tour season window used for autoresearch guardrails.
2. **Holdout:** prior season or disjoint months for confirmation.

Record the exact date ranges and git SHA in each experiment note under `docs/research/experiments/`.

## Commands (reference)

```bash
# Autoresearch data health preflight
python -c "from backtester.autoresearch_data_health import validate_autoresearch_data_health; print(validate_autoresearch_data_health())"

# AB compare (existing tooling)
python -m pytest tests/test_ab_compare.py -q
```

## Artifact locations

- Research extractions: [datagolf_extractions.jsonl](datagolf_extractions.jsonl)
- Promotion criteria: [LAB_PROMOTION_GATES.md](LAB_PROMOTION_GATES.md)
