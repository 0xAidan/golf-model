# Multi-season learning challenger

**Integrity repair:** all earlier v1/v2 learning artifacts are invalidated and
their metrics withdrawn. Their original reports, models and predictions remain
intact. The repaired experiment uses `tour:datagolf:dg_id` for history and targets,
preserves raw aliases, and withholds ambiguous current-field aliases lacking IDs.
Independent review exactly reproduced its 4,002 predictions and 66 current ranks.
See [the repair record](2026-10-16-learning-identity-integrity-repair.md) for the
reviewed results, exact hashes and separate future-run projection guard change.

The original model and its pinned source/configuration manifest remain unchanged.
The v1 experiment and its invalidation history remain available. This protocol
adds verified 2019–2026 round history; forensic SQL, recovered forecasts, Optuna
policy results and historical model-price profits are not training observations.

`config/learning-protocols/recovered-rounds-v2-identity-repair.json` retains the
original protocol's seven candidate
specifications before this run: SG50 with an eight-round shrinkage prior, three
recency/component ridge strengths, one regularized hinge-basis model and two
bounded gradient-boosted stump models. Stumps use deterministic training-only
quantiles and event-weighted residual fitting; their trees are serialized as JSON.
No pickle, external model service or live-model replacement is involved.

## Data and chronology

The verified hidden-local and Finder-downloaded logical vaults contain 137,102
and 128,664 rounds. They are merged with the preserved production research export
for current-season coverage. Compressed vault hashes and completed table counts
are checked while streaming. Tour/event/year/DataGolf-player/round identities are
deduplicated; every source observation retains its snapshot, table ordinal and
row hash. Conflicting scores, completion dates, courses or finishes are excluded.
Conflicting official start dates exclude their calendar identity. Disagreeing
course calendars omit the course feature.

Only PGA events aligned to official calendar starts and completed strictly before
the target start contribute features. Team events and sealed event keys are
excluded from both feature history and targets. A course feature requires one
known official calendar venue; an outcome-derived modal course is never used.
2019 supplies history warmup. Training targets start in 2020; 2025 selects the
candidate; 2026 is an **already exposed retrospective audit**. Events overlapping
a split boundary are purged. Withdrawals, ambiguous finishes and insufficient
history/cohort coverage remain explicit exclusions.

The 28 features include the original short-window/component/course signals,
longer history, exponentially weighted skill, volatility and layoff interaction.
Every feature is recomputed from prior completed events. The target is mean SG
over actually played rounds, including the shorter observation horizon for cuts.
No unplayed rounds are invented. Historical archives were acquired after events;
calendar separation does not establish original publication or revision history.

## Selection and honest evaluation

Every candidate calibrates its symmetric decisive-finish-order probabilities on
four expanding chronological out-of-fold blocks from training years only. The
2025 validation log loss selects a fixed candidate, with SG RMSE as a tie breaker.
The chosen model is then fitted through 2025 and calibrated on pre-2026 expanding
forecasts. Its 2026 predictions use that exact evaluation model.

All comparators share the same covered player/event cohort. Reports include SG50,
the pinned PIT comparator with its original calibration, and that comparator with
pre-test-only recalibration. This exposes improvements caused merely by changing
the probability scale. Event-weighted log loss, Brier, ordering accuracy, rank
correlation, SG RMSE, reliability and quarterly diagnostics are retained. Paired
event bootstrap intervals resample events, not correlated player pairs.

The seven bounded trials are this protocol's search count. They do not erase
prior v1 searches, thousands of preserved historical Optuna trials, or earlier
inspection of 2026 outcomes. Statistical uncertainty cannot turn this exposed
audit into fresh prospective evidence. No retrospective result automatically
promotes a model. Conditional finish-order probabilities do not price ties,
withdrawals, placements, 3-ball or book-specific settlements. ROI and CLV remain
null in this round-skill experiment.

## Forward refit and weekly artifacts

The selected specification is separately refitted on all completed, unsealed
development events through the refresh date. That **forward-only shadow model**
has a different hash and training cutoff. It is never substituted into the 2026
audit. `current_rankings` uses this forward model and its own SG-per-round unit.

The existing report contract remains available, with these additions:

- `schema_version: 2`; `candidate.hash` names the pre-2026 evaluated model.
- `forward_candidate.hash` and `trained_through` name the forward refit.
- `current_rankings_model_hash` binds field scores to the forward model.
- `diagnostics` retains calibration boundaries and quarterly development/audit
  metrics; `selection.trial_count` names this protocol's seven candidates.
- `model.json` stores the evaluated model; `forward-model.json` stores the current
  shadow refit; `protocol.json` preserves the resolved protocol.
- `registry.jsonl` appends unique run/source/protocol/evaluation/forward identities.
  Prior runs, baseline snapshots and prediction rows are never replaced.
- `implementation/` and `reproducibility.json` retain the exact trainer/inference
  sources, Python/NumPy versions, hashes and projection/protocol inputs, including
  the sealed-event policy, event-format classifier and CLI publication closure.
- `training-source.jsonl.gz` retains the exact merged round/calendar corpus used
  by this run. It is compressed and readback-verified before fitting, then bound
  by SHA-256 in `source-manifest.json` and `reproducibility.json`. Later database
  corrections cannot change the retained weekly input.

Display the forward training cutoff beside current field scores, and the evaluated
cutoff beside historical metrics. Match the recorded event identity before showing
any projected field. Neither hash is the incumbent dashboard model hash.

```sh
python3 scripts/train_learning_challenger.py \
  --source data/research/verified-learning-corpus-v2-identity-repair.jsonl.gz \
  --protocol recovered-v2 --as-of 2026-10-16 \
  --snapshot data/research/live_refresh_snapshot.json

# Weekly after ordinary ingestion: merge the retained verified seed with current
# readonly SQLite rounds, then append a new evaluation/forward-refit artifact.
python3 scripts/weekly_learning_refresh.py
```

The corrected compressed seed is about 19 MB; the large preservation vaults need not be
repeatedly expanded. Installation and live scheduler verification remain separate
release steps. Training does not ingest data, place bets, change the incumbent,
enable markets or send notifications.

The weekly entry point refuses to run with a missing verified seed (exit 2,
`missing_verified_history_seed`); manual legacy training remains available through
the original CLI mode. The public report path can be overridden, including the
built site's `frontend/dist/reports/learning-latest.json`. Every refreshed report
also records whether any new completed training events arrived. A rerun with no
new completed events explicitly says so and does not imply fresh learning.

## Withdrawn first bounded experiment result

The following numbers are retained only as the record of an invalidated run.
They must not be used as evidence of predictive improvement. Provider-identity
repair and independent review are required before replacement metrics publish.

The fixed seven-candidate search selected the spline ridge at regularization 0.1.
Training used 225 events in 2020–2024; validation used 47 events in 2025. The
exposed 2026 audit used 37 events and 4,003 player/event observations on the same
cohort for every comparator. Conditional finish-order log loss was 0.642501 versus
0.656419 for SG50; Brier was 0.225965 versus 0.232434; ordering accuracy was
62.557% versus 60.577%; SG RMSE was 1.643238 versus 1.727274. The paired-event
bootstrap interval for the log-loss difference versus SG50 was
[-0.018957, -0.008725].

The invalidated frozen PIT replay scored 0.717649 log loss; its recalibrated
comparison was 0.668075. Those numbers cannot substantiate improvement while the
cohort contains contaminated player identities. The repaired frozen run requires
independent review. The incumbent remains unchanged and promotion remains disabled.

## Reviewed replacement and private weekly storage

The frozen replacement `20261016-3b828fe0d23747a7` passed independent replay
of all 4,002 audit predictions, 113 Sony baseline scores and all 66 current
PGA field projections. Its report SHA-256 is
`ce11bdcdbbb91edfffe475b675810b71c9fc740246aab840ce6545b902b8820e`.
The unchanged seven-candidate protocol selects spline ridge 0.1 on 2025.
The 37-event exposed audit log loss is 0.642518 versus SG50 0.656387 and
recalibrated PIT 0.667975. This supports research comparison only. No untouched
holdout, prospective profitability, ROI, CLV or promotion is established.

Subsequent producer guards reject contradictory/unverified current-field identity.
The reviewed artifact preserves its exact original CLI; its verified PGA field
replays identically under the corrected guard. Future runs archive the shipping
CLI and weekly entry point under their own implementation hashes.

The installed weekly runner must store raw artifacts under
`data/research/learning-runs`, outside the legacy output-content API's readable
`output/` tree. Only sanitized reports go into the built site's reports directory.
The service has a 2 GiB memory cap; the local experiment sampled 1.21 GiB RSS,
which was not a measured peak. Installation and the first protected server run
must be verified separately before claiming recurring operation.
