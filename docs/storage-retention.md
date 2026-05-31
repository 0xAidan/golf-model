# Storage and retention policy

$0-cost hygiene for `data/golf.db` on the VPS.

## Keep forever (model + operator history)

- `picks`, `pick_outcomes`, `results`, `prediction_log`
- `tournaments`, `runs`, `weight_sets`, `calibration_curve`, `market_performance`
- `rounds`, `metrics` (backfill / rolling — large but required)

## May prune (append-heavy)

- `live_snapshot_history`
- `market_prediction_rows`

**Default:** retain **210 days** (`SNAPSHOT_HISTORY_RETAIN_DAYS`).  
**Prune:** live-refresh worker (every 6h) or:

```bash
SNAPSHOT_HISTORY_RETAIN_DAYS=210 python3 scripts/prune_snapshot_history.py --vacuum
```

## Reclaim disk after prune

SQLite does not shrink the file until **VACUUM**:

```bash
# Only when enough free disk (same caution as deploy backup)
python3 scripts/prune_snapshot_history.py --vacuum
```

Also check `data/golf.db-wal` — large WAL → run vacuum/checkpoint during maintenance window.

## Audit

```bash
python3 scripts/audit_data_coverage.py --year 2026 --db-path /opt/golf-model/data/golf.db \
  --output output/data_health_2026.json
```

Dashboard: **Research → Diagnostics → Data health** or `GET /api/data-health`.

## Cold archive (optional)

Export old ticks before delete:

```bash
python3 scripts/export_tournament_archive.py --tournament-id 12 --output-dir data/exports/
```

`data/exports/` is gitignored.
