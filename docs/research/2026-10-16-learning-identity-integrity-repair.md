# Learning challenger provider-identity integrity repair

The independent review reproduced two distinct DataGolf players sharing
`zach_johnson`: ID 6986 (451 archived rounds) and ID 17619 (four archived rounds,
including club professional Zach J. Johnson). Name-based history grouping let the
sparse second player borrow the first player's eligibility and features. Other
ambiguous aliases were present. No equivalence between changing provider IDs is
inferred from a shared name.

## Withdrawal and retained evidence

Both v2 runs (`20261016-4d91ba55718aa247`,
`20261016-f1a128da6dda47de`) and the corrected v1 run
(`20261016-5203626273d2d358`) now have append-only `INVALIDATED.json` markers.
The v1 production export also contains multiple DataGolf IDs under shared aliases.
The two earlier cross-tour-invalid runs keep their existing markers. Every
original model, report and prediction file remains unchanged. The public report
is withheld; the public run-history builder excludes all invalidated runs.

`output/learning/integrity-20261016-provider-identities/` preserves the pre-withdrawal
public/pointer bytes. `output/learning/invalidations.jsonl` records the withdrawal.
The incumbent model and all collected source history remain unchanged.

## Frozen repair protocol

`config/learning-protocols/recovered-rounds-v2-identity-repair.json` preserves the
original seven candidate specifications, chronology, selection objective,
calibration method and paired-event bootstrap. Its parent protocol hash is
`239b49279de7a5a2074202150a4c522f33b8659fdf9b58e399b1ac1d58481194`.
No family or hyperparameter is added after inspecting the exposed audit.
The repaired protocol explicitly labels 2026 an **exposed retrospective integrity
repair**, never a new holdout.

The batch repairs these four boundaries before the full experiment runs:

1. All round deduplication, historical features, target eligibility, PIT comparator
   inputs and predictions use `tour:datagolf:dg_id`. Missing IDs are excluded.
   Raw player keys/names and exact original source-row references are retained.
   Feature construction rejects a mixed-provider history. Field projection uses
   an explicit valid DataGolf ID or one unambiguous observed alias; missing-ID
   namesakes, ID/name conflicts and duplicate field aliases are withheld.
2. Every weekly effective round/calendar corpus is compressed, hashed and
   readback-verified **before fitting**, then copied into the immutable run as
   `training-source.jsonl.gz`. New SQLite rows retain the transaction hash,
   table, ordinal and exact raw-row hash. Replays use those retained bytes even
   after the live database is corrected. No forensic salvage is admitted.
3. The archived fingerprint includes the sealed-holdout reader and policy JSON,
   event-format classifier, training/weekly scripts, public run-history builder
   and exact repaired protocol, alongside training/inference implementations.
4. Current field identity includes tour and year. One official calendar event
   must match the recorded snapshot's capture date within minus seven/plus
   forty-two days, and any explicit event year must agree. Missing/ambiguous
   years, future snapshots and snapshots more than seven days old are withheld;
   selecting the maximum calendar year is prohibited.

## Rebuilt verified source

The source was rebuilt directly from the two verified logical vaults and the
retained production export, with logical gzip hashes, row hashes and table counts
checked. The old alias-rewritten cache is preserved and is not the repair input.

- Seed: `data/research/verified-learning-corpus-v2-identity-repair.jsonl.gz`
- Size: 19,270,866 bytes.
- Gzip SHA-256:
  `77fa175573bd03b214984de193e20466ecb4c0f045e7bd3e9a3b6ab722afb418`.
- Canonical effective corpus SHA-256:
  `afb4d9f0039b8c0d21517ce4faafc1126dfd9464bae8538202396b8e67b3f26d`.
- 147,124 unique rounds and 370 calendar events; 154,113 repeated round
  observations retain their original references. One conflicting calendar
  identity is excluded; ten venue-disagreement observations omit venue data.

## Reviewed repaired artifact

The frozen full rerun completed at
`output/learning/20261016-3b828fe0d23747a7/`. The independent reviewer reproduced
all 4,002 evaluated SG predictions from the saved corpus with maximum error zero,
reproduced all 66 current ranks and projection diagnostics exactly, matched all
113 Sony 2026 frozen PIT scores, and verified the corpus, model and eleven
archived dependency hashes. DG 17619 has only two prior eligible rounds and is
absent from the repaired audit. The original three material repairs passed.

The same spline ridge at regularization 0.1 was selected by 2025 validation.
Training contains 225 events/26,171 player observations; validation contains
47/5,300. The 2026 exposed audit contains 37 events/4,002 observations and 186,849
dependent decisive pairs, with an identical cohort for all comparisons.

| Exposed retrospective measure | Repaired candidate | SG50 | Recalibrated frozen PIT |
| --- | ---: | ---: | ---: |
| Event-weighted log loss | 0.642518 | 0.656387 | 0.667975 |
| Brier score | 0.225974 | 0.232419 | 0.237463 |
| Pair ordering accuracy | 0.625510 | 0.605816 | 0.596233 |
| SG RMSE | 1.642753 | 1.726542 | unavailable |

The paired-event 95% bootstrap interval for candidate minus SG50 log loss is
[-0.018899, -0.008678]; versus recalibrated frozen PIT it is
[-0.033606, -0.016876]. These are exposed retrospective predictive diagnostics,
not untouched-holdout, executable-price, ROI or CLV evidence. Promotion remains
disabled. This identity-repair refit records zero newly completed events and
explicitly does not claim fresh weekly learning.

| Retained identity | SHA-256 |
| --- | --- |
| Report | `ce11bdcdbbb91edfffe475b675810b71c9fc740246aab840ce6545b902b8820e` |
| Evaluated model | `ccbdc9f0e2620f7f83f5007d2b2cb60aa6f9aa0959d8f21a5cca7009bfd1c34d` |
| Forward model | `0c8ac0eb645685dd648f2e572cc81b3e60456f623b1af9ffa2095134990ebbe1` |
| Resolved protocol | `71f9706ee1e0c9ff6581f0e61dc54751f9e254dc3ca2362b6849f9fc2d18a852` |
| Training-source gzip | `c4018b7eda1f7c51bf67bfd10c8f962714bc02d35628f0f8a248dc200d76c5fc` |

The artifact's `training-source.jsonl.gz` is 19,270,885 bytes and has the canonical
corpus hash recorded above. Its gzip differs from the seed because it also retains
the exact CLI source-manifest metadata. Both copies are readback-verified.

## Narrow producer guard shipped after that artifact version

The remaining review scenario was an otherwise dated snapshot whose standard
`eligibility.observed_tour` said LIV while the producer assumed PGA. The actual
reviewed event 528 snapshot explicitly verifies PGA, so its projections and saved
artifact remain valid. The current producer now considers both explicit
`section.tour` and `eligibility.observed_tour`, rejects contradictions/non-PGA or
missing tour evidence, and requires literal field verification, matching field
event ID and an empty invariant-failure list before exposing players. Explicit
verification errors and inactive sections are withheld.

This is a future-run admission guard, not a model-family change or retune. The
reviewed artifact retains its original archived CLI bytes with SHA-256
`87ecaf01d262822a768b8392ef3b55d1602caeb32f18639aed7c217418d981dc`.
The corrected shipping CLI has SHA-256
`e4463fe762249eed7801320efa1bd1cabc1b3b6811d073371808f0d06e891475`;
future weekly artifacts naturally capture that different implementation closure.
Neither the reviewed artifact nor its hashes were rewritten to pretend otherwise.

Forty-three challenger/run-history tests pass after the guard repair, including
the namesake, WAL-input replay, dated-calendar and standard eligibility cases.
Publication, installation, scheduler verification and promotion remain separate
release decisions; this work performs none of them.
