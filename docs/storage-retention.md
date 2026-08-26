# Storage and retention policy

$0-cost hygiene for `data/golf.db` on the VPS.

## Keep forever (model + operator history)

Classification: **KEEP_FOREVER**

- `picks`, `pick_outcomes`, `pick_ledger`, `grading_audit_log`, `results`, `prediction_log`
- `tournaments`, `runs`, `weight_sets`, `calibration_curve`, `market_performance`
- `rounds`, `metrics` (backfill / rolling — large but required)

`pick_ledger` keeps **displayed / frozen / graded / recovered / canonical** rows forever. Tick-level `lifecycle=generated` rows are **not** KEEP_FOREVER — live refresh already stores those ticks in `market_prediction_rows`, and `INSERT OR IGNORE` cannot dedupe them because `pick_key` includes `snapshot_id`. Cleanup runs `prune_generated_pick_ledger()` (generated lifecycle only). File size does not drop until a guarded VACUUM.

## Archive then prune (append-heavy ticks)

Classification: **ARCHIVE_THEN_PRUNE**

- `live_snapshot_history`
- `market_prediction_rows`

**Default:** retain **210 days** (`SNAPSHOT_HISTORY_RETAIN_DAYS`).

**Prune gate:** when `SNAPSHOT_PRUNE_REQUIRE_ARCHIVE=1` (default), prune refuses to DELETE until a verified cold archive exists for the same cutoff window under `data/exports/`.

Export tick rows before prune:

```bash
# Export rows older than the retention window
python3 scripts/export_tournament_archive.py --tick-before-days 210

# Or export one tournament's core history tables
python3 scripts/export_tournament_archive.py --tournament-id 12
```

**Prune:** live-refresh worker (every 6h), weekly systemd timer, or manual:

```bash
# Full cycle: export → verify manifest → prune (recommended)
python3 scripts/run_retention_cycle.py

# Dry-run only (no export/delete)
python3 scripts/run_retention_cycle.py --dry-run

# Legacy prune script
SNAPSHOT_HISTORY_RETAIN_DAYS=210 python3 scripts/prune_snapshot_history.py --vacuum
```

To bypass the archive gate (emergency only):

```bash
SNAPSHOT_PRUNE_REQUIRE_ARCHIVE=0 SNAPSHOT_HISTORY_RETAIN_DAYS=210 python3 scripts/prune_snapshot_history.py
```

## Slim tick logging

Classification: **SLIM** — `market_prediction_rows`

Set `MARKET_PREDICTION_SLIM_PAYLOAD=1` to store full `payload_json` only once per `snapshot_id` (subsequent rows in the same snapshot get `{}`). Normalized columns remain queryable; existing rows with full JSON are unchanged.

## Investigate (no automatic prune)

Classification: **INVESTIGATE**

- `ai_decisions`, `intel_events`, `shadow_event_simulations`, `challenger_predictions`

## Reclaim disk after prune

SQLite does not shrink the file until **VACUUM**. Use disk-guarded reclaim (refuses when free space is insufficient):

```python
from src import db
db.reclaim_database_disk()  # VACUUM on small DBs; VACUUM INTO swap on DBs >= 5 GB
```

Or via prune script during a maintenance window:

```bash
python3 scripts/prune_snapshot_history.py --vacuum
```

Also check `data/golf.db-wal` — large WAL → run vacuum/checkpoint during maintenance window.

## Backups

Nightly backups live in `backups/` (`python3 -m src.backup --keep 4 --compress`). Backup refuses when free disk is below `db_size + 512 MiB`. Integrity is written to a `.integrity.json` sidecar at backup time so later checks do not gunzip a 13 GB file on a tight disk. Data-health (`GET /api/data-health`) exposes free disk, backup age, whether the next backup can fit, and integrity status.

Storage color on `/system`:

- **Red:** disk hard floor, latest backup missing or older than 36h, real integrity failure, WAL huge, or the next backup cannot fit.
- **Yellow:** database is large, disk below 10 GB free, integrity check skipped for space, prune deleted 0 rows, or other warnings.
- **Not red by itself:** file larger than 10 GB, or an approximate table taking more than 50% of measured pages.

On `/system`, **Run cleanup** calls `POST /api/ops/jobs/cleanup` (sidecar sweep → generated-ledger prune → WAL checkpoint → retention cycle → guarded reclaim).

## Audit

```bash
python3 scripts/audit_data_coverage.py --year 2026 --db-path /opt/golf-model/data/golf.db \
  --output output/data_health_2026.json
```

Dashboard: **Research → Diagnostics → Data health** or `GET /api/data-health`.

`data/exports/` and `backups/` are gitignored.
