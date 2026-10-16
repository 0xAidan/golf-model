# Golf Model

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The owner uses the site to research golf betting opportunities. The confirmed workflow is personal card building plus shared picks. Both should feel fast and dependable across the full stack.

## Product Purpose

Make rankings the center of a connected research workflow: understand the field, compare market prices, save a card, inspect performance, and refine models using chronological evidence.

## Operating Context

The primary markets are head-to-head matchups over 72 holes and 18 holes, group markets, and other niches with historical evidence. The application runs on the owner's VPS at golf.shermandavison.com, using FastAPI, SQLite, React and Vite.

## Capabilities and Constraints

- The user requires the current model to remain accessible and all historical data/results to be preserved.
- As of October 15, 2026, the user explicitly authorizes developing and training better challengers, extensive backtests, data acquisition, weekly learning, configurable markets, and a full product redesign. Earlier model-freeze instructions are superseded by this authorization.
- Existing model probabilities, prices and EV must retain their source, event, lane and timestamp. Unverified, stale, absent and research-only markets remain explicit.
- Stored predictions are not proof of placed bets. Unknown stakes and missing history must not be presented as a verified betting return.
- Training creates versioned challenger artifacts. Historical predictions and outcomes remain immutable. Retrospective improvements are distinguished from prospective evidence, and a failed challenger remains visible rather than being promoted to manufacture progress.

## Evidence on Hand

Production source was cloned from commit cb86850 on 2026-10-13. Read-only inspection found active records beginning in September, older preserved quarantine databases, tournament exports, snapshots, and audit artifacts. Recovery completeness and profitability remain unverified. The current site contains redundant navigation, ambiguous event context and market groupings that do not match the owner's workflow.

## Product Principles

1. Start with the rankings, then connect the player to the market and the price.
2. Preserve every source record and explain the limits of its evidence.
3. Keep a single event context through market selection and card building.
4. Put research and operations behind the daily workflow.
5. Measure learning by version, event and market; keep the baseline available and show missing evidence.
