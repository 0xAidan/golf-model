# Local prediction history discovery — 2026-10-15

Audit date: October 15, 2026, America/Toronto. Collection timestamps use UTC; some therefore read October 16. This report covers Mac files and locally preserved archives. Parallel server, database and Cursor investigations have separate reports.

## Finding

The historical corpus is substantially larger than the ten-event dashboard 72-hole **selection-eligible** subset previously discussed. The old local project still contains thousands of original output paths, including early-season cards absent from the current checkout. A narrow eligible performance cohort must not be described as the full prediction history.

The additive discovery corpus currently preserves:

| Material | Source references | Distinct logical payload hashes |
|---|---:|---:|
| Markdown | 2,522 | 2,452 |
| JSON, including explicitly labeled resource forks | 2,205 | 2,167 |

These are source/payload counts, not bets or independent forecasts. Research trials, backtests, methodology, audits, duplicate copies and fixture labels remain distinguishable. Thirteen JSON references are macOS resource-fork metadata, explicitly labeled `macos_resource_fork`.

The named non-research “Betting Card” inventory contains **190 distinct card payloads across 30 named event labels**, plus 13 payloads labeled Test Event / Current Event / Future Event. Sponsor/title aliases were normalized only for this inventory table. Event identity and issued-forecast timing still require reconciliation; a card title is not proof that its field corresponds to the official event.

Recovery is **not complete**. The metadata inventory contains 25,767 paths, including **22,293 unresolved dataless iCloud entries** at the last collector snapshot. Most are old research artifacts. Documents and Desktop recursive scans had bounded listing timeouts. Neither missing bytes nor unknown chronology is treated as a zero, a loss or proof that no prediction existed.

## New preserved evidence

All new files are under:

`/Users/aidannugent/websites/golf-model-preservation/2026-10-15-local-discovery/`

| Path | Purpose |
|---|---|
| `corpus/<sha256>.md.gz` | Exact logical Markdown bytes, content-addressed and compressed |
| `sources.jsonl` | Every source wrapper/path, logical hash, payload size, corpus path, headings, filename dates and source kind |
| `json_corpus/<sha256>.json.gz` | Exact original prediction/provenance/snapshot/research JSON bytes |
| `structured_sources.jsonl` | Independent JSON source references and context |
| `files.jsonl` | Loose-file metadata, available hashes and explicit dataless states |
| `listed-paths.json.gz` | Compressed filename discovery list |
| `hydration-requests.json` | The 93 targeted original-file download requests and observed states |
| `hydration-final-outcomes.json` | Final byte-capture matching for each of the 93 target requests |
| `named-card-inventory.json` | The 30 named event labels, three fixture labels, counts and every exact card source reference |
| `urgent-local-snapshot-source.json` | Provenance for the recovered old RBC/Valero snapshot, also merged into the main structured manifest |
| `validation.json` | Logical payload validation and unchanged original archive checks |
| `summary.json` | Counts, scan states, errors and limitations |

Every actual recovered payload has a SHA-256 hash. Duplicate payloads share storage, while every archive, nested ZIP and loose-file path retains a separate source reference. No unsafe archive pathname is used as a destination: writes use only the SHA-256 filename. No original card, archive, source database or historical record was rewritten, moved, initialized, imported or deleted.

The Markdown corpus occupies approximately 21.1 MB compressed and the JSON corpus approximately 19.1 MB compressed. More than 2.39 GB of logical source payloads have been checked without retaining expanded duplicate copies. The collector initially created raw working copies; only those newly generated copies were compressed, decompressed-hash-verified and removed. The original archives were never removed.

## Original source locations

### Old local project

`/Users/aidannugent/Documents/golf-model/`

The output tree has 21,974 files by direct metadata traversal: 11,002 Markdown files, 10,960 JSON files, four research databases, three JSONL files, one ZIP and four extensionless files. Its 75 non-research Markdown files include original cards, methodology, sandbox, audit and QA documents.

Important subdirectories:

- `output/archive/`: early archived cards, including Genesis February 15; Cognizant February 23/26; Players March 9/10/14; Valspar March 16/17; Houston March 23/24; Valero March 30/31; Masters April 6; and Truist May 4/5.
- `output/md cards/`: early original card copies and provenance JSON.
- `output/md cards.zip`: an original ZIP wrapper whose nested contents also survive in the preserved server-output archive.
- `output/research/archive/20260323_181452/`, `20260323_181622/`, `20260323_181724/`: old research runs, including files, registry/proposal metadata and Optuna databases.
- `data/live_refresh_snapshot.json`: a newly retrieved April 13 snapshot.
- `.worktrees/event-cockpit-rebuild/`: a second historical checkout, separately investigated by the Cursor/Git agent.

Fourteen old-project Markdown source paths have verified copies in the corpus. They include the newly recovered Genesis February 15 and Masters April 6 originals, duplicate original cards already surviving in the archives, one research output and QA/supporting material. This count requires actual copied bytes; a transient availability flag alone does not establish recovery.

The old snapshot has SHA-256 `50e5661840036560fe69b78422161873270ef103beb2ed49f497b24555b7007b`, 65,441 bytes and explicit generation time `2026-04-13T17:43:25.274583+00:00`. It retains 30 RBC Heritage upcoming rankings and 20 Valero Texas Open previous-card rankings. Its source is separate from the later 72-player Bermuda snapshot.

### Golf inputs

`/Users/aidannugent/Documents/golf/` contains eight CSV input files, including recent form, 12-/24-round extracts, tournament simulation and TPC approach/OTT/SG inputs. Matching Downloads filenames are leads for input provenance; input statistics are not issued forecasts.

### Current checkout and iCloud copy

- `/Users/aidannugent/websites/golf-model/`
- `/Users/aidannugent/Library/Mobile Documents/com~apple~CloudDocs/aidan's github/golf-model/`

The current checkout has only 12 loose non-research Markdown outputs. It must not stand in for the older Documents tree or the preserved production archives.

### Original preserved archives

`/Users/aidannugent/websites/golf-model-preservation/2026-10-13/`

| Original archive | SHA-256, rechecked against its preserved manifest |
|---|---|
| `research-cards-output.tar.gz` | `2c896d93418e81289e8653b7136dc34acb3c72a32b9d6a001ca2aaa37b52dbcc` |
| `exports-and-audits.tar.gz` | `a620f3d9e1f552aa8c5b5df63a6f8624e9fcb549c5498b8a6d877c895d93772b` |

All Markdown and Markdown-gzip members in both archives were read. The first archive has 1,468 real Markdown members: 26 local-recovery documents, 177 archived output files, 38 other output/audit/backtest files and 1,227 research documents. The exports archive contributes 746 additional Markdown-gzip references. The nested original `data/local_recovery/md cards.zip` adds 26 source wrappers without pretending identical bytes are new predictions.

All relevant JSON and JSON-gzip members were also preserved, including 201 prediction-run provenance references, 1,968 research-trial references, the full later snapshot and track record. The later snapshot contains 72-player rankings in original/lab/legacy sections. Source kinds preserve the difference between experiments and issued-card candidates.

## What the card bytes preserve

The recovered cards contain real historical model information, not merely retrospective summaries:

- Original ranked player names and composite, course-fit, form and momentum values.
- Explicit Generated timestamps as source assertions.
- Matchup picks, opponents, 72-hole labels, quoted odds, EV and tiers when supplied.
- Outright, Top 5/10/20 and first-round-leader selections in some early cards.
- AI watch/fade tables and recommended-bet tables, retained as distinct sections.
- Explicit baseline strategy labels and blend weights on later early-season cards.
- No-value/no-pick states, which are also historical outputs.

For example, the February 17 Genesis card preserves a Top 20 model ranking and separate AI FRL / Top 5 / Top 10 recommendations with odds and source-written stakes. The April 8 Masters card preserves five matchup selections, odds and EV, alongside an explicit `verified_baseline_v4.2` strategy snapshot. Missing bookmakers, stakes, model probabilities, round identities or settlement evidence remain missing; this inventory does not infer them.

## Named card coverage

The dates below are **filename source dates**, not verified event dates or proof of pre-event publication. Labels such as Masters in August show why calendar reconciliation is necessary. Counts collapse byte-identical payloads while retaining every source wrapper.

| Card event label | Distinct payloads | Source references | Filename range | Classification |
|---|---:|---:|---|---|
| 3M Open | 12 | 12 | 2026-07-16–2026-07-26 | Named card source |
| Arnold Palmer Invitational | 2 | 5 | 2026-03-08–2026-04-05 | Named card source |
| AT&T Pebble Beach Pro-Am | 3 | 6 | 2026-02-11–2026-02-15 | Named card source |
| Bank of Utah Championship | 6 | 6 | 2026-10-01–2026-10-05 | Named card source |
| Baycurrent Classic | 12 | 12 | 2026-10-01–2026-10-11 | Named card source |
| Biltmore Championship Asheville | 4 | 4 | 2026-08-27–2026-09-13 | Named card source |
| BMW Championship | 11 | 11 | 2026-08-13–2026-08-23 | Named card source |
| Butterfield Bermuda Championship | 6 | 7 | 2026-10-08–2026-10-13 | Named card source |
| Cadillac Championship | 1 | 2 | 2026-04-29–2026-04-29 | Named card source |
| Cognizant Classic | 1 | 2 | 2026-02-28–2026-02-28 | Named card source |
| Current Event | 5 | 5 | 2026-07-07–2026-08-31 | Fixture / placeholder label |
| FedEx St. Jude Championship | 11 | 11 | 2026-08-06–2026-08-16 | Named card source |
| Future Event | 4 | 4 | 2026-07-07–2026-08-23 | Fixture / placeholder label |
| Genesis Scottish Open | 12 | 12 | 2026-07-02–2026-07-12 | Named card source |
| ISCO Championship | 2 | 2 | 2026-07-12–2026-07-12 | Named card source |
| John Deere Classic | 12 | 12 | 2026-06-25–2026-07-05 | Named card source |
| Masters Tournament | 5 | 8 | 2026-04-06–2026-08-23 | Named card source |
| RBC Canadian Open | 2 | 2 | 2026-06-14–2026-06-14 | Named card source |
| RBC Heritage | 5 | 7 | 2026-04-13–2026-08-23 | Named card source |
| Rocket Classic | 13 | 13 | 2026-07-23–2026-08-03 | Named card source |
| Test Event | 4 | 4 | 2026-07-07–2026-08-23 | Fixture / placeholder label |
| Texas Children's Houston Open | 3 | 7 | 2026-03-25–2026-03-25 | Named card source |
| The Genesis Invitational | 2 | 6 | 2026-02-15–2026-02-17 | Named card source |
| The Open Championship | 12 | 12 | 2026-07-09–2026-07-19 | Named card source |
| THE PLAYERS Championship | 1 | 3 | 2026-03-15–2026-03-15 | Named card source |
| TOUR Championship | 9 | 9 | 2026-08-20–2026-08-27 | Named card source |
| Travelers Championship | 13 | 13 | 2026-06-18–2026-06-29 | Named card source |
| Truist Championship | 1 | 2 | 2026-05-06–2026-05-06 | Named card source |
| U.S. Open | 12 | 13 | 2026-06-14–2026-08-23 | Named card source |
| Valero Texas Open | 1 | 2 | 2026-04-01–2026-04-01 | Named card source |
| Valspar Championship | 1 | 2 | 2026-03-18–2026-03-18 | Named card source |
| WM Phoenix Open | 2 | 4 | 2026-02-07–2026-02-07 | Named card source |
| Wyndham Championship | 13 | 13 | 2026-07-30–2026-08-10 | Named card source |

### May–early June gap

No named PGA Championship, Charles Schwab, Memorial, Myrtle Beach or Colonial card filename was found in the listed loose/pending paths or recovered tar/ZIP members. This is a search result with the access limits above, not a declaration that the predictions never existed.

The following original provenance files do exist:

- `masters_tournament_provenance_20260508.json`
- `masters_tournament_provenance_20260511.json`
- `masters_tournament_provenance_20260512.json`
- `masters_tournament_provenance_20260513.json`
- `masters_tournament_provenance_20260605.json`
- `masters_tournament_provenance_20260609.json`

Inspected payloads explicitly identify `Masters Tournament`; their later generation dates cannot be used to relabel them as PGA/Schwab/Memorial forecasts.

The preserved `value_bet_audit_20260531.json` explicitly describes a December 1, 2025–May 31, 2026 walk-forward backtest across 22 PGA events and 1,902 placement bets, alongside four live +EV snapshots with 80 gradeable bets. It is retained, but backtest output cannot fill a missing issued-forecast ledger. No 2025-dated original card filename has yet been recovered from this Mac corpus.

## Searched roots and limits

Counts are matched file paths returned by the filename traversal, not golf predictions.

| Root | Listing state | Returned paths |
|---|---|---:|
| `~/Documents` | Partial after 45-second listing limit | 252,460 |
| `~/Downloads` | Completed | 553 |
| `~/Desktop` | Recursive listing stalled; direct child listing inspected | 0 recursive matches returned before timeout |
| `~/websites` | Completed | 6,085 |
| `~/Library/Mobile Documents/com~apple~CloudDocs` | Completed | 4,958 |
| `~/My Drive` | Completed | 11 |
| `~/Projects` | Completed | 1,912 |
| `~/.golf-model` | Completed; database agent owns payload investigation | 1 |

A broader whole-home attempt also returned 311,087 paths before its 60-second limit. Photos/Photo Booth libraries and Trash returned permission errors. Dependency trees, Git object directories, application bundles, caches, secret-named files and chat-history stores assigned to the Cursor agent were excluded from payload collection. The direct Desktop listing had no obvious golf-named project; its recursively unavailable directories remain an access limit.

`/Volumes` contains only Macintosh HD and ChatGPT Installer; no additional external disk was mounted. `tmutil listlocalsnapshots /` returned no snapshots. A golf-specific Trash inventory could not proceed because macOS denied directory access; no Trash or Time Machine restore was attempted.

One inventory error records a derived `server-worker-runtime.sqlite` working path disappearing while the parallel database agent compressed its own new copy. It is not recorded as an original-source loss.

## iCloud retrieval and storage

Many old Documents originals have macOS `dataless` flags and zero allocated blocks. Blind reads can block. The collector records those metadata paths and does not copy empty bytes as recovered files.

The targeted request batch addressed **93 original cards, provenance files, the snapshot, track record and ZIP, totaling 1,064,784 logical bytes**. Ninety `brctl download <exact-file-path>` requests returned exit zero; three were already available at request time. Exit zero means a request was accepted, not that retrieval succeeded. Final manifest matching confirms verified byte copies for **14 of those 93 exact source paths** (including three already available at request time); **79 target source paths were not byte-captured**. Independently preserved archive copies retain separate provenance and are not counted as hydration of those loose originals. Four additional 45,991-byte `.firecrawl/live-refresh-snapshot*.json` files were requested individually. A supported Foundation `FileManager.startDownloadingUbiquitousItem(at:)` request for the April 6 Masters original also returned success.

No whole Documents tree, whole output tree or research archive was requested for hydration. When disk space became critical, no new bulk retrieval was started. Only exact small original-file requests were allowed to finish. The remaining roughly 40 GB of logical old-project metadata was not blindly materialized.

The large filename working lists created by this audit were compressed and hash-verified before removing only their own raw working copies, reclaiming 105.8 MB. Existing history and archives were preserved.


## Late cloud rescue after native Finder download succeeded

Native Finder successfully retrieved the old Documents main database; that database rescue is documented separately by the database investigation. A final targeted card rescue then used **one `brctl download` batch for only the 79 exact source paths still uncaptured**, totaling 902,815 logical bytes. Its 120-second request/residency window finished in **118.022 seconds**, copying 20 newly available original paths into a new immutable generation. No directory or research download was requested by that batch.

The parent subsequently used native Finder Download on **only two previously verified small folders**: `~/Documents/golf-model/output/archive` (34 regular files, 373,310 bytes) and `output/md cards` (41 regular files, 447,697 bytes), with no subdirectories. A separate **90-second metadata/resident-copy follow-up** checked their 75 known paths plus the earlier exact targets; the union was 91 paths / 997,985 known bytes, below the 1.5 MiB limit. It completed in **88.049 seconds**, capturing 79 currently available paths, including 73 of the 75 folder originals.

Combining the initial verified copies and both late generations, **all 93 of the original targeted source paths now have verified byte copies; none remain uncaptured in that target list. All 75 native-folder originals are preserved.** Two Players files were no longer available during the last pass but had already been copied during the first late batch; they are therefore preserved, not missing. This does not establish that all cloud history or every possible prediction has been recovered. The previously listed research placeholders and bounded traversal limits remain separate gaps.

Stable additive generations:

| Generation | Markdown references / hashes | JSON references / hashes |
|---|---:|---:|
| `2026-10-15-late-cloud-rescue` | 18 / 15 | 2 / 1 |
| `2026-10-15-late-cloud-native-rescue` | 90 / 59 | 27 / 14 |

Nested original `md cards.zip` members retain independent wrapper provenance; the original ZIP bytes are also preserved by SHA-256 under `containers/`. Every copied logical payload and ZIP container hash verifies. There were no read or validation errors. Free space after the final pass was 5.89 GB, above the 1 GiB reserve. Earlier corpus manifests, source files and historical archives were not modified.

These two late generations add **18 distinct Markdown hashes** beyond `archive-pass-009` plus `structured-pass-006`; the JSON hashes already had independent preserved copies. New exact card versions include Truist May 4/5; Players March 9/14/15; Valero March 30/April 1; Houston March 23/24; Valspar March 17; Arnold Palmer March 4/April 5; Masters April 8; Cognizant shadow/methodology variants; a Players methodology version; and the May 11 EV audit. Card, sandbox, methodology and retrospective/audit contexts remain distinct, and byte differences are not counted as independent wagers.

Final target status and full new-hash list: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-late-cloud-native-rescue/final-original-target-status.json`. Final validation and manifest hashes: `combined-late-validation.json` in the same folder. Source manifests in **both** late generations are stable inputs for the final archive/browser rebuild.

## Executed resident Markdown content search outside golf-named paths

A subsequent bounded read-only content pass closed the earlier filename-only coverage gap for the retained broader listings. This pass is separate from the original 25,767-entry golf-path metadata inventory.

Inputs were `/tmp/golf-local-history-all-paths.json.gz` (259,803 paths) and `2026-10-15-local-discovery/listed-paths.json.gz` (266,108 paths). Their union contained **267,699 paths**, including **16,987 Markdown candidates**. Input-file hashes and the exact executed counts are retained in `2026-10-15-broad-markdown-discovery/resident-content-scan-report.json`.

The pass completed in **5.184 seconds**, read **1,053 resident Markdown files / 10,212,607 bytes**, and recorded **1,010 negative content reads**. It skipped **11,750 dataless files without reading**, **1,541 files over 2 MiB**, and **2,642 excluded paths**. One listed supporting file had disappeared before metadata inspection. No hydration was requested, no original was changed, and 2.03 GB remained free after the pass.

| Home root | Resident files read | Negative content reads | Positive files copied | Dataless files skipped |
|---|---:|---:|---:|---:|
| Documents | 62 | 59 | 3 | 9,966 |
| Downloads | 135 | 124 | 11 | 0 |
| Projects | 630 | 630 | 0 | 0 |
| iCloud Drive | 12 | 12 | 0 | 1,778 |
| websites | 214 | 185 | 29 | 0 |
| Desktop | 0 | 0 | 0 | 6 |

Matches required golf-specific context plus a forecast heading/table or the collector's content hint. Generic ranking tables from unrelated subjects were read as negatives and not copied. Only resident regular non-symlink `.md` / `.markdown` files no larger than 2 MiB were eligible. Dependencies, caches, secret paths, chat stores assigned to other agents and this recovery's own output folders were excluded.

The new additive corpus is `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-broad-markdown-discovery/`: **43 source references / 40 distinct hashes**, all logical gzip payload hashes verified. Five source paths were outside the filename hints. Seven hashes were absent from `archive-pass-008`:

| New payload | Source-written generation | Classification | SHA-256 prefix |
|---|---|---|---|
| `Downloads/houston full card.md` and `(1).md` | 2026-03-25 11:59 | Original card candidate; publication unverified | `b3227736b81c` |
| `Downloads/houston roundcard.md` and `(1).md` | 2026-03-25 11:57 | Original card candidate; publication unverified | `33756cf438b8` |
| `Downloads/texas_childrens_houston_open_20260323.md` | 2026-03-23 12:51 | Original card candidate; publication unverified | `bce2649c48ee` |
| `Downloads/the_players_championship_20260310.md` and `(1).md` | 2026-03-10 14:26 | Original card candidate; publication unverified | `3894945dd305` |
| `Downloads/valero_texas_open_20260331.md` | 2026-03-31 12:21 | Explicit sandbox strategy card | `a618a60dda62` |
| `Downloads/valspar_championship_20260316 run 1.md` | 2026-03-16 13:52 | Original card candidate; publication unverified | `0e2dad5638c9` |
| `Downloads/cursor_last_week_s_picks_evaluation.md` | Exported 2026-05-11; no forecast generation asserted | Retrospective Truist evaluation conversation | `6b3dcf961013` |

These contain 352 additional parser observations: 292 from five non-sandbox card payloads, 47 from the sandbox card and 13 from the retrospective conversation. They are not 352 independent bets. Full hashes, source paths, classifications and per-kind counts are in `new-payload-validation.json`; every source reference remains in `sources.jsonl`.

The retained input listings were previously bounded/partial, so this is proof of an executed content search over those listed paths, not a claim of exhaustive traversal of every home-directory path. Scanner: `scripts/discover_resident_markdown_history.py` (Ruff passes).

A final **55-second bounded home Markdown filename listing** (56.640 seconds including subprocess shutdown) returned 58,501 paths before timing out, with Photos/Photo Booth/Trash permission errors recorded. Its previously unlisted 45,953 paths then received a separate resident-only content pass in **78.603 seconds**: 45,745 reads / 407,328,777 bytes, 45,742 automatic negatives, 205 excluded paths and three oversized files. All three automatic candidate matches were manually rejected: two were this recovery's own newly generated audits and one was an unrelated esports plan referencing golf-model. Their hashes and rejection reasons remain in `2026-10-15-broad-markdown-home-discovery/screened-out-sources.jsonl`; its `sources.jsonl` is empty and must not add forecast rows. No new prediction source was found in this home delta.

The two content passes and bounded home listing took **140.427 seconds total**, within the 180-second scanning/read budget. They performed 46,798 resident content reads; after the three manual rejections, 46,755 read files were negative or ineligible and 43 qualified source paths were copied. This adds explicit negative coverage for HIVE, HIVE-dt-thursday, HIVE-polymarket, MMA/esports/F1 project roots and listed hidden-tool Markdown. Complete per-root counts are retained in the separate reports. The original 43-reference corpus remains stable.


## Bounded resident JSON content pass

An additional resident-only JSON pass reused the same retained full filename lists, with no new filesystem listing or cloud retrieval. It admitted regular non-symlink JSON files no larger than 2 MiB in Documents, Downloads, Desktop and Projects; secrets, dependencies, assigned chat stores and recovery outputs were excluded. Matches required golf-specific context, event/tournament evidence and player forecast arrays with probability, odds, composite or EV fields. The copy cap was 20 MiB and the disk reserve was 1 GiB.

The pass stopped at its hard budget after **88.002 seconds** (90-second budget with finalization reserve). It considered **141,603 of 242,583 listed candidates**, read **48,520 resident JSON files / 34,254,695 bytes**, recorded **48,520 negative content reads**, skipped **91,102 dataless files without reading**, **1,545 oversized files** and **436 excluded paths**. There were no read errors, qualifying matches or copied payloads; **5.10 GB remained free**.

Exact root coverage: Desktop contributed five candidates (four dataless, one excluded). All 48,520 resident content reads were in Documents. Alphabetical traversal consumed the budget before reaching Downloads or Projects; **those two roots are not covered by this JSON content pass**. Unsupported schemas, root arrays without event context and content that lacks the required golf evidence may also remain unindexed.

Evidence: `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-broad-json-discovery/resident-json-scan-report.json`; its `structured_sources.jsonl` is empty. Scanner: `scripts/discover_resident_json_history.py`. No original source was modified, no hydration was requested, and no immutable archive generation was rewritten.

A separately authorized **30-second priority follow-up** filtered the already-listed paths to Downloads and Projects *before* iteration. It completed **all 1,341 candidates in 23.699 seconds**: Downloads had 88 resident reads / 88 negatives (91 candidates; two oversized and one excluded); Projects had 1,245 reads / 1,245 negatives (1,250 candidates; five oversized). There were no qualifying matches, copied bytes or errors. Its report and empty structured manifest are in `/Users/aidannugent/websites/golf-model-preservation/2026-10-15-priority-json-discovery/`. Free space afterward was 4.94 GB.

Together the two JSON passes performed **49,853 negative resident content reads** across 142,944 considered listed candidates. The bounded first pass left **99,639 listed Documents JSON candidates unprocessed**; Downloads and Projects no longer have an unprocessed candidate gap within these retained listings. File-size, residency, excluded-path and unsupported-schema limits still apply. No additional filesystem listing or cloud request was made for either JSON pass.

A final additive suffix pass closed that listed-candidate gap. The two original
input-list hashes were verified, their sorted considered prefix reconstructed,
and only the remaining 99,639 Documents paths were written to a small derived
gzip list. `2026-10-16-remaining-json-discovery/resident-json-scan-report.json`
records completion in 52.363 seconds: **71,069 resident reads, all negative**,
28,569 dataless skips, one excluded path, zero errors and zero copied payloads.
Its output manifests are empty; they must not create forecast rows.

Across the three JSON passes, all **242,583 candidates in the retained listings**
were considered: 120,922 resident negatives, 119,671 dataless skips, 1,552 oversized
skips and 438 excluded paths. These reconcile exactly to the candidate total.
No new listing or hydration was requested. Original listing incompleteness and
unsupported/root-array schema limits still apply; this closes a known bounded
search gap rather than proving every file on the Mac was read.


## Subsequent native Finder checks

After the shell-based collection, Finder successfully downloaded the exact old
`Documents/golf-model/data/golf.db` file. The database agent preserved it in
`data/research/database-history-20261016-finder/8340ec5baf39d26c/`; see the database
audit for hashes and February–March coverage. Finder displayed full iCloud
storage, but the inbound download nevertheless completed. This supersedes the
earlier main-database availability limit, not the other pending-file counts.

A later exact-file follow-up also recovered all five remaining known small
databases: the 454,656-byte worktree database and four study databases, 10,207,232
bytes combined. Their full snapshots, source metadata, hashes and table inventory
are preserved under `2026-10-16-small-db-cloud-rescue`. The worktree has no history
rows. The study sources retain 5,754 trial observations in two nonempty generations
and two empty generations; these do not increase issued prediction counts. All
five preserved snapshots pass integrity and decompression checks. Other cloud
research placeholders remain separate unresolved leads. See the database audit.

The shell's Trash permission error remains recorded. A separate normal Finder
search scoped to Trash for `golf` returned zero items. No item was restored,
removed or emptied, and no full recursive Trash content inventory is claimed.

## Reproduction and verification

Collector: `scripts/discover_local_history.py`.

A fixture exercise verified nested ZIPs, Markdown-gzip and JSON preservation, malicious `../../` member names, duplicate content with distinct provenance, repeated collection, logical SHA-256 checks and unchanged original archive bytes. Ruff passes for the collector. The real corpus validation checks every distinct decompressed payload against its source hash; the two original archive hashes still match their prior preserved manifests.

Examples:

```bash
python3 scripts/discover_local_history.py \
  --archive /absolute/path/research-cards-output.tar.gz \
  --output /absolute/path/new-discovery

python3 scripts/discover_local_history.py \
  --paths-json /absolute/path/listed-paths.json.gz \
  --inventory-only \
  --output /absolute/path/new-discovery
```

Recovery and forecast parsing are separate. This inventory retains every recovered original source and its context; it does not create stakes, outcomes, closing quotes, model identities or publication times that the source did not supply.
