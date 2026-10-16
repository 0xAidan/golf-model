# Golf prediction recovery — October 15, 2026

There is substantially more history than the ten-event subset previously quoted.
That subset was a strict dashboard/baseline/72-hole selection-research cohort,
not the set of tournaments for which this project made predictions.

The recovered evidence is preserved separately from the live application. This
is a recovery checkpoint, **not a claim that every prediction has been found**.
Original source databases, cards, archives and histories have not been deleted
or rewritten by the recovery.

## What was recovered

| Source | Confirmed evidence | Important interpretation |
| --- | --- | --- |
| Cards, original files and complete history captures | 233 distinct complete card versions with indexed forecasts across 30 normalized event labels; nine additional complete notices/cards without indexed forecasts | Bytes/completeness are verified, publication is not. Versions and copies are not independent bets. Cards span February–October 2026. |
| Hidden original database at `~/.golf-model/data/golf.db` | 16,690 pick rows, 2,240 prediction-log rows, 327 analysis runs, full snapshots and market rows | 16,669 pick rows and most dense observations are repeated Truist refreshes; raw row count does not establish broad event coverage. |
| Same hidden database | 137,102 historical rounds from 2019–2026, plus original metrics and DataGolf/challenger forecasts | Input data and research forecasts are preserved, not mislabeled as issued selections. This may expand future model research. |
| Original export archive | 9,146 analysis-run records newly included in the logical vault, plus the previously preserved picks, logs, outcomes and ledgers | Rows retain archive/member and source-local identity. Tick-table members in this archive are empty, not missing successful forecasts. |
| Cursor and historical Git | Complete and partial cards, saved file versions, exact terminal API payloads and screenshot evidence; full reachable Git history now covers 692 commits | Partial captures are not stitched together. Research snippets and OCR are explicitly unverified. |
| Recovered historical API responses | Charles Schwab: 132 ranking rows and 132 frozen ranking rows; Memorial: 72 ranking rows and 72 frozen rows; Canadian Open: 72 ranking rows | Capture time is distinct from forecast/publication time. These fill important May–June evidence gaps. |
| Recovered old local snapshot | April 13 snapshot with 30 RBC Heritage rankings and 20 Valero previous-card rankings | Preserved exact bytes, not a replay using today's model. |
| Current VPS | Consistent full database snapshot acquired October 16 at 02:07:09.787 UTC, plus a complete logical sports-history vault | Covers the stated collection cutoff, not forecasts generated afterward. |
| Damaged September database, full SQL salvage | 2,502,646 market-prediction rows and 4,251 snapshot rows, in addition to the previously recovered 7,970 core rows | Newly retained from a damaged source; unverified salvage, not performance-eligible. |
| Broad resident Markdown content search | Seven additional distinct payloads in Downloads: five card versions, an explicit sandbox card and a Truist evaluation conversation | Original bytes and source-written dates retained; no publication or results inferred from the conversation. |
| Original Documents database, rescued through Finder | 21 picks, 2,215 prediction logs, nine full runs, 128,664 historical rounds and 327,935 odds rows | Older February–March generation; no dense/snapshot tables or May/PGA forecasts. Preserved with `quick_check`, snapshot/gzip hashes and a logical vault. |
| Five remaining small cloud databases | Empty old-worktree history schema; 5,754 research trial observations in two nonempty study generations; two empty study generations | All five preserved and integrity-verified. Trials are research lineage, not issued forecasts or independent bets. |

The 30 named card labels are supplemented by **two additional event
labels in exact API captures: Charles Schwab and Memorial**. Canadian Open
already appears among the original cards. PGA Championship remains a separate,
partial screenshot evidence class. These are source labels, not 33 certified
pre-event wagering cohorts.

The four principal database snapshot streams passed SQLite `quick_check` and
independent gzip decompression/hash verification. The full snapshots preserve
all their original tables. Logical exports whitelist sports-history tables and
retain source IDs, row hashes and original payloads; they do not initialize,
migrate, restore or regrade source databases.

## Where the recovered evidence is

Raw evidence is private, outside public web assets:

- Mac/archive files: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-local-discovery/`
- Server cards and provenance: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-server-discovery/`
- Cursor, Git and screenshot/OCR evidence: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-cursor-discovery/`
- Consistent database snapshots and logical vaults: `/Users/aidannugent/websites/golf-model/data/research/database-history-20261015/`
- Finder-rescued original Documents database: `/Users/aidannugent/websites/golf-model/data/research/database-history-20261016-finder/8340ec5baf39d26c/`
- Five small cloud databases: `/Users/aidannugent/websites/golf-model-preservation/2026-10-16-small-db-cloud-rescue/`
- Full forensic SQL salvage: `/Users/aidannugent/websites/golf-model-preservation/2026-10-16-full-forensic-sql/`
- Broader resident Markdown matches: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-broad-markdown-discovery/`
- Late exact-file cloud rescue: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-late-cloud-rescue/`
- Late native-folder cloud rescue: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-late-cloud-native-rescue/`
- Derived Markdown/JSON indexes: `/Users/aidannugent/websites/golf-model-reconciliation/2026-10-15/`

### Searchable private catalog

The current searchable artifact is
`/Users/aidannugent/websites/golf-model-reconciliation/2026-10-15/browser-pass-006/recovered-forecasts.html`.
It works offline, with player/text search, event/type/source filters, source-row
inspection and filtered JSON export. It contains **12,707 indexed observations
from 355 source payloads**. These include partial captures, repeated views and
research artifacts with explicit source-context labels; they are not 12,707 bets.
The full preserved database streams are separate and are not all rendered in
this browser.

Its source generations are `archive-pass-010` (2,797 Markdown payloads / 5,081
source references) and `structured-pass-007` (2,259 JSON payloads / 3,897 source
references). The manifest binds each input index and observation stream by
SHA-256. Original relative corpus references are retained alongside their
resolved absolute paths and complete provenance metadata. Sandbox-only cards
remain searchable as research cards; a sandbox model declaration alone does not
prove that a card was never issued.

Across both format indexes there are 5,055 distinct logical payload hashes
(5,056 format-index entries), totaling 2,464,146,247 decompressed bytes. Every
payload hash, every indexed source line/JSON pointer and all 8,978 resolved source
references passed independent verification. Browser filtering, source inspection,
JSON export and literal rendering of untrusted source text were checked offline.

The newest derived generation must be selected using its manifest and source
hashes; earlier `archive-pass-*` and `structured-pass-*` directories are retained
checkpoints. Some earlier indexes refer to expanded working copies that were
subsequently losslessly compressed. Current corpus manifests point to the
verified gzip payloads. Every source wrapper remains linked even when identical
bytes share one content-addressed copy.

`scripts/build_prediction_archive.py` indexes all supported Markdown player
tables, priced bullet forecasts, matchup projections and qualitative/AI
observations with exact line references. Its structured mode preserves saved
ranking/market arrays and original JSON pointers, including frozen/pre-tournament
arrays separately from live arrays. Unknown formats and unparsed candidates
remain preserved for review. No stake, settlement, ROI or CLV is invented.

### Full recovery of the damaged September copy

The existing disposable September 13 database copy was opened with the Mac
SQLite shell in read-only, immutable mode after a direct successful
`sqlite_dbpage` probe. The source is 6,835,355,648 bytes. Its SHA-256 before and
after recovery is identical:
`2f514028ff41c6ac631129698017c8de56eb494a00ca35425dc4f1346c6f3ef4`.
No archive was expanded and no recovery SQL was executed or imported.

The shell completed successfully within its 600-second bound. All
6,427,749,807 emitted SQL bytes are retained in the 308,767,964-byte
`full-recovery.sql.gz`, whose SHA-256 is
`1eae27ade5731a47182ef03c662789a943ef21af8a58b84eb3208a6e921b5b0e`.
Independent decompression/hash read-back passed. The compressed-size limit was
512 MiB and the minimum free-space reserve was 1 GiB; neither stopped capture.

The earlier recovery indexed only six core tables. This full stream also retains
dense market observations, snapshots, weights, rounds, metrics and other emitted
tables. Schema-only tables are not assumed empty. Some statements are not parsed
by the optional indexer but remain in the complete raw SQL. The optional large
lead sample was not published, protecting disk reserve; the raw gzip and scalar
manifest were finalized first. This is **uncorroborated salvage**, so it stays
outside verified results and model promotion. Fixture rows and June-restored
calendar metadata are not proof of original May predictions.

A bounded scalar analysis matched all recorded INSERT counts with zero parse
errors. The 2,502,646 dense rows are concentrated in U.S. Open (1,565,937),
Travelers (935,818) and Canadian Open (891), generated June 14–21. This is not
2.5 million distinct bets or broad all-season dense coverage. The 4,251 snapshot
rows span June 14–September 3 across 14 meaningful named summer event labels,
alongside separately retained fixture/stale labels. No snapshot event label or
generation prefix establishes a PGA Championship/Aronimink or May forecast.
`scalar-event-coverage.json` retains 97 source-local table/event/section groups and
97 exact raw SQL offset/hash samples. See the [full forensic salvage audit](2026-10-16-full-forensic-sql-salvage.md).

## Remaining gaps

- More than 22,000 listed old-project iCloud paths remain dataless; most are
  research artifacts. Accepted download requests do not prove successful recovery.
  Initially only 14 of 93 targeted paths were byte-captured. After the native
  Finder retrieval and a final targeted retry, **all 93/93 original target paths
  and all 75/75 files in the two small original-card folders have verified copies**
  across the immutable generations. The broader dataless research inventory was
  not downloaded wholesale and remains outside that successful target set.
- The old Documents main database was initially dataless and bounded reads timed
  out. A later exact-file download through Finder actually completed; its
  141,500,416-byte generation is now preserved. Finder reported full iCloud
  storage, which did not prevent this inbound download. Other cloud placeholders
  must still be evaluated by actual copied bytes, not accepted requests.
- Some Documents/Desktop recursive listings timed out. Their partial state and
  search roots are recorded in the local discovery report.
- macOS denied shell listing of Trash. A subsequent normal Finder search scoped
  to Trash for `golf` returned zero items; this is not a full Trash content
  inventory. No local Time Machine snapshots were listed, and no external backup
  disk was mounted at inspection.
- PGA Championship has a May 12 screenshot showing part of the field and a
  matchup, but its full original 156-player snapshot has not been recovered.
- No original published 2025 card was confirmed. The 2019–2025 round data are
  historical inputs, not evidence of earlier issued project forecasts.
- Existing quarantines include unreadable or only partially salvaged sources.
  Their bytes remain preserved; uncorroborated salvage is not promoted to verified
  historical results.

Connected Google Drive metadata searches for `golf`, `golf-model`, `Betting Card`
and `DataGolf` found no additional identifiable model archive or original forecast
card. Unrelated document results were not treated as project evidence.

The broad resident sweeps read 46,798 Markdown files and **120,922 JSON files** with
explicit negative counters. A final suffix pass considered the previously pending
99,639 listed Documents JSON candidates in 52.363 seconds: 71,069 resident content
reads, all negative for supported saved forecast arrays; 28,569 dataless paths and
one excluded path. All **242,583 JSON candidates in the retained listings** have
now been considered across the three passes. No cloud hydration was requested.
Across those passes, 119,671 dataless files, 1,552 oversized files and 438 excluded
paths were not read. Partial original listings and unsupported schemas remain
explicit limits; this is not exhaustive filesystem coverage. The new report is
`2026-10-16-remaining-json-discovery/resident-json-scan-report.json` under the
private preservation root.

A sanitized product inventory, `frontend/public/reports/history-coverage.json`,
binds its source index/inventory hashes and shows the 233 card versions across 30
labels separately from qualifying performance. It contains no private filesystem
paths, raw chat text or player-level source payloads. Recovered generation labels
have unknown timezone and are not assumed to be official event dates.

## Protection put in place

The production retention and storage-janitor timers were verified enabled/active,
then reversibly disabled/stopped on October 16 around 02:16 UTC. Both corresponding
services were verified inactive. The backup, grading, integrity and refresh
watchdog timers retained their prior states.

This follows discovery that the old retention “dry run” could call a deleting
function, and an archive checksum/window alone did not prove coverage of the
current database's candidate rows. The production retention period was 120 days;
current active tick rows started October 1, so this inspection does not establish
that the defect caused any earlier historical loss. Default preservation guards
and regression tests have been implemented locally. They also cover colliding
card/backup filenames, same-day forecast versions, duplicate historical records
and grading before-images. They have **not been deployed**; production deletion
timers remain paused pending a separately verified patch. New forecasts must
continue to write successfully even when historical duplicates prevent a unique
index, which has its own dirty-database and concurrent-writer regression cases.

Only working copies created during this recovery were compressed or removed
after byte-for-byte decompressed hash verification. Originals and the original
preservation archives remain intact. The temporary low-space condition was
resolved without deleting historical source data.

## Detailed audits

- [Local files and cloud placeholders](2026-10-15-local-history-discovery.md)
- [Cursor, Git and visual evidence](2026-10-15-cursor-git-history-discovery.md)
- [Server cards and provenance](2026-10-15-server-history-discovery.md)
- [Database sources and exact hashes](2026-10-15-database-history-discovery.md)

Next, reconciliation must connect original forecasts to the correct event, tour,
model version, timing and result while retaining every conflicting version. The
expanded evidence must not be turned into a fabricated bankroll curve by counting
refresh ticks, restored records, research trials or duplicate copies as wagers.
