# Golf Model

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The owner uses the site to research golf betting opportunities. The confirmed workflow is personal card building plus shared picks. Both should feel fast and dependable across the full stack.

## Product Purpose

Make the existing predictions useful in one fast workflow: review matchup markets, compare the available price with the frozen model output, save a card, share selected quotes, and inspect the evidence after settlement.

## Operating Context

The primary markets are head-to-head matchups over 72 holes and 18 holes, group markets, and other niches with historical evidence. The application runs on the owner's VPS at golf.shermandavison.com, using FastAPI, SQLite, React and Vite.

## Capabilities and Constraints

- The user explicitly prohibits changes to the models and loss or alteration of historical data/results.
- Presentation, navigation, delivery, reporting, operational reliability and additive evaluation are authorized.
- Existing model probabilities, prices and EV must retain their source, event, lane and timestamp. Unverified, stale, absent and research-only markets remain explicit.
- Stored predictions are not proof of placed bets. Unknown stakes and missing history must not be presented as a verified betting return.
- Learning in this scope evaluates existing predictions; it never promotes models, retunes weights, rewrites outcomes or runs the existing mutating learning pipeline.

## Evidence on Hand

Production source was cloned from commit cb86850 on 2026-10-13. Read-only inspection found active records beginning in September, older preserved quarantine databases, tournament exports, snapshots, and audit artifacts. Recovery completeness and profitability remain unverified. The current site contains redundant navigation, ambiguous event context and market groupings that do not match the owner's workflow.

## Product Principles

1. Start with the matchup and the price.
2. Preserve every source record and explain the limits of its evidence.
3. Keep a single event context through market selection and card building.
4. Put research and operations behind the daily workflow.
5. Improve decisions without silently changing predictions.
