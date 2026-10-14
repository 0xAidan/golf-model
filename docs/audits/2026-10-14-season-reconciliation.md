# Season reconciliation — 2026-10-14

## What this establishes

The independently preserved sources now have one derived, source-linked season
view. It is a calendar-complete view of the available record, **not a complete
wager ledger or independently verified sportsbook settlement history**.
Twenty-five of 41 elapsed calendar events have reconciled core picks; one future
event also has picks. Missing events remain visible.

The exclusive `run-005` generation retains 52,659 core source envelopes from 24
source generations and produces 3,026 reporting groups. Source-local identities
prevent reused database IDs from joining unrelated events. Economic quote
normalization removes duplicate formatting, while ambiguous repeated quotes,
conflicting outcomes and incomplete contracts are withheld from performance.
No original row is rewritten or removed.

The five original preserved artifacts match their original SHA-256 values and
were rechecked before and after reconciliation. The separate quarantine archive
preserves all 18 database/WAL/SHM files. Two source databases remain unreadable.
A bounded literal-only recovery on an isolated copy salvaged 7,970 core rows:
4,059 exactly match healthy payloads; 3,911 lack that corroboration. All salvage
remains explicitly unverified and excluded from primary performance and policy
research. WAL headers were inspected; incompatible frames were not replayed.

There are 144 conflicting groups and 1,388 incomplete groups outside the conflict
bucket. Missing round identity affects 1,372 groups across the two model lanes;
18-hole returns are withheld. Archived cards contribute 218 distinct file/line
records, not fabricated stakes or outcomes. No actual group-market selections
were found in the preserved corpus.

## Selection research

The frozen-model protocol compares four predetermined rules separately for each
market, lane and model variant. It rejects mixed scopes and ambiguous timing,
uses chronological whole-event splits, purges overlapping boundary events and
requires at least eight earlier events, five later events and thirty later
decisions before uncertainty estimates. Stored stakes and normalized research
returns are separate. No predictive model is fitted or modified.

The 520 eligible groups are not one valid pooled cohort. Every properly scoped
comparison is insufficient. Dashboard 72-hole baseline has 72 eligible quotes
over ten events, split seven earlier and three later. There is **no promoted
selection policy and no change to live ranking**. Historical outcomes have
already been examined, so retrospective later-event checks are not an untouched
holdout. Future promotion needs independently frozen, complete records collected
before outcomes; the runbook describes that contract.

## Reproducible artifacts

- Report ID: `ff63aeda67e8ad5564ce8a32221724058aa15aaadd5b4bfcb89397145413d46b`
- Source manifest: `65badab3210915f1492d487af4c81cec52ce9c2660f4b504682fcf6f00bb9009`
- Calendar: `4b9a25de0f2914c2c2e113edd45dfd77c7d2473e0c9d7769d5e9e650ec75dda6`
- Reporting implementation: `fa8e75197d8863300a4c289c4b729fca92b48f01b1ccf40fe53043db6ee7bba8`
- Public JSON: 77,579 bytes, SHA-256 `667a5076e56fc951db4950c81cd11b01e962eb296a8d6feb9158c624443f93cc`
- Public CSV: 954,455 bytes, SHA-256 `c8087819b65efcd274f3eebf1c4d1a4def8233d50062fce621394893376ee318`

The private generation also includes original envelopes, canonical decisions,
provenance links, source manifests, full scoped evaluation and exact reporting
implementation copies. Only the sanitized JSON/CSV pair is public.

## Delivery and verification

Results defaults to the lazy-loaded Season record. Current store remains at
`/evidence?view=store`. The season page uses one precomputed static JSON response;
market/lane/version/calendar interactions are local and do not scan archives or
query the production database. Desktop and mobile confirmation passed after one
batched review fix. Mobile height reduced from 6,957 to 4,066 pixels with no
horizontal overflow. Synchronized filters and empty 18-hole research scopes were
verified in the browser. The finish review returned ship for the scored fixes.

Validation: 139 focused Python tests passed, with Ruff clean. The earlier full
frontend run passed 425 tests across 72 files. After the final UI review batch,
30 focused frontend tests, typecheck, targeted ESLint, production build and bundle
budget passed. Exact-head CI and production delivery are recorded below when
complete; local checks alone are not live deployment evidence.

See [the reconciliation runbook](../runbooks/historical-reconciliation.md) for
reproduction and [the limited delivery runbook](../runbooks/matchup-desk-deployment.md)
for isolation and rollback. Normal backend rollout remains prohibited because
source-only grading repairs and automatic retuning are outside this release.
