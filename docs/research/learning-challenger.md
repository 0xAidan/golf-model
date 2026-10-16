# Learning challenger: experiment and artifact contract

The original dashboard model remains available at `/research/legacy-model` and its
effective configuration, active weight set, source commit and source hashes are
preserved in `config/model-baselines/original-<hash>.json`. No training command
changes a live model registry, weight set, betting setting or historical row.
The comparator manifest is pinned to `original-453f49ec24f0e48a.json`; later live
changes do not redefine it. Its manifest hash and all preserved source-file hashes
must match the checkout before a comparison runs. Changed source raises
`comparator_source_changed`; the runner does not silently rebaseline the series.

## Candidate

The research candidate predicts expected strokes gained per round. Its 15 features
are shrinkage-adjusted SG averages over 8, 24 and 50 prior rounds, component skill,
recent trend, course residual, coverage and layoff. Ridge coefficients learn which
signals transfer to later events. The score keeps its own SG unit; it must never be
displayed as the existing 0–100 composite.

`src/models/learning_challenger.py` exports `player_features`,
`predict_expected_sg`, `pair_probability` and `rank_players`. `rank_players` needs a
fitted model, historical round rows, a named field, an `as_of` date and optionally a
course number. Players with fewer than eight eligible prior rounds receive no
invented ranking. The runtime leaves all existing model math unchanged.

Binary finish-order probabilities use a symmetric sigmoid calibrated on expanding
out-of-fold forecasts. They are conditional on a decisive comparison and are not yet
executable market probabilities: ties, withdrawals, 3-ball, dead heats, placements
and book-specific rules require additional pricing work.

## Temporal evaluation

Only source events whose official calendar start and completed-round dates are
known are eligible. Features for an event use rounds from events completed strictly
before its start. Same-day results and overlapping events are excluded. Duplicate
rounds do not increase sample size; conflicting duplicates are excluded. Team
events, withdrawals, ambiguous finishes and the pre-existing sealed holdout events
are excluded from training and evaluation targets.

The chronological 60/20/20 split keeps same-day events together and purges events
that cross a later split boundary. Five fixed regularization strengths are selected
by validation pair log loss, with validation SG RMSE as a tie breaker. Probability
calibration uses expanding forecasts whose predicted events were absent from their
fits. Final coefficients use training and validation events only; test events are
never used to fit or select the model.

All comparators use the same covered player/event cohort. The original scorer is
the unchanged `backtester.pit_models.compute_pit_composite`, applied to independently
rebuilt, strictly prior PIT tables. This is a **frozen PIT comparator**, not a replay
of the full contemporaneous live DG/simulation blend. The simple 50-round SG mean is
also a comparator, so gains from calibration alone are visible.

Test reports include equal-event-weighted log loss, Brier score, pair ordering
accuracy, rank correlation, SG RMSE and reliability bins. Pair counts are dependent
comparisons, not independent bets. Paired event-bootstrap intervals use 2,000
resamples and a fixed seed. SG targets average actual played rounds; no unplayed
weekend rounds are fabricated for missed-cut players. Archive acquisition after an
event does not establish contemporaneous vendor publication or revision history.

The initial report was invalidated after review found PGA and LIV event IDs could
collide in the loader. Original reports remain intact with `INVALIDATED.json`
sidecars and an append-only invalidation ledger. The repaired protocol restricts
targets and feature histories to PGA rounds, includes tour in round identities, and
requires completion dates to agree with the official PGA calendar within seven days.
Its already exposed test period is labeled a retrospective integrity repair and
must not be presented as fresh untouched evidence. Reading test results and
subsequently changing a model turns that window into development data. The
versioned protocol, implementation hashes, five-candidate trial log and retained
artifacts make that distinction auditable. No retrospective profit result promotes
a model automatically.

## Market evidence

DataGolf model prices in `historical_odds` are not historical executable sportsbook
quotes. They supply neither honest ROI nor CLV evidence. Recorded sportsbook lines
are counted separately, with strict pre-start calendar-date admission; same-day
lines are excluded absent verified tee-time timing. ROI and CLV remain `null` when
the required entry, close and settlement evidence is unavailable. Missing coverage
is shown explicitly and is never converted to a zero return or zero CLV.

## Commands and weekly operation

```sh
python3 scripts/train_learning_challenger.py \
  --source data/research/production-learning-20261015.jsonl.gz \
  --snapshot data/research/live_refresh_snapshot.json \
  --as-of 2026-10-16 \
  --public-report frontend/public/reports/learning-latest.json

# After the ordinary weekly DataGolf ingestion and PIT refresh:
python3 scripts/weekly_learning_refresh.py
```

The source may be a read-only SQLite file or an exported `.jsonl.gz` corpus. SQLite
is opened with `mode=ro`, `query_only=ON` and a read transaction. A process lock
prevents overlapping training. Artifacts are written to a new content-derived run
directory; identical inputs reuse it without overwriting the original. Only the
`latest.json` pointer and optional product report are replaced. Existing research,
source history and previous candidates remain intact. No data ingestion or outbound
notifications are performed by this runner.

The weekly runner is an available entry point; installation in an active scheduler
must be verified separately. A saved script does not prove that a timer is running.

## Artifact and UI contract

Each `output/learning/<run-id>/` contains:

- `model.json`: fitted coefficients, scaling, probability slope, training cutoff,
  candidate hash, protocol and implementation hashes.
- `report.json`: sanitized public report; no credentials or raw corpus.
- `predictions.jsonl`: test player/event forecasts with outcome and history dates.
- `baseline.json`: the preserved original configuration and source provenance.
- `source-manifest.json`: source digest, acquisition metadata and table counts.

The schema-version 1 public report has `candidate`, `baseline`, `data`, `splits`,
`selection`, `comparisons`, `market_evidence`, `promotion`, `learning`,
`current_event`, `current_rankings` and `limitations`. `comparisons.test` contains
`candidate`, `baseline` and `naive`; `comparisons.event_series` contains one row per
test event. `comparisons.delta` includes paired event-bootstrap loss intervals
against both comparators. The candidate hash names the exact evaluated artifact;
it is not the dashboard model hash.

`current_event` binds a projection to event ID, name and feature `as_of` date. The
product must match that identity to its selected event before showing the learned
field. `candidate.trained_through` is the coefficient training cutoff, separately
from the newer feature `as_of`. `state: insufficient_data` remains an explicit
non-success with absent metrics. `promotion.eligible` stays false until separate
prospective pricing and execution evidence has been reviewed.
