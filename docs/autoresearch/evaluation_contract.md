# Autoresearch Evaluation Contract

Version: `1`

## Editable Surface

- Allowed strategy artifact path: `autoresearch/strategy_config.json`
- All other files are non-editable during loop execution.

## Pilot Contract Source

- Contract file: `docs/autoresearch/pilot_contract.json`
- Evaluator must hard-fail if contract version mismatch occurs.

## Primary Objective

Blended score is computed using existing production helper:

- `compute_blended_score(summary_metrics, guardrail_results)`

Summary metrics and guardrails are produced by fixed evaluation path.

## Guardrail Semantics

Guardrails pass only when no reasons are produced by fixed guardrail evaluator.

Candidate is blocked if guardrails fail, regardless of metric delta.

## Output Contract (stdout)

Evaluator must emit all lines:

- `autoresearch_metric: <float>`
- `autoresearch_guardrails: pass|fail`
- `autoresearch_sample: <int>`
- `autoresearch_checkpoint_summary: <json>`

## Keep/Discard Policy

Candidate is kept only if:

- metric strictly improves vs baseline, and
- `autoresearch_guardrails: pass`

Otherwise candidate is discarded.

## Required Run Metadata

Each iteration must persist:

- run_id
- timestamp
- git_commit
- strategy_hash
- pilot_contract_version
- evaluator_version
- checkpoint_set_id
- metric
- guardrail verdict
- decision
- seed

## Failure Modes

- `contract_mismatch`
- `schema_validation_error`
- `missing_data`
- `timeout`
- `parse_failure`
- `runtime_error`

Any of these must produce a non-zero evaluator exit code.

## Promotion Gate Dependency

No registry promotion is allowed without holdout artifact:

- `output/research/holdout_verdict_<timestamp>.json`
- must contain `holdout_verdict: pass`
