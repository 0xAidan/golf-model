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
32-task cap. Python bytecode writes are disabled in both script and unit.

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
