# Rollback drill runbook

The 2026-04-13 weekend-readiness report was NO-GO partly because a rollback drill had
**never been executed**. This runbook makes both rollback paths explicit and drillable:
**code rollback** and **model-config rollback**. Run the drill on a staging checkout (or a
low-traffic window) and record the result at the bottom.

## 1. Code rollback (a bad deploy)

The mechanism is git-revert-and-redeploy (no feature-flag rollback for code).

```bash
# On the VPS, in /opt/golf-model:
git log --oneline -5                      # find the bad merge commit
git revert --no-edit <merge-commit-sha>   # or: git checkout <last-good-sha>
./deploy.sh --update-local                # rebuilds FE, runs init_db, restarts services
# verify:
systemctl status golf-dashboard golf-live-refresh
curl -s localhost:8000/api/ops/health | jq '{ok, summary, identity}'
```

Post-rollback soak (10 min): `/api/ops/health` ok, no split-brain, snapshot fresh,
upcoming/live boards render. See `docs/reliability_runbook.md`.

**Never** roll back by running the dashboard from `/root/golf-model` — that knowingly
serves stale data and causes split-brain.

## 2. Model-config rollback (a bad challenger→champion promotion)

Two layers, both reversible:

1. **Registry rollback (one action)** — reverts the `track_configs` dashboard slot to the
   config it replaced (the `parent_id` chain):
   ```bash
   curl -s -X POST localhost:8000/api/tracks/rollback \
     -H 'content-type: application/json' -d '{"track":"dashboard"}'
   curl -s localhost:8000/api/tracks | jq '.tracks.dashboard.config_hash'
   ```
   (Requires `TRACK_PROMOTION_ENABLED=1`; mutating endpoints honor `DASHBOARD_API_KEY`.)
2. **Runtime variant revert** — if a promotion was actually wired live via the documented
   env change, revert it:
   ```bash
   # restore the operator dashboard to the Masters-era baseline model
   # (edit /opt/golf-model/.env): COCKPIT_SNAPSHOT_MODEL_VARIANT=baseline
   systemctl restart golf-live-refresh golf-dashboard
   ```
   Confirm via `/api/ops/health` → `.tracks.active.dashboard.config_hash` and
   `/api/tracks` `effective_config_hash`.

## 3. Stale-worker recovery (pidfile)

A SIGKILLed worker leaves a stale `/tmp/golf_live_refresh.pid`. The worker now clears a
stale pidfile on startup (`_clear_stale_pidfile`). To force-clear manually:
```bash
systemctl restart golf-live-refresh   # startup clears the stale pidfile
```

## Drill log

| Date | Operator | Path drilled | Result | Notes |
|------|----------|--------------|--------|-------|
| _pending_ | _pending_ | code / registry / variant | _pending_ | run on staging first |
