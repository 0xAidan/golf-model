# Reliability Monitoring Runbook

This runbook covers synthetic reliability alerts for production (`https://golf.ancc.blog`).

## What is monitored

The scheduled workflow `Production Reliability Monitor` runs `scripts/reliability_synthetic_check.py` and checks:

- `GET /` returns `200` within 5 seconds
- `GET /api/live-refresh/status` returns valid JSON and `running` metadata within 8 seconds
- `GET /api/live-refresh/snapshot` returns valid JSON within 8 seconds
- `snapshot.generated_at` is no older than 45 minutes

## Alert policy (high signal, low noise)

- Schedule: every 30 minutes
- Alert trigger: any failed synthetic check
- Alert channel: GitHub issue labeled `reliability-alert` (deduplicated to a single open issue)
- Alert context includes:
  - failing check names
  - workflow run URL
  - this runbook link

## First response checklist

1. Open the latest failed run and inspect `synthetic-check-results` artifact.
2. Confirm outage from an independent source:
   - `curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" https://golf.ancc.blog/`
   - `curl -s https://golf.ancc.blog/api/live-refresh/status`
   - `curl -s https://golf.ancc.blog/api/live-refresh/snapshot`
3. SSH to production host (`root@204.168.147.6`) and inspect service state:
   - `systemctl status golf-dashboard golf-live-refresh golf-agent`
   - `journalctl -u golf-dashboard -n 150 --no-pager`
   - `journalctl -u golf-live-refresh -n 150 --no-pager`
4. If dashboard is down:
   - `systemctl restart golf-dashboard`
   - verify `http://127.0.0.1:8000/` returns `200`
5. If snapshot is stale:
   - verify `golf-live-refresh` is active
   - inspect for repeated runtime warnings/errors in live refresh logs
   - if needed, `systemctl restart golf-live-refresh` and re-check snapshot age
6. Re-run the synthetic check manually:
   - `python3 scripts/reliability_synthetic_check.py --base-url https://golf.ancc.blog`

## Rollback trigger guidance

Use rollback when either condition is true:

- repeated monitor failures after one restart cycle
- recent deploy introduced a regression that reproduces consistently

Rollback steps:

1. On server: `cd /opt/golf-model`
2. Identify last known-good commit from `git log --oneline`
3. `git checkout <known-good-sha>`
4. `./deploy.sh --update-local`
5. Re-run synthetic checks and verify alerts stop firing

## Post-incident follow-up

- Record root cause and preventive action in the active PR.
- Add or update regression tests for the failure mode.
- Close the `reliability-alert` issue once two consecutive monitor runs pass.
