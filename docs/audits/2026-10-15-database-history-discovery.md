# Original database prediction and ranking discovery — October 15, 2026

The historical sources are preserved separately from the live application. No
source database was restored, migrated, regraded, imported or deleted. Forecast
observations include ungraded rows; they are not restricted to profitable picks.
No model was retrained using the newly discovered corpus during this preservation.

## Hidden local source recovered

`/Users/aidannugent/.golf-model/data/golf.db` was physically resident and readable,
unlike the older Documents-folder cloud placeholders. Its separate consistent
SQLite backup passed `quick_check`, includes committed WAL data, and was gzip
preserved with independent decompression/hash verification. Original source file
metadata was unchanged. The exclusively owned uncompressed temporary duplicate was
removed only after preservation verification.

Private source manifest:
`data/research/database-history-20261015/61fd3785dcae0a44/manifest.json`.

| Preserved evidence | Rows |
| --- | ---: |
| Picks, including ungraded forecasts | 16,690 |
| Prediction probability log | 2,240 |
| Model/source metrics | 159,393 |
| Dense market prediction observations | 778,974 |
| Full live-refresh snapshot sections | 692 |
| Full analysis run records | 327 |
| Historical DataGolf predictions | 67,639 |
| Challenger predictions | 20,392 |
| Historical rounds | 137,102 |
| PIT rolling/course rows | 69,348 / 941 |
| Results / pick outcomes | 80 / 7 |

There are 13 source-local tournament rows: Pebble Beach, Genesis, Cognizant,
Arnold Palmer (two literal aliases), Players, Valspar, Houston, Valero, Masters,
Heritage, Cadillac and Truist. Pick recording dates span February 15–May 6, 2026;
prediction-log dates span February 11–May 6. Round seasons span 2019–2026. These
rounds expand potential future research coverage, but tour/calendar identity must
be validated before training. Provider event IDs are not globally unique across
tours or source generations.

The logical preservation vault is 196,678,929 compressed bytes, SHA-256
`fcbb69b497b5dbb66b81c4f89a80535a22fa535f4860c56a89308437fdf7cfab`.
The full SQLite snapshot SHA-256 is
`606d1f8af7c8591df6cd9835e4329b2f082c0a4627cc52703626ed4c547cc6f2`;
its gzip is 150,274,478 bytes, SHA-256
`6fbb310ae92b8e1bdd528ac5f457a3e3a7797a9547b9fafe437cc2a48407138a`.
Tables outside the logical sports whitelist remain present in the private full
snapshot; no arbitrary settings or private tables were logically exported.

## Original forecasts versus fixtures and refresh repetitions

`hidden-local-prediction-coverage.json` in that private collection lists every
source-local pick/log tournament and all dense/snapshot identity groups with
recorded-date ranges. It does not globally join integer foreign keys.

The 778,974 dense rows include 778,386 real-named Truist observations recorded
May 4–6 across live, upcoming, legacy and lab lanes. The remaining 588 have generic
Current/Next Event identities or an explicit test section and must not be counted
as original named PGA predictions. Repeated refreshes and model lanes are retained
as source references, not counted as independent bets.

All 692 snapshot payloads were inspected for complete ranking arrays. There are
7,925 raw ranking observations: 7,776 are the 72-player Truist field repeated in 54
live and 54 upcoming sections. The remaining 149 are generic Current/Next Event
fixtures or one-player Heritage stubs. Other snapshot identities include empty
Valero, Masters and Zurich guard/test payloads. The May 12 maximum timestamp is
mostly repeated fixture activity; it does **not** establish a full May 12 PGA
Championship forecast. No PGA Championship/Aronimink full-field projection was
found in this database.

`hidden-local-source-quality-flags.json` supplements the untouched initial raw
vault with source-local fixture context flags. Raw rows and payloads remain intact;
neither fixtures nor unresolved identities become performance evidence.

The five-table exact-payload comparison with the prior compact core vault found
no byte-identical row payloads for this source. That is an expansion in preserved
source generations, not proof that every row is a new independent forecast:
timestamps, schema, row IDs and source-local histories differ. Semantic lineage
and issued-versus-refresh reconciliation remain separate work.

## Additional server source

`/opt/golf-model/.worktrees/1b-worker-runtime/data/golf.db` was backed up through a
query-only source connection, including committed WAL data, and streamed as gzip.
Remote `quick_check` passed; the decompressed transport hash was independently
verified locally. Its original remote snapshot SHA-256 is
`62895322628610d595d322a0d325d6fbfd3a8e75b7ed3168e3c474482283338d`.
`server-worker-runtime.provenance.json` links the remote source to the local vault
at `ad22936a39384944/manifest.json`.

It contains 7 tournament rows, 80 picks, 1,355 prediction-log rows, 86,460 metrics,
36 runs, 92 challenger predictions, 14,378 rounds, 10 dense rows and 2 snapshots.
Recording timestamps cluster on July 31, 2026, including reconstructed old events
and explicit Current/Next Event fixtures. These are preserved source observations;
the restoration timestamp is not an original pre-event publication timestamp.

## Current live server cutoff

The current `/opt/golf-model/data/golf.db` was also captured through a frozen
read transaction and consistent SQLite backup. Snapshot acquisition began at
**2026-10-16 02:07:09.787368 UTC** and streaming completed at 02:08:24.095478 UTC.
This is an explicit cutoff, not a claim to cover forecasts generated afterward.

The source snapshot passed `quick_check` and gzip decompression/hash verification:

- SQLite: 515,338,240 bytes, SHA-256
  `ff25d93e27fbdefa0075983e74e9f9e778f8859f1cacafa80b2107564a592c3b`.
- Gzip: 63,350,979 bytes, SHA-256
  `3318ae1ca1b5b5295e1fddf07f6964491f73b8aa62347e0be0a006135dc2d5ec`.

`server-current-20261016.provenance.json` records 21 tournaments, 527 picks,
817 prediction-log rows, 758,258 dense forecasts, 344 full snapshot sections,
46,295 metrics and 35,471 rounds. The verified full snapshot preserves every
table. The additional logical export completed with 1,164,374 rows across all
present whitelisted tables, including 1,809 full runs, 55,040 challenger forecasts,
83,463 CLV rows, 503 outcomes and 323 results. The 113,028,003-byte logical gzip
has SHA-256 `e33b85aa4d150d786ad56e39f8b88473e02aaa4ef2980954c44e17ac779aea41`;
`server-current-20261016.logical-manifest.json` contains table closure states.
Named-book CLV rows are preserved as potential historical movement evidence;
they are not assumed linked to selected or executed forecasts.

Only exclusively owned temporary backup/decompressed duplicates were removed
after local preservation/hash verification; the original server database remains
untouched. Five-table comparison against the previous compact vault found exact
payload matches for 21 tournaments, 519 picks, 5 outcomes, 132 results and all 817
prediction-log rows. Eight pick payloads, 498 outcome payloads and 191 result
payloads differ. These counts retain source generations; differences do not
automatically constitute independently issued new forecasts or new bets.

## Older cloud sources and export archives

At the initial discovery, these files were iCloud-dataless placeholders rather
than recovered bytes; accepted `brctl download` requests were not a successful download:

- `Documents/golf-model/data/golf.db`: 141,500,416 advertised bytes, zero blocks.
- `Documents/golf-model/.worktrees/event-cockpit-rebuild/data/golf.db`: 454,656
  advertised bytes, zero blocks.
- Four research-study database paths below `output/research/optuna` and
  `output/research/archive/*/files/optuna`: advertised sizes 9,396,224, 126,976,
  114,688 and 114,688 bytes. Their bytes/schema have not been read here.

### Finder download follow-up — October 16

The parent opened Finder and clicked the exact main database's Download control.
Metadata checks confirmed that the file actually became resident at **03:05:58
UTC**: 141,500,416 allocated bytes, dataless flag cleared. The main Documents
database is therefore no longer an unresolved content gap. The worktree/study
databases above were not downloaded in this follow-up.

An inactive-source SQLite backup used `mode=ro&immutable=1` after verifying its
WAL was zero bytes; the cloud-placeholder SHM was not opened. No application
initialization or source full-hash pass ran. Snapshot `quick_check` and independent
gzip readback passed, and source metadata was unchanged. The uncompressed
preservation snapshot was retained.

Private manifest:
`data/research/database-history-20261016-finder/8340ec5baf39d26c/manifest.json`.
Snapshot SHA-256:
`123ef94092a622d6d9961e954759e4e5910a25cae2d63afbda837371f7e4a39e`.
Gzip: 39,346,166 bytes, SHA-256
`2208ad47d2aef8067ebd6bd433dc1647353117050e2e85344bca5a709d34d0c8`.
Logical vault: 56,777,230 bytes, SHA-256
`f2bb00fdcfe3402af5e1f312b27364b6968644e7e55a6bedf113213f56569e4c`.

This is an older February–March generation: five tournaments (Pebble Beach,
Genesis, Cognizant, Arnold Palmer and Players), 21 picks, 2,215 prediction logs,
nine full runs through March 15, 80 results and seven outcomes. It also preserves
59,732 metrics, 128,664 rounds, 67,639 historical provider predictions and 327,935
odds rows. There are no dense-market or full-snapshot tables and no May/PGA
forecast in this database. These are additional source generations, not assumed
new independent bets. Six collector tests, including the explicit empty-WAL
requirement and SHM avoidance, pass.

### Final five small cloud database leads

At 03:38 UTC, exact-file `brctl download` requests plus native Finder navigation
made the remaining old worktree database and all four study databases resident.
Only these five known files, 10,207,232 advertised bytes combined, were requested;
no research directory was downloaded. Each source had absent/zero-byte WAL, so the
collector used `mode=ro&immutable=1` and did not open cloud SHM. All five snapshots
passed `quick_check`, gzip decompression/hash readback, and unchanged source
metadata checks during capture.

Their private manifests and full compressed snapshots are under
`/Users/aidannugent/websites/golf-model-preservation/2026-10-16-small-db-cloud-rescue/vaults/`.
`source-table-inventory.json` binds the subsequent table counts to those verified
snapshot hashes:

| Source | Verified content | Interpretation |
| --- | --- | --- |
| `event-cockpit-rebuild/data/golf.db` | Empty application history tables; one schema-version row | No additional issued forecasts |
| Main `output/research/optuna/studies.db` | 5,742 trials, 28,710 trial attributes, 40,194 parameter rows | Research lineage, not issued selections |
| March 23 `181452` study archive | 12 trials across three studies | Separate preserved research generation |
| March 23 `181622` and `181724` archives | One study each, zero trials; identical snapshot hashes | Empty research generations; both source wrappers retained |

The main study snapshot hash is
`6a6f7cbde0f9d562533bf4ba3b107fbdbf2fd386dff6b1e3bb65c1771eda3853`;
the 12-trial archive is
`6d17bb17b7afae7af97563991d5a38c777fc5849ab0285c631fc974966d47db2`.
These are **5,754 trial observations, not new wagers**, and no extra issued-card
prediction rows were recovered. All original schemas and trial attributes remain
in private full snapshots even when outside the sports-history logical whitelist.

A subsequent direct cloud-source reinspection returned `file is not a database`.
No source repair was attempted. Final inventory instead reads verified preserved
gzip snapshots through disposable exact-byte copies and repeats SQLite integrity
checks there. Their snapshot hashes still match; transient cloud residency is not
treated as a durable archive. This follow-up closes all five known small-database
content gaps and supersedes their earlier dataless status below.

The original `exports-and-audits.tar.gz` is already preserved with SHA-256
`a620f3d9e1f552aa8c5b5df63a6f8624e9fcb549c5498b8a6d877c895d93772b`.
The previous logical vault admitted only six core tables, omitting exported dense
prediction and full-snapshot tables. The expanded collector reads whitelisted
JSONL members, including nested gzip members, without extraction. It retains
archive/member hashes, source-local row references, line hashes and raw payloads.

The expanded archive export completed after a temporary disk-reserve pause. Its
223 admitted members contain 2,703,039 rows: 2,684,341 ledger observations, 9,146
full run records, 2,878 picks, 2,878 outcomes, 1,989 results, 1,790 prediction logs
and 17 tournament rows. The gzip vault is 731,911,132 bytes, SHA-256
`60ca1adbf1b3b45f980745922d74d34680eaca0d448e0c606c3c585dde60632d`.
Every admitted member has a raw-member hash and complete closure state.

Crucially, every tick prediction/snapshot JSONL member in that archive is empty.
The live VPS export directory was also independently checked: all 55
`market_prediction_rows.jsonl` and all 55 `live_snapshot_history.jsonl` files have
zero bytes. Empty files are preserved and reported as zero; they do not provide
recovered dense forecast history. Full run JSON payloads are an additional source
beyond the old six-table logical vault. The verified local/server database
snapshots provide the nonempty dense/snapshot sources actually recovered here.

After disk space cleared, both older Documents databases received another targeted
download request and a real header-read probe. Each read was killed after its
eight-second deadline and each file remained dataless with zero blocks. No OS
permission or account error was returned, so no specific account repair can be
inferred. These are explicit unavailable-content gaps, not empty databases.

## Existing retention risks discovered without invoking them

At discovery, `scripts/run_retention_cycle.py` called the real pruning function even
in its `dry_run=True` branch. `src/cold_archive.py` validated a prior archive's timestamp window and file hashes
without binding the manifest to the source database or exact current rows pending
deletion. A checksum-valid empty archive can therefore be an inadequate coverage
guarantee for later backfilled rows. No retention/prune routine was run during this
discovery. These findings were handed to the parent implementation for protecting
future history; the preservation collector performs no deletes on original data.
The separate source patches add default preservation and exact-rowset checks;
their deployment must be verified separately from this read-only collection.

Additional source guards preserve backup generations, duplicate original picks
and outcomes, different archive bytes, and same-day card/provenance versions.
Legitimate regrading journals exact prior outcome payloads before updating current
outcomes. New forecasts and backups remain functional. The focused mutation,
backup, card/provenance, DB and report suite passed 58 tests; the separate existing
grading/backup integration suite passed 69 tests, and targeted Ruff passed.

## Reproduction and checks

`scripts/collect_prediction_database_vault.py` opens source databases with
`mode=ro` and `query_only=ON`; it never imports application schema/migration code.
Full snapshots use SQLite backup, not a copy of the main file that omits committed
WAL pages. Logical exports use a strict sports-history whitelist, source hashes,
row hashes, table closure states and fixture flags. Every raw row starts with
`performance_eligible: false` until separately reconciled.

```sh
python3 scripts/collect_prediction_database_vault.py \
  --source /Users/aidannugent/.golf-model/data/golf.db \
  --prior-core-vault /private/compact-core-vault.jsonl.gz \
  --output data/research/database-history-new-generation

python3 scripts/collect_prediction_database_vault.py \
  --archive /private/exports-and-audits.tar.gz \
  --output data/research/database-history-new-generation
```

Four targeted preservation tests pass: committed WAL rows survive, originals do
not change, fixture rows are retained and ineligible, cloud placeholders are not
opened, and nested exported gzip members retain exact member/line provenance.
The learning challenger has a separate fourteen-test temporal/evidence suite.
