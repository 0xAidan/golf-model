# Rankings workspace release — October 16, 2026

The Rankings workspace is published at `https://golf.shermandavison.com/`.
Rankings remain the primary route. Markets, Performance and Models have direct
navigation, and the original model remains accessible through its legacy route.
Recovered history is presented separately from qualifying performance evidence.

Release identity: `rankings-workspace-20261016-23a1c3d`.

## Verified deployment

All 101 release files passed staged SHA-256 verification. The release archive is
1,389,919 bytes with SHA-256
`71baa32a44c257d6cfa19a48e80b1430ba5bb87dd13a64e2334372d80f89d21f`.
The installed index SHA-256 is
`843ec9669165959f7b0b7e9715643e833c39f6b15bbc2701da239e164fadec37`.

The previous complete build and all old fingerprinted chunks remain available
for rollback and already-open browsers. Assets/support files were installed
first and the index was replaced atomically last. No application process restart
or database operation was performed; four observed application PIDs were
unchanged. The versioned release and private install/public-readback receipts
remain under `/opt/golf-frontend/releases/` and the matching local reconciliation
folder.

Public HTTP checks verified 15 route/asset/report responses with status 200 and
exact expected hashes. Actual browser checks covered Rankings, Markets,
Performance, Models and the original-model route. The original route displayed
the preserved 72-player baseline. Public browser evidence is retained in
`.impeccable/review/public-rankings.jpg`.

## Evidence boundaries

- Recovered inventory: 233 complete card versions across 30 source event labels.
  Copies, refreshes and research observations are not independent wagers.
- Performance: a 13-event historical paper cohort, with event-level uncertainty,
  drawdown, calibration and outcome details. It is not verified live profit.
- CLV: zero qualified observations; missing timing evidence remains visible.
- Challenger: the independently replayed multi-season research artifact is
  explicitly labeled research. No live-model promotion occurred.
- Forward challenger rankings require an exact current event/field/snapshot
  match. The published page correctly withheld a report whose snapshot no longer
  matched the latest incumbent capture.
- Market visibility controls organize the browser view. They do not establish
  that market generation or betting execution has been enabled.
- One dated research week does not establish improvement over multiple weeks.

## Local verification

The full frontend suite passed 488 tests across 74 files. Forty-seven focused
report-binding checks, type checking, lint and production build passed after
the final report guard. Seven browser accessibility checks found zero critical
axe violations. The final entry bundle measured 76,234 gzip bytes against a
79,772-byte limit. The focused independent finish review returned ship, and the
design documentation was derived from the final rendered build. Full combined
backend verification passed 1,258 tests with eight warnings.

See the separate [local verification record](2026-10-16-frontend-verification.md)
for the earlier pre-publication report states and test configuration.
