# Prediction-history preservation release — October 16, 2026

The reviewed preservation and grading changes are installed on the VPS. This is
backend preservation evidence, not a claim of complete historical recovery,
profitable predictions, completed grading reconciliation or a frontend release.

## Protected release

- Source commits: `bcf97a33fb3925b0a0421ee0bfcbe962f2cb6648` and
  `2b6b34b` (grading completion admission).
- Versioned server staging/rollback: `/opt/golf-model-releases/20261016-preservation-bcf97a3/`.
- Installed 20 source files after verifying each live original and staged SHA-256.
  Nineteen preservation targets were adapted to the actual server baseline.
  Three tournament-identity hunks omitted by that adaptation were then restored
  from the reviewed `official_pick_record.py`; its final hash matches the reviewed
  file. The grading sweep is the twentieth target.
- Existing affected timers/processes were quiesced. Dashboard, refresh worker and
  research agent were restored; only previously active permitted timers resumed.
  Installation began 04:21:18.410 UTC and completed 04:22:52.036 UTC.
- Retention, storage-janitor and disk-watchdog timers remain inactive. No database
  restore, bulk regrade, cleanup or model promotion was invoked by deployment.

## Database and model evidence

A standalone read-only SQLite-backup API snapshot, including committed WAL,
passed `quick_check`, `integrity_check` and decompression verification before
installation. Its SQLite SHA-256 is
`4cd7fc7caea6354439ded10f2171575f73463e771a2f95584a1910ff3fbb95b8`;
its gzip SHA-256 is
`ee7c3880565ecec97db786209fe6a0ebb753dc0e3a81a7be0dab1c4b3f248860`.
Both server and off-server copies remain preserved.

The exact server Python source with the staged overlay was started against a
**disposable** snapshot. All 1,194,921 original rows across all 62 existing tables
retained their exact original values after `init_db`; no before-image fallback
was needed for this snapshot. The copy passed `quick_check`. No original database
was initialized by that validation.

All eight pinned incumbent model/configuration source hashes are unchanged.
Captured model-state table contents were identical immediately before and after
service restart. Later normal jobs can still evolve their existing state; the
pinned original comparator remains separately preserved.

Live readback verified all 20 installed hashes and three active application
services. It observed a new pick (578 versus the preinstall snapshot's 577) and
20,427 retained before-image journal rows. This confirms real writes continued
and version retention was exercised; these counts are observations at the check,
not permanent totals or distinct bets.

## Grading and remaining operational limits

The prior provider 400 was for PGA event 528/year 2026, an upcoming Bermuda event;
only its 2025 completion rounds existed. The revised local-source admission check
returned 39 completed-event candidates and excluded 2026 Bermuda. It opened the
live database query-only and did not execute grading. Its standalone provider
schedule lookup lacked the service environment and was unavailable; the local
completion check is not proof of provider schedule or full sweep success.

`/api/ops/health` returned `ok=true` with `summary=grading_discrepancies` after the
restart. Existing discrepancies remain visible and are not relabeled success.
The next normal timer run started at 04:47:34 UTC and completed at 04:47:38 UTC
with `Result=success` and `ExecMainStatus=0`. The full structured result is
retained privately: `ok=true`, 39 admitted events, 36 skipped for no inventory,
three already graded, zero orphan outcomes and zero events with ungraded
positive-EV inventory in that reconciliation. Upcoming event 528 was absent.
No new event was graded by this run. This successful job exit does not resolve every previously
recorded grading discrepancy or establish results for every recovered event.
The disk-watchdog unit points at a missing script and remains disabled. Capacity
was restored by a [verified lossless quarantine representation change](2026-10-16-lossless-quarantine-storage.md),
with all historical bytes retained and a guarded exact-path restore script.

## Validation

- 1,231 backend tests passed for the preservation batch.
- 40 focused grading/freeze tests passed for the dated-admission follow-up.
- Independent review verified the preservation corrections and identified the
  staged grading-identity adaptation before installation.
- Complete clone startup conservation and live hash/readback checks above passed.
- Final combined backend suite: 1,258 tests passed (eight warnings).

Private execution receipts, database snapshots, complete source originals and
clone comparison details are under the matching local reconciliation release
folder and server release folder. They are outside public web assets.
