# Storage recovery runbook

Use this when disk space is low, the database is oversized, backups look wrong, or you need to restore from a nightly backup.

**Production host:** `root@204.168.147.6` · **Repo path:** `/opt/golf-model` · **Public site:** https://golf.ancc.blog/

## When to use this runbook

| Symptom | Likely cause | Start at |
|---|---|---|
| Site slow or 500 errors; `df -h` shows &lt;10 GB free | Disk full | [Scenario 1](#scenario-1-disk-full-site-degraded) |
| `/system` Storage panel red; `GET /api/data-health` status `red` | DB &gt;10 GB or prune never ran | [Scenario 1](#scenario-1-disk-full-site-degraded) |
| `PRAGMA quick_check` fails or DB missing | Corruption / accidental delete | [Scenario 2](#scenario-2-db-corrupted-or-lost) |
| Need old tick-level matchup rows pruned from DB | Cold archive under `data/exports/` | [Scenario 3](#scenario-3-restore-archived-tick-history-for-analysis) |

**Call for help** (stop and ask before proceeding) if:

- `data/golf.db` is missing and there is **no** recent backup under `backups/`
- `quick_check` fails on the **latest** backup too
- You are unsure whether a file is the live database vs a temp copy

**Never delete:** `data/golf.db`, `data/golf.db-wal`, `data/golf.db-shm` unless you are performing a deliberate restore from backup.

---

## Quick health check (read-only)

Run on the VPS at `/opt/golf-model`:

```bash
df -h /
du -sh data backups output data/exports
ls -lah data/golf.db*
ls -lah backups/ | tail -20
curl -s https://golf.ancc.blog/api/data-health | python3 -m json.tool | head -50
curl -s https://golf.ancc.blog/api/ops/health | python3 -m json.tool | grep -E '"summary"|"disk"'
```

**Healthy:** &gt;15 GB disk free; latest backup &lt;26 h old with `integrity.ok: true`; data-health not `red`.

---

## Scenario 1: Disk full, site degraded

### Option A — UI available (preferred)

1. Open https://golf.ancc.blog/system
2. Storage panel → **Run cleanup**
3. Wait for the cleanup job to finish (poll `GET /api/ops/jobs/latest/cleanup` or refresh the Jobs panel)
4. Confirm disk free increased and data-health improves

The cleanup job runs, in order: backup sidecar sweep → remove stale `.pre_reclaim` / `.pre_restore` copies (only when live DB passes `quick_check`) → WAL checkpoint → retention cycle (archive then prune) → guarded `reclaim_database_disk`.

### Option B — UI down or SSH required

```bash
cd /opt/golf-model
source venv/bin/activate

# 1. Remove junk only — NOT the live database
rm -f backups/*.db-shm backups/*.db-wal backups/*.db-journal
rm -f data/golf.db.pre_reclaim data/golf.db.pre_restore data/golf.db.vacuum_into

# 2. Confirm at least one good backup remains
python3 -m src.backup --list
python3 - <<'PY'
from src.backup import list_backups, verify_backup_integrity
backups = list_backups()
if not backups:
    raise SystemExit("ERROR: no backups found — stop and get help")
latest = backups[0]["path"]
result = verify_backup_integrity(latest)
print("Latest:", latest)
print("Integrity:", result)
if not result.get("ok"):
    raise SystemExit("ERROR: latest backup failed quick_check — stop and get help")
PY

# 3. Run full cleanup (same as API job)
python3 - <<'PY'
from src.ops_jobs import run_storage_cleanup
import json
print(json.dumps(run_storage_cleanup(), indent=2, default=str))
PY

# 4. Restart services
systemctl restart golf-dashboard golf-live-refresh golf-agent
```

**Expected:** `run_storage_cleanup` returns `"ok": true` or `"skipped"` on reclaim when disk is still too tight (re-run after sidecar/temp cleanup frees space).

---

## Scenario 2: DB corrupted or lost

**Prerequisite:** A backup that passes `quick_check` (see list step above).

```bash
cd /opt/golf-model
source venv/bin/activate

# Pick latest good backup path from --list output
BACKUP="backups/golf_model_YYYYMMDD_HHMMSS.db"   # or .db.gz

python3 - <<'PY'
from src.backup import verify_backup_integrity
import os, sys
path = os.environ.get("BACKUP")
if not path:
    sys.exit("Set BACKUP env to the backup file path")
result = verify_backup_integrity(path)
print(result)
sys.exit(0 if result.get("ok") else 1)
PY

# Restore (writes data/golf.db.pre_restore first)
BACKUP="$BACKUP" python3 -m src.backup --restore "$BACKUP"

systemctl restart golf-dashboard golf-live-refresh

# Re-grade events completed after the backup timestamp
python3 scripts/ensure_completed_event_grading.py --year 2026
python3 scripts/grading_reconciliation.py
```

**Expected:** Site loads; reconciliation exits 0 or lists events that need manual grade.

---

## Scenario 3: Restore archived tick history for analysis

Pruned tick rows live under `data/exports/tick_archive_*/` as JSONL + `manifest.json`. **KEEP_FOREVER** tables (`picks`, `pick_outcomes`, `results`, etc.) were never pruned — season P&amp;L stays in the live DB.

```bash
ls data/exports/tick_archive_*/manifest.json
# Inspect manifest: tables, row counts, sha256 checksums
zcat data/exports/research_archive/*.gz 2>/dev/null | head   # if research rotation ran
```

Gunzip JSONL files offline; query with `jq`, Python, or import into a scratch SQLite DB. Do not replace `data/golf.db` with archive exports.

---

## Scheduled maintenance (reference)

| Job | Schedule | Command |
|---|---|---|
| Nightly backup | 03:00 UTC (`golf-backup.timer`) | `python3 -m src.backup --keep 4` |
| Weekly retention | `golf-retention.timer` | `scripts/run_retention_cycle.py --vacuum` |
| On-demand cleanup | `/system` or API | `POST /api/ops/jobs/cleanup` |

Env defaults (see `docs/storage-retention.md`): `DISK_FREE_MB_WARN=10240`, `DISK_FREE_MB_HARD=5120`, `SNAPSHOT_HISTORY_RETAIN_DAYS=210`, `MARKET_PREDICTION_SLIM_PAYLOAD=1`.

---

## Rehearsal log

| Date | Operator | Action | Result | Notes |
|---|---|---|---|---|
| _pending_ | — | Scratch-path restore drill | — | Record timing + `quick_check` output after first VPS rehearsal |

---

## Related docs

- [Storage and retention policy](../storage-retention.md)
- [Live refresh incident runbook](./live-refresh-incident.md)
- [Rollback drill](./rollback-drill.md)
