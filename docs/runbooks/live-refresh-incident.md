# Live refresh / split-brain incident runbook

Use this when production shows stale data, empty boards with no explanation, or manual refresh fails.

## Symptoms

- Dashboard shows an old tournament (e.g. Heritage) while the current week is a different event
- `GET /api/live-refresh/snapshot` returns very high `age_seconds`
- `golf-dashboard.service` restart counter (`NRestarts`) climbs rapidly
- Manual refresh returns generic errors or never updates the board
- `GET /api/ops/health` shows `summary: snapshot_stale` or `worker_heartbeat_stale`
- Heartbeat file shows `phase: shadow_mc` (or other phase) with age > 15 minutes while `running: true`

## Stuck worker (shadow_mc / long recompute)

If the worker process is alive but snapshot age keeps climbing:

1. Check heartbeat phase:
   ```bash
   cat /opt/golf-model/data/live_refresh_heartbeat.json | python3 -m json.tool
   journalctl -u golf-live-refresh -n 120 --no-pager | rg -i "shadow|timeout|error"
   ```
2. Restart the worker (releases cycle lock):
   ```bash
   systemctl restart golf-live-refresh
   ```
3. Confirm recovery:
   ```bash
   curl -s http://127.0.0.1:8000/api/live-refresh/snapshot | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('ok'), d.get('age_seconds'))"
   ```

**Prevention (post 2026-06 fix):** snapshot is published **before** shadow MC / SQLite tail work; worker heartbeat refreshes during long phases; `golf-live-refresh-watchdog.timer` restarts hung workers every 5 minutes.

## Diagnosis order

1. **Port owner**
   ```bash
   ss -tlnp 'sport = :8000'
   /opt/golf-model/venv/bin/python /opt/golf-model/scripts/port_8000_audit.py --json
   ```
   For each PID: `readlink -f /proc/<pid>/cwd` and `tr '\0' ' ' < /proc/<pid>/cmdline`

2. **Systemd**
   ```bash
   systemctl status golf-dashboard golf-live-refresh
   journalctl -u golf-dashboard -n 80 --no-pager
   journalctl -u golf-live-refresh -n 80 --no-pager
   ```

3. **Snapshot paths**
   ```bash
   ls -l /opt/golf-model/data/live_refresh_snapshot.json
   ls -l /root/golf-model/data/live_refresh_snapshot.json 2>/dev/null || true
   ```

4. **API identity**
   ```bash
   curl -s http://127.0.0.1:8000/api/ops/health | python3 -m json.tool
   curl -s https://golf.ancc.blog/api/ops/health | python3 -m json.tool
   ```

5. **Compare local vs public** — both must report the same `identity.app_root` and `identity.snapshot_path`.

## Recovery (safe)

**Never restart `/root/golf-model` as a rollback.** That restores stale split-brain data.

1. Re-resolve port 8000 PID immediately before any kill (avoid PID reuse).
2. Stop **only** a verified wrong-root dashboard listener (cwd ≠ `/opt/golf-model`, not the live-refresh worker):
   ```bash
   kill -TERM <orphan_pid>
   sleep 3
   ```
3. Reset and start the canonical service:
   ```bash
   systemctl reset-failed golf-dashboard
   systemctl start golf-dashboard
   ```
4. Verify:
   ```bash
   readlink -f /proc/$(ss -tlnp 'sport = :8000' | rg -o 'pid=\\d+' | head -1 | cut -d= -f2)/cwd
   curl -s http://127.0.0.1:8000/api/live-refresh/snapshot | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('ok'), d.get('age_seconds'), (d.get('snapshot') or {}).get('upcoming_tournament',{}).get('event_name'))"
   /opt/golf-model/scripts/ops_verify_production.sh
   ```

## Rollback

Prefer a **known-good `/opt/golf-model` deploy**:

```bash
cd /opt/golf-model
git log --oneline -n 10
git checkout <known-good-sha>
./deploy.sh --update-local
```

Or revert the bad commit on `main` and redeploy. Do **not** bind port 8000 from `/root/golf-model`.

## Prevention

- Deploy only via `./deploy.sh --update` / `--update-local` (syncs systemd units + runs smoke checks)
- `GOLF_APP_ROOT=/opt/golf-model` and `GOLF_DATA_DIR=/opt/golf-model/data` in systemd units
- `ExecStartPre` runs `scripts/ensure_port_owner.sh` before dashboard bind
- Monitor `scripts/reliability_synthetic_check.py` (GitHub `reliability-monitor` workflow)
- `golf-live-refresh-watchdog.timer` runs `scripts/live_refresh_watchdog.py --restart` every 5 minutes on production

## Integrity

- Empty +EV boards with honest diagnostics are correct — never fabricate picks or relax EV gates.
- When data is stale or split-brain, the API returns `ok:false` and the UI hides cached rows.
