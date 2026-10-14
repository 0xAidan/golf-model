# Historical evidence preservation and reconciliation

Audit date: October 13, 2026 (America/Toronto). Scope: preserve and inspect sources without changing production data, predictions, weights, calibration or model promotion.

## Preserved sources

Artifacts are outside the checkout at `/Users/aidannugent/websites/golf-model-preservation/2026-10-13/`.

| Source | Verification | Coverage found |
|---|---|---|
| `current.sqlite` | SHA256 matches `current.manifest.json`; existing integrity manifest says `ok` | Frozen copy: 568 picks, 548 outcomes, 323 player results, 817 prediction-log rows, 2,872 ledger rows. Picks exist for five events; outcomes for three. |
| `exports-and-audits.tar.gz` | Full outer gzip read and all 1,857 tar headers passed; 328,163,425 bytes | 17 tournament exports, tick archives, 1,481 research-archive files, prior audits. Selected core JSON/JSONL files parsed and individually hashed. |
| `research-cards-output.tar.gz` | Full outer gzip read and all 2,952 tar headers passed; 25,823,472 bytes | Original local-recovery cards and ZIP, output research/cards, 175 provenance JSON files, live-refresh snapshot, static track record. |
| Static `trackRecord.json` copy | Exclusive copy and checksum manifest | Six named events; individual picks exist only for Arnold Palmer Invitational (14) and Cognizant Classic (15). |
| `history-evidence-vault.20261014T003000Z.jsonl.gz` | Exclusive new file, SHA256 and full gzip stream validated; 737,360,747 compressed bytes | All six whitelisted core tables from 22 source generations: current copy, four quarantine base files, and 17 tournament exports. All 132 table streams completed. |

Checksums:

- Current database: `de473c5d331e34623c8f9c24353cf745a6d42bf824ad91392451ff040a7a9540`.
- Exports/audits archive: `a620f3d9e1f552aa8c5b5df63a6f8624e9fcb549c5498b8a6d877c895d93772b`.
- Research/cards/output archive: `2c896d93418e81289e8653b7136dc34acb3c72a32b9d6a001ca2aaa37b52dbcc`.
- Logical evidence vault: `4291222388e42905f12ca818fbc4fdb559a8e5da83eaa6b2bbb6937b0a898ee5`.

Exact member names, sizes and validation timestamps are in `exports-and-audits.manifest.20261014T001602Z.json` and `research-cards-output.manifest.20261014T001958Z.json`. Archive validation does not establish factual accuracy or full-season completeness. The raw quarantine archive transfer remains separate and was not accessed; validate it after completion. A subsequent bounded logical collection read the six core tables directly from the four specified quarantine **base files** using `mode=ro&immutable=1` and `query_only`; their original WAL was deliberately not applied.

## Logical core vault completed

The new vault preserves **2,757,406 source rows** without extracting raw databases or changing any source: 206 tournament metadata rows, 12,824 picks, 12,788 outcomes, 12,308 player results, 2,712,717 ledger rows and 6,563 prediction-log rows. Repeated generations and conflicting duplicates remain separate; these totals are not unique wagers or a reconstructed season record.

Every row contains source ID, table, ordinal and canonical row hash. Export rows additionally retain archive/member and original-line hash provenance. SQLite sources retain path, size, modification time and immutable/WAL-read mode; this metadata fingerprint is not represented as a full database checksum. All source metadata remained unchanged during collection. The 132 completed table streams cover only `tournaments`, `picks`, `pick_outcomes`, `results`, `pick_ledger` and `prediction_log`; no tick archives, `market_prediction_rows`, configuration or secrets tables were exported.

Most of the 703 MiB vault is the already-preserved U.S. Open and Travelers export ledgers (1,448,570 and 1,170,767 rows). Their nested gzip JSONL was streamed and parsed, never extracted. Full validation read 6,677,247,428 decompressed stream bytes without storing that expanded data. All 206 tournament candidates remain `needs_identity_review`; missing tour/name/season identity is not invented or merged.

The source/table counts are in `history-evidence-vault.20261014T003000Z.jsonl.gz.manifest.json`; its separate `history-evidence-vault.validation.*.json` records post-collection gzip validation. The reproducible stdlib-only collector is [build_history_evidence_vault.py](../../scripts/build_history_evidence_vault.py). Five focused tests cover source immutability, table whitelist, reused IDs, conflicting-generation preservation, exclusive output, nested gzip provenance and missing identity. This is a ready reconciliation input, not a production restoration.

## What the preserved history contains

The 17 tournament exports contain **2,878 pick rows, 2,878 outcome rows, 1,989 player-result rows and 1,790 prediction-log rows**. All selected outcome rows reference picks within their own export folder. These are overlapping source observations, not a count of independent wagers.

- Lanes: 1,690 cockpit rows and 1,188 lab rows.
- Matchups: 1,311 labeled round-matchup rows, 815 tournament-matchup rows, and 149 matchup rows without a duration label.
- The remaining 603 picks are placement/outright rows. No selected export pick row has a group/three-ball market label. Some preserved cards mention those markets; their actual selections and settlement evidence still need section-level review.
- Outcome authorities include 409 void rows, 29 static track-record imports, 1,169 computed grades and 1,271 matchup-outcome grades. Authority labels are provenance, not independent verification.
- A bounded read of 52 Markdown files found 38 candidate betting-card files representing 36 distinct hashes. Early cards cover February–May events absent from the current pick store. Filename dates and card text do not prove pre-start publication.

The detailed event comparison is in `season-source-inventory.20261014T001702Z.json`; card provenance is in `card-source-inventory.20261014T002037Z.json`. No profitability statistics were calculated for this inventory.

## Reconciliation hazards

1. **Numeric IDs were reused.** Old tournament 2 is the U.S. Open; current 2 is Presidents Cup. Old 3 is Arnold Palmer; current 3 is 3M Open. Old 4 is Cognizant; current 4 is AT&T Pebble Beach. Source-generation-local IDs must never join archives to the current database.
2. **An internal manifest is stale.** Travelers' export manifest lists 148 outcomes, while its preserved outcome file contains 172. Retain both; do not delete the difference to make the counts agree.
3. **Chronology is incomplete.** All 17 archived tournament `date` fields are null. Early-season picks imported in June must not be labeled June predictions or treated as proven pre-event observations.
4. **Historical deduplication was unsafe.** The audited initialization path dropped the pick index and globally deduplicated with an identity missing tournament ID. Even with the separate code repair, initialize only disposable copies—not the preserved sources.
5. **Existing CLV is unsuitable as raw evidence.** Repeated learning calls can multiply rows, quote identities are incomplete, and existing implementations use inconsistent sign/metric conventions. Model-versus-book edge is not closing-line value. Raw CLV rowcount is not sample size.

## Next safe recovery procedure

1. Finish and validate every quarantine archive together with original WAL/SHM sidecars. Keep all checksummed source generations unchanged. Obtain consistent analysis copies; never copy only an active SQLite main file or ignore its WAL.
2. Create a **separate append-only reconciliation store**. Every source row keeps its archive/database hash, member/table, source-local ID, original payload and import-observation timestamp. Preserve conflicting versions instead of choosing one silently.
3. Resolve tournament identity using tour, vendor event ID and season, cross-checked against name, course and authoritative scheduled dates. Sponsor-name differences need explicit aliases. Missing identity stays unresolved.
4. Resolve decision identity using event/season/tour, market duration, round or group membership, selected player/opponent, source/lane/model/configuration, book, quoted price, and decision/snapshot time. Do not infer round, bookmaker or publication time when absent.
5. Match outcomes only after their source-local picks are resolved. Preserve stored profit, stake, void/push status, authority and locks. Collapse exact duplicate observations only in the reporting view, retaining all provenance links. Put disagreement in a review queue; do not retrospectively select favorable prices or grades.
6. Separate frozen displayed predictions, imported official cards, retrospective reconstructions, lab trials and confirmed actual wagers. Prioritize missing-event recovery from the 17 exports and February–May cards, then use quarantines/tick archives to restore timing and market identity.
7. Publish coverage before performance. Show missing markets/rounds/books, grade coverage, unavailable stake, source conflicts and chronology confidence. Do not claim full-season accuracy or profitability until reconciliation supports the claim.

## Learning roadmap with the current models preserved

The additive `/api/market-evidence` report is already independent of model/database initialization. It reads canonical stored outcomes through SQLite `mode=ro` and `query_only`, separates lanes and markets, discloses incomplete coverage, and keeps voids/pushes/unknowns distinct. See [market-evidence.md](../market-evidence.md).

The next learning unit should be a timestamped **evaluation report**, not a weight update:

- **Market evidence:** season/event/round/group/book/source breakdowns, stored flat-stake performance where complete, valid binary calibration, prediction/settlement/quote coverage, and uncertainty at the event level rather than treating correlated rows as independent.
- **Chronological evidence:** freeze decision-time predictions, quoted price and model configuration; match closing quotes before the correct market's start; disclose timing gaps. Evaluate proposed book, timing, market-selection and presentation policies against the same frozen predictions.
- **Shadow policy proposals:** write an append-only proposal with its hypothesis, eligible evidence, selection rules, model hash, data cutoff and evaluation contract. Run event-separated walk-forward evaluation and reserve untouched later-event holdouts. Include price availability, ties/voids, dead heats, withdrawals and missing-data exclusions.
- **No automatic promotion:** research results produce reviewable dossiers only. No report may call retuning, calibration replacement, dynamic-blend updates, registry writes, historical regrading or live strategy promotion. The existing post-tournament learning path can perform some of these mutations and is outside this workflow.

The immediate objective is a trustworthy historical record and better delivery of the existing forecasts. A successful research report does not authorize a model change.
