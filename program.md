# Autoresearch Program

This file is the control-plane instruction set for the industrial autoresearch loop.

## Scope

- The agent may edit only:
  - `autoresearch/strategy_config.json`
- The agent must not edit evaluator or PIT/replay logic while running search iterations.

## Immutable Evaluator Rule

- Evaluation logic is fixed by `docs/autoresearch/evaluation_contract.md`.
- Any contract mismatch is a hard failure.

## Objective

- Maximize blended score from the immutable evaluator.
- Candidate is accepted only when:
  - blended score improves vs baseline,
  - guardrails pass.

## Guardrails

- Minimum sample size.
- No material CLV regression.
- No material calibration regression.
- No material drawdown regression.

## Loop Protocol

1. Read pilot contract and evaluator version.
2. Propose one coherent strategy mutation.
3. Commit candidate strategy artifact.
4. Run evaluator and parse machine-readable lines.
5. Keep candidate only if score improves and guardrails pass.
6. Otherwise discard candidate commit.
7. Append immutable run metadata to run ledger.
8. Repeat until stopped.

## Failure Handling

- Timeout: mark failed iteration.
- Parse failure: mark failed iteration.
- Contract mismatch: hard stop.
- Missing data: hard stop.

## Promotion Rule

- A pilot winner cannot be promoted without a holdout pass artifact.
- Live promotion still requires charter gates.
