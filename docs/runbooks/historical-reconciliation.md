# Historical reconciliation: immutable sources, separate reporting

The October 14, 2026 season report is a **season-to-date evidence inventory**.
It is not a complete placed-bet ledger, and no selection policy has been shown
to improve future returns. Models, source databases, historical outcomes,
calibration and weights are outside this procedure.

## Preserved evidence

Original artifacts remain in the private sibling directory
`golf-model-preservation/2026-10-13/`. SHA-256 values were checked against the
initial preservation manifest before publishing this report:

| Artifact | SHA-256 |
| --- | --- |
| current.sqlite | de473c5d331e34623c8f9c24353cf745a6d42bf824ad91392451ff040a7a9540 |
| exports-and-audits.tar.gz | a620f3d9e1f552aa8c5b5df63a6f8624e9fcb549c5498b8a6d877c895d93772b |
| research-cards-output.tar.gz | 2c896d93418e81289e8653b7136dc34acb3c72a32b9d6a001ca2aaa37b52dbcc |
| history-evidence-vault.20261014T003000Z.jsonl.gz | 4291222388e42905f12ca818fbc4fdb559a8e5da83eaa6b2bbb6937b0a898ee5 |
| quarantines-with-sidecars.tar.gz | d40c7d6ddc00f78fc8d4aebbee1a36e80458b7bcbc101c7d6bc65186258ad3e9 |

The 22-generation logical vault contains 2,757,406 rows. Its complete ledger
scan covered 2,712,717 ledger rows, including repeated refresh ticks. These
are observations, not wagers. The compact core retains 44,689 original rows
across tournaments, picks, outcomes, results and prediction logs. Two omitted
quarantines were preserved with their WAL/SHM files and inspected separately,
bringing the original source-generation inventory to 24.

All six quarantine base files and twelve sidecars are retained with member
hashes. Four small WALs have valid frame checksums but incompatible base headers
and committed page counts. None was replayed. The two omitted databases fail
ordinary SQLite reads; this means unreadable, not empty.

## Bounded salvage

`scripts/recover_history_core.py` runs SQLite's `.recover --ignore-freelist`
against an exclusively owned disposable copy using `mode=ro&immutable=1`.
The original WAL for this truncated copy is empty. It **never executes recovered
SQL**: a literal-only parser keeps INSERTs for six whitelisted core tables and
discards unknown tables, triggers and statements. Deadlines, output limits,
disk reserve, source hashes, row hashes and exclusive publication are enforced.

The successful attempt recovered 7,970 rows: 42 tournaments, 2,343 picks,
2,097 outcomes, 2,499 results and 989 prediction-log rows. No ledger rows were
recovered. All rows and table closures are `salvaged_unverified`, with SQL-line
hashes and `primary_performance_eligible: false`. The preceding readonly-open
failure is retained separately. The success artifact hash is
`c9f3059f11986d71e4c21ceb7f7d3ad13438f933ee5641072ef5663f00b3000a`.

Exactly 4,059 recovered payloads match a healthy `(table, row_sha256)`; the
remaining 3,911 are uncorroborated. Neither category adds another return to
primary totals. The private derived SQLite retains every salvage envelope.

## Identity, deduplication and settlement

1. Join tournaments and outcomes through **source-generation-local foreign
   keys**. A database's integer event or pick ID is never a global identity.
2. Match tournament season, preserved provider ID (including leading zeros),
   and explicit name aliases to the official calendar. All 42 real local event
   identities match. Fixture events are retained as observations but excluded
   from performance. The calendar contains 48 events, 41 elapsed by October 14.
3. Group repeated saved quotes across archive generations, retaining every
   original row and source link. Different markets, forecast values, configs
   or settlements within a saved lineage become conflicts. Equivalent numeric
   and textual American prices have one economic identity.
4. Identical economic quotes with different recorded timestamps are ambiguous
   repetitions. They are not assumed to be separate wagers or assigned an
   invented earlier decision time. Both originals survive; returns are excluded.
5. Missing 18-hole round identity, missing group participants, unidentified
   contracts and missing quotes are incomplete. Round numbers are not guessed
   from dates or a heading saying "per-round".
6. Contradictory winner/loser labels, voids with nonzero profit, changed outcomes
   or quote disagreements are withheld. No favorable version is selected and
   no settlement is rewritten. Zero return is not automatically labelled push.
7. Preserve saved profit and stake. Paper ROI uses their ratio only for elapsed,
   consistent, complete, settled contracts. Missing, ungraded, void, incomplete
   and conflicting evidence stays visible. Issue counts can overlap.

Current result: 12,824 raw pick observations, 16 fixture observations excluded,
3,026 reporting groups, 144 conflicting groups and 1,388 incomplete groups
outside the conflict bucket. There are 1,372 groups lacking round identity.
The 226 archived card observations collapse to 218 distinct file/line records;
they contribute coverage, not invented stakes or settlements. No actual group
selections were found in this preserved corpus.

The complete calendar shows missing events. Twenty-five elapsed events have
core picks; one future event also has saved picks. A 26-event source count is
not proof of full-season completeness. Results with high paper ROI over few
events must not be advertised as a validated edge.

## Selection research without model changes

`src/selection_evidence.py` implements frozen, outcome-blind selection rules:
all eligible quotes; positive stored EV; positive EV capped at five per event;
and one quote per contract with at most two player exposures per event.

Inputs must be scoped to one **market, lane and model variant**. Mixed scopes
return no comparisons. Configuration hashes remain visible as strata. Calendar
dates are not tee times: same-day, post-event, unknown and restoration timestamps
are excluded. Candidate restore/backfill provenance is an exclusion signal,
never an invented pick foreign key. Source-local ledger IDs are not pick IDs.

Validation splits whole events chronologically, purges overlapping boundary
events, and requires eight earlier events, five later events and thirty later
decisions per rule before uncertainty estimates. Bootstrap resamples events,
not independent-looking quotes from the same tournament. Original stakes and
normalized one-unit research returns are kept separate.

The 520 eligible quote groups do **not** form one valid learning cohort. Every
properly separated scope is currently insufficient. Historical outcomes have
already been inspected, so later events are retrospective validation, not an
untouched holdout. No policy is promoted, no live rank is changed and no model
is fitted. This gate prevents duplicate archives, ambiguous rounds or pooled
model versions from manufacturing an apparent selection improvement.

For future evidence, freeze contract identity, round/group membership, quote
time, publication time, book, price, model/config hash and selection policy
**before** outcomes; append settlements later with original result provenance.
Evaluate this same protocol on unseen whole events before considering a policy
promotion. The current reconciliation does not silently schedule collection,
regrade the database or enable the application's existing retuning routines.

## Reproduce into a new generation

Use only `scripts/reconcile_history.py`; do not start `app.py`, import `src.db`,
run restore scripts, regrade or backfill. The CLI refuses an existing output
directory, validates stream closures/counts/hashes, hashes inputs before and
after, and writes a separate SQLite database with original envelopes and links.

```sh
python3 scripts/reconcile_history.py \
  --vault /private/reconciliation/identity/compact-core-vault.jsonl.gz \
  --vault /private/reconciliation/wal-probe/omitted-quarantine-core.20261014.jsonl.gz \
  --vault /private/reconciliation/wal-probe/salvaged-quarantine-core.20261014-immutable.jsonl.gz \
  --calendar config/reporting/season_2026_calendar.json \
  --cards /private/reconciliation/identity/card-matchup-candidates.jsonl \
  --lineage /private/reconciliation/ledger/lineage-evidence.jsonl.gz \
  --artifact /private/preservation/quarantines-with-sidecars.tar.gz \
  --as-of 2026-10-14 \
  --output /private/reconciliation/new-generation
```

Pass each original artifact again with `--artifact` to bind all hashes. The
private output is `reconciliation.sqlite`, `decisions.jsonl`, full scoped
`selection-evaluation.json`, `manifest.json`, and sanitized public JSON/CSV.
Only the sanitized pair belongs under `frontend/public/reports/`; raw sources,
private paths and full database payloads do not belong in the public site.

The checked report is the local `run-005` generation. Tests cover source-local
joins, duplication, conflicts, restoration chronology, missing contracts,
corrupt/truncated vaults, immutable source hashes, salvage isolation, mixed
selection scopes, chronological splits and exclusive output creation.

## Static delivery

The Season record view is the default Results tab. Current store remains at
`/evidence?view=store`. The season component loads only on Results and reads one
precomputed JSON file; it never scans the archive or queries a database in the
request path. Lane, market, calendar and model-version interactions are local.

Add this handler only within the existing golf Caddy host, before its fallback:

```caddyfile
handle /reports/* {
    root * /opt/golf-model/frontend/dist
    header Cache-Control "public, max-age=60"
    file_server
}
```

Use the saved-config/validate/reload and atomic frontend procedure in
`matchup-desk-deployment.md`. No app or model-service restart is needed. Verify
JSON MIME/content, CSV content, snapshot identity and public routes after
publication; a SPA HTML fallback is not a successful report response. Rollback
restores the previous index and saved Caddyfile, retaining fingerprinted assets
and every source/reconciliation generation.
