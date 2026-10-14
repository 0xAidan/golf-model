# Matchup desk deployment without application or pipeline restarts

This release has two independent parts: the compiled frontend and a small
read-only report service. Do not run the repository's normal deployment script,
pull the full branch onto production, replace backend source, initialize a
database, or restart the dashboard, research agent, live-refresh worker, or
grading services as part of this rollout.

The existing FastAPI process reads `frontend/dist/index.html` on each request and
serves its assets from disk. The new service opens SQLite with `mode=ro` and
`query_only=ON`, and reads the worker's JSON snapshot. It imports no application,
database initializer, model, or backtester. It loads no `.env` file.

## Prerequisites

- A verified current database backup and preserved historical recovery sources.
- A tested frontend build from this checkout.
- Python 3.11+ at `/usr/bin/python3` on the server; no third-party dependencies
  are needed by the new service.
- Loopback port 8011 available.
- Existing database/WAL/SHM files and snapshot readable by the service's dynamic
  user. Do not change production ownership or modes simply to bypass a failure;
  inspect access and choose an explicit read-only access solution if required.
- Approximately 512MiB maximum memory budget for the new service, plus room for
  the staged and saved frontend builds. Do not remove historical data for space.

## Isolated service package

Create a new versioned directory such as
`/opt/golf-evidence/releases/20261013-desk-v1/` containing **only**:

```text
serve_matchup_reports.py       # from scripts/serve_matchup_reports.py
snapshot_backup.py            # include when the backup drop-in below is enabled
src/
  __init__.py                 # empty
  market_evidence.py
  operator_read_model.py
  operator_contract.py
```

Copy the three modules from this checkout's `src/`. Do not copy the application's
complete `src/`, `app.py`, its `.env`, or database files. Directories must be
traversable and these nonsecret code files readable by the dynamic service user
(normally root-owned directories 0755 and code files 0644).

Preserve the prior target of `/opt/golf-evidence/current`, if present. Atomically
point `current` to the tested release directory. Install
`deploy/systemd/golf-evidence.service` as
`/etc/systemd/system/golf-evidence.service`, preserving any previous unit first.

The unit explicitly sets:

```text
GOLF_DB_PATH=/opt/golf-model/data/golf.db
GOLF_SNAPSHOT_PATH=/opt/golf-model/data/live_refresh_snapshot.json
GOLF_SNAPSHOT_STALE_SECONDS=3720
```

The 3,720-second freshness window is the observed one-hour recompute cadence plus
120 seconds. It is an explicit deployment assumption, not dynamically inferred.
Recheck this setting if the worker cadence changes. Reads use the snapshot's
`generated_at`, not filesystem modification time. Missing/invalid timestamps and
failed event eligibility remain unavailable. Stale rows retain the original
contract's `state=stale`; clients must honor that state when presenting actions.

The process always binds **127.0.0.1**, never a public interface. It permits at
most four concurrent report computations and reads snapshots up to 16MiB. The
unit adds `DynamicUser`, a read-only filesystem, read-only data/code paths,
loopback-only network access, no elevated privileges, a 512MiB memory cap, and a
32-task cap. Each evidence computation also enforces 10,000 joined source rows,
8MiB aggregate text/blob payload, a 64KiB SQLite value/encoded-row cap, and an
eight-second deadline spanning SQL and Python work. Limits apply before lane or
season filtering and before deduplication. Exceeding any limit returns unavailable
with no partial metrics; it never silently truncates the history. Python bytecode
writes are disabled in both script and unit.

Validate and start **only this new service**:

```sh
systemd-analyze verify /etc/systemd/system/golf-evidence.service
systemctl daemon-reload
systemctl enable --now golf-evidence.service
curl --fail http://127.0.0.1:8011/health
curl --fail 'http://127.0.0.1:8011/api/desk/board?track=champion&mode=upcoming'
curl --fail 'http://127.0.0.1:8011/api/market-evidence?lane=dashboard'
```

If updating an existing instance, restart only `golf-evidence.service` after
switching its isolated release. Do not restart existing application services.
`/health` confirms process liveness, not database completeness or board freshness.
Inspect the report and board states as well as HTTP status.

## HTTP contract

| Route | Parameters | Behavior |
| --- | --- | --- |
| `/health` | None | Process liveness and read-only service identity |
| `/api/market-evidence` | `lane=dashboard\|lab\|all`; optional `season=2000..2100` | Existing stored results only; defaults to dashboard/all seasons |
| `/api/desk/board` | `track=champion\|challenger`; `mode=live\|upcoming`; optional `event_id` | Pure snapshot projection; defaults to champion/upcoming |

GET and HEAD are supported. Unknown routes return 404; mutations return 405;
invalid, duplicate, or unsupported query parameters return 400. `mode=past` is
explicitly unsupported on the new desk route. Source unavailability is returned
as an explicit unavailable report/board state. Unexpected failures and exhausted
report slots return 503 without raw exception text or source paths. Responses
use `Cache-Control: no-store`; there are no raw query-string access logs.

The service does not expose `/api/operator/board`; leave the existing backend's
past-event and other operator routes untouched. The new desk frontend must use
`/api/desk/board` for live/upcoming reads. Challenger data is never filled from
Champion. Event mismatch/failed field verification withholds rows using the
existing pure read-model contract. This service does not interrogate or control
the worker's live runtime; it reports the existing snapshot and its provenance.

## Caddy routing

Save the exact current Caddyfile. In the existing `golf.shermandavison.com` block,
add these exact handlers before its general `handle /api/*` block:

```caddyfile
encode zstd gzip

handle /api/market-evidence {
    reverse_proxy 127.0.0.1:8011
}

handle /api/desk/board {
    reverse_proxy 127.0.0.1:8011
}
```

Keep the existing method restrictions, CORS headers, legacy API route, static
fallback, redirects, and all unrelated virtual hosts. The service sets no-store
headers itself. Do not expose its health endpoint publicly unless needed.
Compression applies within the golf host and retains the API's no-store policy.

```sh
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy
curl --fail 'https://golf.shermandavison.com/api/market-evidence?lane=dashboard'
curl --fail 'https://golf.shermandavison.com/api/desk/board?track=champion&mode=upcoming'
```

Validate the full returned JSON: an HTML response, unavailable database, missing
lane, or mismatched event must not be reported as a successful data rollout.

## Publish the frontend last

1. Save the complete current `/opt/golf-model/frontend/dist` in a separate
   rollback directory. Preserve its index and release metadata.
2. Upload the new verified build to a staging directory. Check that every local
   asset reference in its `index.html` exists.
3. Copy all assets and supporting files into the live `dist` first, excluding
   `index.html`. **Retain old fingerprinted asset files; never use `--delete`.**
4. Write the staged `index.html` to a temporary file inside the live `dist` and
   atomically rename it to `index.html` last. Preserve release metadata for
   accurate version reporting and rollback.
5. Verify public HTML, referenced JS/CSS/fonts, the new desk, and both new JSON
   routes in a browser. Confirm the existing backend and worker process IDs did
   not change.

No dashboard restart is required or permitted by this procedure. A fresh UI
build alone does not prove model performance, full historical recovery, or the
resolution of existing background-job failures.

## Rollback

The frontend also serves `/shared-card#card=…` through the existing SPA fallback.
The fragment contains a bounded, unverified saved selection snapshot, decoded
only in the browser. It needs no new API, database table or server write. Sharing
does not establish placed bets or current prices. Never log the fragment in
frontend telemetry; the Sentry scrubber removes it before sending events.

Restore the saved frontend index/root files atomically, retaining both releases'
fingerprinted assets. Restore the saved Caddy configuration, validate, and reload
Caddy. Stop only the new report service if removing it, or switch its `current`
link back and restart only that service. Restore corresponding frontend release
metadata so version reporting matches the visible build. No database rollback,
migration, cleanup, grading, or model action belongs in this rollback.

## Existing automatic learning is a separate unresolved concern

Production grading already invokes `post_tournament_learn`, including
`retune(dry_run=False)` and calibration updates. The 30-minute grading timer can
therefore change stored model state independently of this UI rollout. Repairing
the sweep can expand that behavior to additional events. Do not deploy the
grading safety patch or silently stop/change existing model jobs under this
frontend/report-only procedure. Disclose and resolve that policy separately.

## Local checks

```sh
python3 -m pytest tests/test_matchup_report_sidecar.py tests/test_operator_read_model.py \
  tests/test_market_evidence.py -q --tb=short
python3 -m ruff check scripts/serve_matchup_reports.py tests/test_matchup_report_sidecar.py
```

Tests exercise real loopback HTTP requests, source-file hash preservation,
missing source handling, query validation, freshness and eligibility, no
Challenger fallback, and an isolated import check against application/database/
model modules. They use temporary fixtures only; no production process is
started by these checks.

## Restore the existing daily backup safely

The production backup unit was inspected read-only. It is a oneshot with one
`ExecStart` that sources the application's `.env` and invokes `python -m
src.backup --keep ... --compress`. There were no ExecStartPre/ExecStartPost/
ExecStopPost hooks, OnSuccess/OnFailure units, or existing drop-ins. Its daily
timer runs at **03:00 UTC** with `Persistent=true`. The existing implementation
imports application database helpers, rotates previous backups, and invokes
cleanup. Do not use it for the protected-history preservation work.

`scripts/snapshot_backup.py` is a separate stdlib-only replacement. It opens the
existing source using SQLite URI `mode=ro` plus `query_only=ON`; its backup API
includes committed WAL data. It does not import `src.db`, application startup,
models, migrations, cleanup, restoration, or notification code.

The script creates a uniquely owned temporary directory inside the backup
destination. It copies into a private SQLite file, changes only that private
copy to standalone journal mode, runs both `quick_check` and `integrity_check`,
streams gzip, then verifies decompressed bytes against the raw SHA-256. Only
verified artifacts are published. Output names are unique
`golf_model_<UTC timestamp with microseconds>_<random suffix>.db.gz` files with
compatible `.db.gz.integrity.json` sidecars. The manifest includes both hashes,
sizes, timestamps, integrity results, and read-only provenance. Existing backup
discovery and integrity-sidecar readers recognize these names and fields.
The staged gzip and manifest are explicitly mode `0600` before publication;
the service drop-in also sets `UMask=0077`.

Publication uses same-filesystem hard links that fail rather than replace an
existing filename. Existing backups, historical files, and the source are never
deleted or rotated. Cleanup removes only this invocation's private temporary
directory. If manifest publication fails after a verified gzip is published,
that gzip remains available and the job reports failure; it is not deleted to
hide the incomplete publication. Ordinary process failures clean private temps;
an uncatchable process/host crash may leave its hidden temporary directory for
later explicit inspection. There is no sweeping cleanup of other files.

The initial disk check requires both the **5,120MiB initial hard floor** and
enough space for the raw SQLite copy plus worst-case gzip expansion plus a
**512MiB reserve**. It measures SQLite's logical page count, including committed
WAL content, rather than just the main file's apparent size. Remaining footprint,
reserve, and a **600-second deadline** are checked throughout copy/compression;
integrity queries have an interruption deadline. An unavailable/corrupt source,
insufficient disk, or expired deadline fails visibly without pruning anything.
After the first successful server backup, `systemctl show` confirmed
`TimeoutStartUSec=infinity`; systemd therefore does not impose an earlier
90-second startup cutoff. `TimeoutStopUSec=1min 30s` applies to stopping the
service, not to normal backup runtime. No timeout override is needed for this
unit. Recheck `TimeoutStartUSec` after future service-definition changes; if it
falls below the script's deadline, use `TimeoutStartSec=660` so the script has
time to report failure and clean its private temporary files.

To deploy after reviewing and testing:

1. Copy only `scripts/snapshot_backup.py` to
   `/opt/golf-evidence/current/snapshot_backup.py`, retaining it in every future
   isolated release while the drop-in is enabled. It needs no additional modules.
2. Preserve the current service definition and any existing drop-ins. Recheck
   hooks before applying; the no-hook observation above is not a permanent fact.
3. Install
   `deploy/systemd/golf-backup.service.d/readonly-snapshot.conf` at
   `/etc/systemd/system/golf-backup.service.d/readonly-snapshot.conf`.
   This resets/replaces **only ExecStart** and adds the restrictive umask. It leaves the existing timer,
   application services, and environment settings untouched; the replacement
   script neither sources `.env` itself nor uses provider credentials.
4. Validate and reload systemd definitions. Confirm the resulting ExecStart points
   to the isolated script and that no inherited pre/post hooks were introduced.
5. Start only `golf-backup.service` for a monitored first backup. Do not run a
   restore, regrade events, restart models, or activate any new scheduler.

```sh
systemd-analyze verify /etc/systemd/system/golf-backup.service
systemctl daemon-reload
systemctl show golf-backup.service -p ExecStart -p ExecStartPre -p ExecStartPost -p ExecStopPost
systemctl start golf-backup.service
systemctl show golf-backup.service -p Result -p ExecMainStatus
```

Verify the new gzip and manifest exist, their SHA-256 values match, and the unit
reports success. Keep the prior off-server and on-server preserved snapshots.
Do not invoke `src.backup` just to validate the replacement. Confirm that the
daily timer still has its original 03:00 UTC schedule. No new alerts/messages or
notification automation are introduced by this drop-in.

Append-only retention consumes additional disk each day. It deliberately fails
at the budget boundary rather than destroying older backups. Additional storage
or separately reviewed off-server archival/retention is still needed for
sustained operation on this small volume. Restoring one successful backup job
does not resolve historical completeness or the separate automatic-learning
concern.

Local backup tests:

```sh
python3 -m pytest tests/test_snapshot_backup.py -q --tb=short
python3 -m ruff check scripts/snapshot_backup.py tests/test_snapshot_backup.py
```

The fixtures cover committed WAL recovery, unchanged source hashes, compatible
manifests, repeated append-only backups, publication collisions, missing/corrupt
sources, restrictive artifact modes even under a permissive umask, disk/time
refusals, private failure cleanup, and preserving a verified
gzip when sidecar publication fails. No application initializer runs.
