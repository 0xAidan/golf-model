# Recovery Verification Report

Date: 2026-04-13

## Gate Results

- ✅ Targeted backend regression tests pass:
  - `python3 -m pytest tests/test_field_selection.py tests/test_run_provenance.py -q`
  - Result: `7 passed`
- ✅ Frontend lint passes:
  - `cd frontend && npm run lint`
- ✅ Frontend production build passes:
  - `cd frontend && npm run build`
- ✅ Baseline artifact pack generated:
  - `python3 scripts/build_recovery_baseline_pack.py`
  - Artifacts:
    - `output/recovery/baseline_pack_20260413_160558.json`
    - `output/recovery/baseline_pack_20260413_160558.md`

## Regression Gates Added

- Strict field filtering now fails closed when confirmed field rows are absent.
- Missing `player_key` rows are excluded from strict field output.
- Live snapshot recompute now uses ingest event context (`event_name`, `course`, `year`) to reduce cross-event drift.
- Runtime parity fixes align diversification/exposure/3-ball flow between CLI and service.
- Per-run provenance JSON now written for CLI and service flows.
- CI now includes:
  - Python 3.11 + 3.12 matrix for tests/lint
  - Frontend `npm run lint` and `npm run build`

## Cutover Preconditions

Before production cutover, run on VPS:

1. `DEPLOY_HOST=root@204.168.147.6 ./deploy.sh --update`
2. `DEPLOY_HOST=root@204.168.147.6 ./deploy.sh --status`
3. `ssh root@204.168.147.6 "systemctl status golf-dashboard golf-agent golf-live-refresh --no-pager"`
4. `ssh root@204.168.147.6 "journalctl -u golf-live-refresh -n 200 --no-pager"`
5. `curl -sS http://204.168.147.6:8000/api/live-refresh/status`
6. `curl -sS http://204.168.147.6:8000/api/live-refresh/snapshot`

## Rollback Procedure

If trust gates fail after deploy:

1. `ssh root@204.168.147.6 "cd /opt/golf-model && git checkout <last_known_good_commit> && git pull --ff-only origin main"`
2. `ssh root@204.168.147.6 "cd /opt/golf-model && source venv/bin/activate && python -m src.backup --restore-latest"`
3. `ssh root@204.168.147.6 "systemctl restart golf-dashboard golf-agent golf-live-refresh"`
4. Re-run status and snapshot checks.
