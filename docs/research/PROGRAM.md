# Research Program

## Purpose

This document defines how the manual backtesting research engine should behave.

The system is a proposal engine, not an autonomous production optimizer.
It exists to generate bounded, reviewable research proposals for the golf model.
OpenAI is the default theory generator for research cycles, while local numeric code remains the source of truth for evaluation and ranking.

## Hard rules

- Do not edit production code automatically.
- Do not promote any proposal into `active_strategy`.
- Do not run indefinitely.
- Do not use daemon loops or background polling in version 1.
- Do not treat synthetic historical odds as sportsbook-true profit proof.
- Do not optimize per-event or per-course strategies in version 1.

## Allowed proposal types

- `StrategyConfig` weight changes
- EV threshold changes
- market filter changes
- temperature changes
- bankroll parameter changes
- weather toggle changes
- OpenAI-generated theory variants that map back to valid `StrategyConfig` overrides

## Evaluation rules

- Use walk-forward only.
- Use chronological event order only.
- Show both weighted and unweighted summaries.
- Weight majors and signature events more heavily in summary views.
- Rank proposals by weighted ROI.
- Block or warn on major CLV, calibration, drawdown, or sample-size regressions.
- Use OpenAI first for theory generation, but fall back to local neighbor search if AI is unavailable.

## Output requirements

Every proposal must produce:

- a markdown dossier
- a JSON manifest
- explicit synthetic-odds warning text
- baseline comparison
- guardrail verdict
- theory title, rationale, and source metadata

## Runtime model

Version 1 is manual-run only.

One command should run one bounded research cycle and stop.

Future scheduling or daemonization must wrap the same reusable cycle instead of changing its core logic.

## Scope

Each cycle proposes and evaluates research configurations. It may append datasets,
trials, immutable artifacts and reviewable dossiers. It must preserve the incumbent
model, source predictions, all prior experiments and their provenance. A scheduled
wrapper may invoke a bounded cycle; the cycle itself must finish and release its lock.

## Immutable Evaluator Rule

Pin evaluator source hashes, data fingerprints, event identities, temporal windows
and the selection rule before a study. A changed evaluator or repaired dataset
starts a new protocol version and requires a fresh common-cohort baseline. Never
silently compare incompatible versions or use event outcomes in pre-event features.
An already inspected test period must be labeled exposed rather than fresh holdout.

## Objective

Estimate predictive quality on chronological, event-level cohorts and improve
calibration before making financial claims. The weighted ROI ranking above applies
only to market evaluations with real historical bookmaker prices and identified
settlement rules. Synthetic prices remain research inputs; unknown ROI and CLV stay
null. Report unweighted results, event-cluster uncertainty, missingness and every
trial alongside the primary objective so many correlated pairs cannot masquerade
as independent evidence.

## Loop Protocol

1. Read this program, acquire one study lock and verify the pinned source protocol.
2. Ingest append-only data; retain original payload hashes and exclude conflicting
   or unverified source records from performance and promotion.
3. Fit only on completed historical events available before each prediction date.
4. Select and calibrate on declared validation windows within a fixed trial budget.
5. Compare the candidate, frozen incumbent and simple statistical benchmark on the
   same cohort. Append the report even when the candidate loses or data are missing.
6. Publish a research report and an explicit promotion verdict, then stop. A forward
   refit must have its own artifact and must not replace retrospective predictions.

## Promotion Rule

The cycle produces a dossier. It never changes `active_strategy` automatically.
Preserve the current model and allow rollback to its exact configuration. A
production replacement requires verified event/market coverage, meaningful sample
size, calibrated probabilities and financial evidence from qualified real quotes.
Record the exact configuration and activation time of every explicitly approved
replacement so subsequent results can be attributed to the correct model era.
