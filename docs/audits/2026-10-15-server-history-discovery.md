# Server prediction-source discovery — October 15, 2026

The owner explicitly requested a broad search for every historical prediction,
including local files, Cursor and the VPS. This collection extends the earlier
reconciliation; the ten-event dashboard/baseline/72-hole research subset is not
the total history of the project.

## Read-only search and preservation

The existing `golf-vps` SSH alias was used. No application service, database,
model, archive or original card was changed. The stdlib collector
`scripts/export_server_prediction_cards.py` was streamed through SSH stdin; it
did not install files or write on the VPS. It searched `/opt`, the former
`/root/golf-model` and `/root/opt/golf-model` locations, and the golf Superpowers
worktree root. The two former repository paths are now absent.

The initial server output scan found 1,450 Markdown files in the main checkout,
including 180 archive files and 1,232 research files. A wider search also found
old `/opt/golf-model*` checkouts and `.worktrees/1b-worker-runtime`, whose output
directory contains additional generated artifacts. That worktree has a resident
33,980,416-byte database and is included in the database recovery investigation.
Small fixture/worktree databases are not presumed to be production history.

The collector retained all regular Markdown files and JSON provenance/snapshots
under golf output, local-recovery and research-archive locations. Nested ZIP
Markdown entries were read without extracting them on the server. Resource
forks, symlinks, software dependencies and unrelated Cursor/plugin files were
excluded. The 32 MiB member budget omitted **zero** selected files.

Private preservation generation:

`/Users/aidannugent/websites/golf-model-preservation/2026-10-15-server-discovery/`

- `cards-and-provenance.tar.gz`: complete streamed collection.
- `extracted/sources.jsonl`: 3,526 original-source references.
- `extracted/corpus/`: 2,919 distinct content hashes, including Markdown and JSON.
- `extracted/collection-summary.json`: counts and explicit omission list.

Every archive member was checked to be regular and inside the exclusive local
destination. Every source reference was checked against the SHA-256 of its
collected content. There are 1,928 Markdown references; duplicates retain all
original paths. Exact duplicate bytes count once in the derived corpus, while
different forecast versions remain separate.

The main database, six malformed generations with WAL/SHM files, and retained
backups remain in place. Most raw quarantine bytes and the earlier logical core
vault already have separately verified preservation artifacts from October 13.
This extension does not extract, repair or overwrite those originals. Current
and newly discovered database sources are being preserved separately through
consistent snapshots and source-local logical extraction.

## Interpretation

The Markdown index preserves rankings, priced predictions, unpriced matchup
projections, AI recommendations and qualitative watch/fade observations. It
distinguishes original cards, methodology restatements, retrospective reports,
research documents and unresolved event labels. `Current Event`, `Future Event`
and `Test Event` do not become real tournament identities automatically.

These are source observations, not independent wagers. A card's generated label
is preserved verbatim and is not independent proof of pre-event publication.
No settlement, wager placement, stake, ROI or CLV is inferred during discovery.
Unparsed forecast-like lines remain in an explicit review file rather than
silently disappearing.

Completeness remains open while local iCloud placeholders, Cursor evidence,
newly discovered databases and all duplicate/conflicting forecast generations
are reconciled. No claim that every historical prediction has been found is
made by this inventory.
