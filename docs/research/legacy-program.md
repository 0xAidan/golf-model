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
