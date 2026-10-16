# Full SQL forensic salvage — October 16, 2026

An additional bounded recovery preserved **all SQL emitted by SQLite** from the
already isolated September 13 disposable copy. The earlier attempt retained only
six core tables and discarded other SQL. This pass recovered substantial dense
forecast and full-snapshot observations. Every observation remains
`salvaged_unverified`; no recovered SQL was executed or imported, no model was
changed, and no original or prior recovery artifact was deleted.

## Source and exact output

Source: `/Users/aidannugent/websites/golf-model-reconciliation/2026-10-14/wal-probe/golf.db.malformed_20260913_180810`.
It is the previously extracted 6,835,355,648-byte disposable copy, linked to the
verified original quarantine archive. Its empty WAL was checked. Source SHA-256
before and after was
`2f514028ff41c6ac631129698017c8de56eb494a00ca35425dc4f1346c6f3ef4`;
size and modification time were unchanged.

The installed Mac SQLite 3.51.0 passed the direct `sqlite_dbpage` probe. The VPS
SQLite 3.45.1 did not. No new binary was compiled or installed.

The command used `-readonly -batch`, a `mode=ro&immutable=1` URI and default
`.recover`, including freelist recovery. SQLite exited **0** before the 600-second
deadline. Raw capture was capped at 512 MiB compressed with a 1 GiB disk reserve;
neither limit was reached. Capture plus source-hash and gzip-readback verification
completed in 551.62 seconds. No archive was extracted during this pass.

Private output directory:
`/Users/aidannugent/websites/golf-model-preservation/2026-10-16-full-forensic-sql/`.

- `full-recovery.sql.gz`: 308,767,964 bytes; gzip SHA-256
  `1eae27ade5731a47182ef03c662789a943ef21af8a58b84eb3208a6e921b5b0e`.
- Decompressed SQL: 6,427,749,807 bytes; SHA-256
  `88bf04c8484d53d2f9091d596cefac21be2433c36a538eb7acf19d996344ee70`.
- `manifest.json`: source/command/bounds, complete emitted INSERT counts,
  unchanged-source proof and successful independent gzip readback.
- `scalar-event-coverage.json`: bounded event/time-prefix analysis, 97 source-local
  table/event/section groups and 97 samples with exact raw SQL offsets and hashes.
- `finalization.json` and `event-leads.json`: the optional large payload sample
  file was intentionally withheld to retain the disk reserve. An exclusive small
  placeholder prevented the controller from replacing it after raw SQL and the
  manifest were already verified. The resulting Python exclusive-write refusal
  did not affect the successful SQLite exit or either verified artifact.

The initial optional sample accumulator used too much memory. The reusable
collector now bounds those samples at 8 MiB and avoids further payload parsing
after that budget; the original full SQL bytes are preserved independently.

## Recovered forecast observations

| Table | Emitted INSERTs |
| --- | ---: |
| Dense market predictions | 2,502,646 |
| Full live snapshot sections | 4,251 |
| Picks | 2,343 |
| Prediction log | 989 |
| Pick outcomes / results | 2,097 / 2,499 |
| Tournaments | 42 |
| Model weights / track configs | 9,230 / 2 |
| Metrics / CSV import records | 320,877 / 57,228 |
| Historical rounds | 34,392 |

The six core tables reproduce the prior 7,970 recovered observations. Schemas for
runs, pre-teeoff fields and other tables are preserved, but no recovered INSERTs
for those tables were observed. This does not establish empty original tables.

Dense forecasts cover U.S. Open (1,565,937 observations), Travelers (935,818) and
RBC Canadian Open (891), with generated timestamps June 14–21. They include live,
upcoming, lab and legacy lanes. Repeated quotes and refreshed forecasts are
observations, not independent bets or execution receipts.

The 4,251 snapshot rows span June 14–September 3. Meaningful named labels include
Canadian Open, U.S. Open, Travelers, John Deere, Scottish Open, Open Championship,
ISCO, 3M, Rocket, Wyndham, St. Jude, BMW, TOUR Championship and Biltmore. Generic
Current/Next Event records and later-date Masters/Heritage/Zurich fixtures or
stale labels are retained separately in the scalar groups. Missing source event
IDs and disagreements remain explicit.

No recovered dense/snapshot event label or generated-time prefix establishes a
PGA Championship/Aronimink forecast or a May publication. The PGA calendar row
was recorded June 15 and remains restoration metadata. Dates appearing inside
large payloads can describe historical inputs; they are not publication proof.

The scalar analysis completed in **64.65 seconds**, within its 120-second limit,
and matched every emitted INSERT count from the independent quote-aware capture.
It parsed only known pre-payload columns, not millions of full tuples or JSON
payloads. No SQLite database was reconstructed. Twenty-four recovery/parser/
prefix tests and targeted Ruff passed.

SQLite explicitly treats recovery as salvage: values can be altered, deleted
content can reappear, and table assignment may be wrong. Corroboration is required
before any new observation enters performance, CLV qualification or model
promotion. See [SQLite recovery documentation](https://www.sqlite.org/recovery.html).
