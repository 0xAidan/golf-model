#!/usr/bin/env bash
# Fail deploy/restart when port 8000 is owned outside the canonical app root.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -x "${DEPLOY_PATH}/venv/bin/python" ]; then
  PYTHON="${DEPLOY_PATH}/venv/bin/python"
elif [ -x "${REPO_ROOT}/venv/bin/python" ]; then
  PYTHON="${REPO_ROOT}/venv/bin/python"
else
  PYTHON="python3"
fi

export GOLF_APP_ROOT="${GOLF_APP_ROOT:-${DEPLOY_PATH}}"
"${PYTHON}" "${REPO_ROOT}/scripts/port_8000_audit.py" --expected-app-root "${GOLF_APP_ROOT}"
