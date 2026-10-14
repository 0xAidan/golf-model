# Server and historical-data audit — October 13, 2026

## Scope and protection boundary

Production observations were collected read-only over the existing `golf-vps`
SSH alias, from approximately **2026-10-13 23:58 UTC / October 13 19:58 EDT**
through **2026-10-14 00:03:07 UTC / October 13 20:03:07 EDT**. The last timestamp
is the server's exact UTC time immediately before the storage inventory.

No production services, schedules, files, models, settings, or database records
were changed during this audit. Active workers continued their ordinary writes,
so current-database counts below are sampled observations, not one transactional
snapshot. No provider/model routines were imported or run against production.
The current database was queried with SQLite URI `mode=ro` and `query_only=ON`.
Quarantines were queried with `mode=ro&immutable=1`; those observations exclude
the accompanying WAL and do not certify whole-file integrity.

The user's boundaries are to preserve models and every historical dataset and
result. UI, reporting, delivery, and operational safety can be improved. Nothing
in this report authorizes deleting quarantines or rewriting historical grades.

## Production inventory

- Application directory: `/opt/golf-model`.
- Git commit: `cb86850`, dated August 31, 2026, merge of PR 270.
- Tracked files were clean. Untracked backups, quarantines, reports, course data,
  and temporary artifacts exist and were retained.
- FastAPI serves the built React SPA. Caddy fronts the site.
- `golf-dashboard.service`, `golf-agent.service`, and `golf-live-refresh.service`
  were active. All three run as root.
- `golf-backup.service`, `golf-grading-sweep.service`, and
  `golf-disk-watchdog.service` were failed.
- Timers: daily backup at 03:00 UTC, storage janitor at 02:00 UTC, weekly retention
  Sunday 04:00 UTC, grading every 30 minutes, integrity every 15 minutes, and
  live-refresh watchdog every five minutes.
- Dashboard/agent had been running since October 1; live-refresh started
  October 13 at 23:38:49 UTC / 19:38:49 EDT.
- FastAPI listens on `0.0.0.0:8000`. External reachability/firewall policy was
  not tested; binding alone does not prove public exposure.

## Backup and storage risk

The 75GB root filesystem was 94% used, with approximately 4.7GB available.
`data/` used approximately 38GB. The current database was approximately 464MiB,
with a approximately 465MiB WAL. Most database storage is preserved quarantines.

The nightly backup fails before copying because available space is below
`DISK_FREE_MB_HARD=5120`. The October 13 failure reported **4803MiB available**.
The latest retained backup is
`backups/golf_model_20261004_030000.db.gz`, approximately 47MiB compressed.
Its integrity sidecar records `quick_check=ok`, 453,230,592 uncompressed bytes,
and verification at October 4 03:00:02 UTC / October 3 23:00:02 EDT. This is
nine days older than the audit. An October 3 backup also remains.

The scheduled current-database integrity probe returned `quick_check=ok` at
**October 13 23:59:35 UTC / 19:59:35 EDT** and did not restore anything.
Structural integrity does not establish historical completeness.

Read-only storage inventory at **October 14 00:03:07 UTC / October 13 20:03:07 EDT**:

| Path | Allocated size (`du -sk`) |
| --- | ---: |
| `data/exports` | 387,684 KiB / 378.60 MiB |
| `output/audits` | 160 KiB |
| `output/research` | 1,586,828 KiB / 1.51 GiB |

| Quarantined main database | Exact bytes |
| --- | ---: |
| `golf.db.malformed_20260902_021214` | 7,973,240,832 |
| `golf.db.malformed_20260903_020827` | 7,973,801,984 |
| `golf.db.malformed_20260904_021537` | 7,973,621,760 |
| `golf.db.malformed_20260913_020514` | 7,978,950,656 |
| `golf.db.malformed_20260913_180810` | 6,835,355,648 |
| `golf.db.malformed_20260913_182329` | 1,470,464 |
| **Main-file total** | **38,736,441,344 / 36.08 GiB** |

Retain their WAL and SHM files too: another 245,984 bytes at observation time.
Compression ratio has not been measured and must not be assumed for capacity.

## Missing active history and surviving recovery sources

| Table/evidence | Current DB sample | Sept 13 02:05 quarantine |
| --- | ---: | ---: |
| `picks` | 564 | 2,355 |
| `pick_outcomes` | 514 | 2,351 |
| `pick_ledger` | 2,872 | 6,376 |
| `results` | 323 | 2,499 |
| `rounds` | 35,471 | 34,392 |
| `research_backtest_lines` | 0 | 1,019 |
| `historical_matchup_odds` | 0 | 0 |
| `track_configs` | 0 | 2 |

Current picks begin September 14 and cover only five events. The older
quarantine contains picks created June 14 through September 13, including
restored earlier-season evidence. The September 2, 3, 4, and September 13 02:05
quarantines all returned core-table counts. The two later September 13 copies
raised `database disk image is malformed` on core-table reads.

Current round coverage was 18,078 PGA rounds across 47 events in 2025, 14,509 PGA
rounds across 39 events in 2026, and 2,884 LIV rounds across 13 events in 2026.
Current `historical_odds` contains 96,261 rows and `historical_predictions`
19,950 rows. Current `market_prediction_rows` had 719,408 rows at the sample.
These surviving sources do not replace contemporaneous prediction/pick history.

The tournament exports are another independent recovery source. Manifest counts
include U.S. Open 254 picks/254 outcomes, Travelers 172/148, Open Championship
298/298, and 3M 361/361. Some exports contain more picks than the quarantine.
Many tick archives have zero rows; their existence alone is not recovery proof.
Export checksums and actual rows still need independent local verification.

**Numeric tournament IDs have been reused across database generations.** Old
ID 1 is RBC Canadian Open; current ID 1 is Biltmore Championship Asheville.
Recovery must preserve source identity and map by verified tour/event/year,
then player/market/round/book/pick provenance. Never merge by numeric IDs alone.
Preserve disagreements rather than overwriting a source's historical answer.
Current model/track registry absence also requires investigation; do not
automatically reinstate old configuration while models are frozen.

## Grading failure and logging defect

The failing event is **528, Butterfield Bermuda Championship**, with stored
start date **October 22, 2026** and no end date. An early verbal audit note
mistakenly inferred Puerto Rico; direct database inspection corrected it.

`src/event_pick_freeze.py::_completed_events_for_sweep` added every tournament
with positive-EV picks without requiring completion evidence. Upcoming Bermuda
picks therefore entered a completed-event sweep. The results endpoint returned
HTTP 400. The event loop had no per-event exception handling, so one failure
aborted all later alphabetically sorted events and reconciliation.

Provider exceptions include authenticated request URLs. Existing logs exposed
the API key in those exception messages; this report intentionally contains no
credentials or copied authenticated URLs.

The source-only repair prepared with this audit requires final-result evidence
or a past historical end date for pick-derived candidates. Completed round
dates and explicit provider completion statuses remain valid. A date equal to
today, without final status, does not prove that today's play has ended. Each
failed event becomes an error result and subsequent events continue; logged and
returned errors retain exception type without raw provider text or traceback.
The report's existing `year`, `events_processed`, `results`, and `ok` fields
remain intact. No production grading or model pipeline was run for verification.

## Market evidence: provisional, not verified actual betting P&L

The following aggregates came from the September 13 02:05 quarantine, filtering
to `model_variant=baseline`, `source=cockpit`, and a nonempty, non-void grading
authority. They are **stored nominal-stake results**, not independently verified
executed wagers, clean holdout evaluation, or a complete-season report.

| Matchup market | Outcomes | Events | Stored nominal profit |
| --- | ---: | ---: | ---: |
| Tournament H2H | 261 | 20 | +13.344 units |
| Round H2H | 582 | 11 | -3.811 units |
| Unspecified duration | 106 | 3 | +8.221 units |

Recovered records, 28 locked `trackRecord_json` outcomes, other computed grades,
market identity, ties, quoted-price timing, and duplicates require reconciliation.
No inspected evidence establishes successful group/three-ball betting. Absence
of that proof is not evidence that those markets never succeeded.

The earlier May 31 audit already distinguishes positive placement backtest ROI
from negative small-sample live value performance and records missing matchup
odds and grading problems. Do not present its backtest returns as live profit.

CLV duplication is material: 50,670 current rows represent only 128 distinct
event/player/market/book combinations over two events; the older quarantine has
347,184 rows but only 114 combinations over four events. These combination
counts still are not certified independent bets. Raw CLV rows cannot be used as
sample size. Current `weight_sets` had 727 rows and `bankroll` 728; the older
quarantine had 12,681 and 12,126 respectively. Repeated settlement/learning
effects need a separate idempotency audit before any self-improvement claims.

## Current delivery state

The snapshot generated October 13 at 23:38:50 UTC / 19:38:50 EDT reported
`off_window`, no live event, and upcoming Bermuda with no posted tournament
H2H edges. Diagnostics also reported 24 raw `three_ball` rows, but availability
does not establish display eligibility or historical profitability. Worker
heartbeat at October 14 00:01:19 UTC / October 13 20:01:19 EDT was running/idle.

## Nondestructive preservation and next steps

1. Capture a consistent current SQLite backup using a read-only source connection
   and SQLite's backup API, then verify the received local file. An in-memory
   destination can stream gzip through SSH without creating a server-side copy;
   at audit time approximately 3.7GB RAM was available for the 464MiB database.
   Do not copy the live main database alone while WAL writers are active.
2. Stream static quarantine main/WAL/SHM files, the entire exports tree, and audit
   artifacts into a local raw archive. For example, from a sufficiently large
   local destination, the following reads production and writes only locally:

   ```sh
   ssh -o BatchMode=yes golf-vps \
     'cd /opt/golf-model && tar -czf - data/golf.db.malformed_* data/exports output/audits' \
     > golf-history-raw-20261013.tar.gz
   ```

   Record every source file's size/hash and verify against extracted local
   copies. Exports may change under existing workers; detect changes with
   before/after manifests and repeat changed artifacts. A tar archive alone is
   not a consistent live-database backup. Preserve research output separately.
3. Salvage into a separate local evidence database. Do not import the application
   or call `init_db` on recovered files: existing migration/deduplication behavior
   needs review and may delete evidence. Preserve raw source artifacts even if
   logical recovery succeeds.
4. Repair completion eligibility and event isolation, then separately review
   grading idempotency and learning side effects. Test only temporary fixtures.
5. Restore backup capacity using added storage or verified off-server retention.
   Do not run `src.backup` as a harmless export: it rotates backups before copying
   and invokes storage cleanup. Do not delete historical quarantines to make room.
6. Build the UI around a unified matchup board and explicit evidence/freshness
   states. Keep market reporting and future shadow research separate from
   production probability/model changes.

## Local regression verification

On the isolated local checkout, the grading safety tests plus existing grading,
inventory, acquisition, and delayed-event tests passed:

```sh
python3 -m pytest tests/test_grading_sweep_safety.py \
  tests/test_event_grading_readiness.py tests/test_placeholder_inventory.py \
  tests/test_event_pick_freeze_acquisition.py tests/test_delayed_event_grading.py \
  -q --tb=short
```

Result: **32 passed in 2.18s**. All database writes were to temporary test
fixtures. External provider requests and grading execution were stubbed in the
new sweep regressions. This is source verification, not deployment or restoration.
