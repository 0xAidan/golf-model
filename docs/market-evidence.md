# Market evidence without changing the models

`GET /api/market-evidence?lane=dashboard&season=2026` reports the evidence present in the current SQLite database. `lane` accepts `dashboard`, `lab`, or `all`; omitting `season` includes all recorded seasons. This is an additive reporting surface, not a learning or promotion command.

## Safety boundary

`src/market_evidence.py` imports no database initialization helpers or prediction modules. It opens SQLite with `mode=ro`, enables `PRAGMA query_only`, and uses a single read transaction. It never calls `ensure_initialized`, a migration, a prediction, grading, retuning, calibration, or registry function. Active WAL is honored; `immutable=1` is deliberately not used. SQLite may maintain its normal shared-memory read locks while reading a live WAL database; the reporting code does not write database or WAL content.

Paths use `GOLF_DB_PATH`, then `GOLF_DATA_DIR/golf.db`, then this checkout's `data/golf.db`. A missing database is not created. A missing schema is `unavailable`; a valid query with no records is `empty`. Do not start the main application against an archive merely to inspect it: its existing database initialization has a separate migration path.

## What the response means

- `coverage` reports the actual dates, event counts, raw pick/outcome counts, duplicate records, conflicts, and missing market identity in this database. It does not assert that a full season survived or is complete.
- `markets` separates known 72-hole matchups, 18-hole matchups, groups/three-ball and other/unspecified markets. A legacy `matchup` with no duration is unspecified.
- `lanes` separates dashboard, lab, and other sources. The default view contains dashboard records only.
- `net_units` uses stored canonical profit; no payout is reconstructed from hit rate or odds. A partial sum is explicitly marked by `profit_missing_records` and `profit_coverage_complete`.
- `flat_unit_roi_pct` is only available when every eligible settled record has known profit and positive recorded stake. It normalizes each stored profit by its stored stake. Voids are excluded. The result is a model/paper record because actual wager placement is unknown.
- Wins, losses, pushes, voids, ungraded and unknown outcomes remain distinct. A zero hit with missing profit is unknown. A void cannot become a loss. Calibration uses valid probabilities and unambiguous binary win/loss outcomes only.
- Exact duplicate evidence counts once. The identity includes event, season, tournament ID, source/model, market, round/group, players, and book. Different prices/probabilities/outcomes for the same identity are conflicts, excluded from performance. Multiple outcomes for one pick are also excluded. Missing round/group identity preserves each original pick separately and is disclosed.
- `low_sample` means fewer than 30 binary records or five settled events. Passing that descriptive threshold does not establish statistical significance or a durable edge.
- Historical matchup odds and research-line presence are database-wide availability checks, not claimed as live results. CLV is withheld: existing stores require identity, timing, convention and repeat-record checks before they can support that metric.

## Append-only report artifacts

Use a verified consistent backup for archive analysis. Do not copy a live SQLite main file alone while WAL is active.

```bash
python3 -m src.market_evidence \
  --db /path/to/consistent-copy.db \
  --out /path/to/new-report-2026-10-13.json \
  --lane dashboard --season 2026
```

The output is created exclusively and an existing output is never overwritten. The database path is always read-only, including when explicitly pointed at the current database.

## Existing learning mechanisms are outside this boundary

The existing `post_tournament_learn` function writes course weights, calls `retune(dry_run=False)`, replaces calibration curves, and can append matchup calibration coefficients. Its consumers can change future predictions. Dynamic blend and adaptation also affect probabilities, selection or stakes. The research cycle can update the research registry when `AUTORESEARCH_AUTO_APPLY` is enabled; separate promotion endpoints can write the live registry. None of these flows is called or modified by this report.

The next safe learning layer is append-only evaluation: timestamped market/book/round coverage, frozen decision-time prices and model configuration hashes, authoritative settlement references, and event-separated chronological validation. Proposed selection or timing improvements should be evaluated on later held-out events and presented for review; they must not silently rewrite probabilities, model state or past results.

## Focused verification

`python3 -m pytest tests/test_market_evidence.py -q` verifies byte-preserved input, unchanged schema, no creation of a missing database, committed WAL visibility, event/season/round and lane isolation, unknown/push/void handling, calibration boundaries, duplicate conflicts, and exclusive report creation. Its FastAPI test mounts only this router, bypassing main application startup and migrations.

## Processing limits

Each report permits up to 10,000 joined pick/outcome rows, 8MiB of total text/blob payload, a 64KiB per-connection SQLite value/encoded-row limit, and eight seconds across SQL plus Python processing. These limits apply before filtering and deduplication so duplicated outcomes cannot evade the budget. A limit failure returns `state=unavailable` and `report_limit_exceeded`, with an empty report and no partial metrics. It does not rewrite source data or silently drop records to fit. Large recovered histories need a separately designed indexed reporting store before these bounds are increased.

The focused report/HTTP checks include oversized inputs, deadline expiry during projection/aggregation, no partial publication, source-hash preservation on refusal, and unchanged normal metrics. The complete report for the preserved current database was also compared before/after in dashboard, lab and all lanes; only generation timestamps differ.
