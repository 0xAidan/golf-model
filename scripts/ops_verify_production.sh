#!/usr/bin/env bash
# Post-deploy production smoke: systemd, port owner, localhost API identity.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
PUBLIC_URL="${PUBLIC_URL:-https://golf.ancc.blog}"
LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export GOLF_APP_ROOT="${GOLF_APP_ROOT:-${DEPLOY_PATH}}"

echo "[ops-verify] systemd active states"
systemctl is-active golf-dashboard
systemctl is-active golf-live-refresh
systemctl is-active golf-live-refresh-watchdog.timer

echo "[ops-verify] port 8000 audit"
"${REPO_ROOT}/scripts/ensure_port_owner.sh"

if [ -x "${DEPLOY_PATH}/venv/bin/python" ]; then
  PYTHON="${DEPLOY_PATH}/venv/bin/python"
else
  PYTHON="python3"
fi

echo "[ops-verify] localhost ops health (with retries)"
for attempt in 1 2 3 4 5; do
  if "${PYTHON}" - <<'PY'
import json
import sys
import urllib.request

url = "http://127.0.0.1:8000/api/ops/health"
with urllib.request.urlopen(url, timeout=10) as response:
    payload = json.loads(response.read().decode("utf-8"))
if not payload.get("ok"):
    print(json.dumps(payload, indent=2), file=sys.stderr)
    raise SystemExit(f"localhost ops health not ok: {payload.get('summary')}")
print(f"localhost ops health ok app_root={payload.get('identity', {}).get('app_root')}")
PY
  then
    break
  fi
  if [ "${attempt}" -eq 5 ]; then
    exit 1
  fi
  echo "[ops-verify] waiting for services to warm up (${attempt}/5)..."
  sleep 4
done

echo "[ops-verify] synthetic reliability (local + public)"
"${PYTHON}" "${REPO_ROOT}/scripts/reliability_synthetic_check.py" \
  --base-url "${LOCAL_URL}" \
  --expected-app-root "${GOLF_APP_ROOT}" \
  --max-snapshot-age-seconds 7200

"${PYTHON}" "${REPO_ROOT}/scripts/reliability_synthetic_check.py" \
  --base-url "${PUBLIC_URL}" \
  --max-snapshot-age-seconds 7200

echo "[ops-verify] prune snapshot history (retain 90d)"
SNAPSHOT_HISTORY_RETAIN_DAYS="${SNAPSHOT_HISTORY_RETAIN_DAYS:-90}" \
  "${PYTHON}" "${REPO_ROOT}/scripts/prune_snapshot_history.py" --vacuum || {
    echo "[ops-verify] WARN: snapshot history prune failed" >&2
  }

echo "[ops-verify] all checks passed"
