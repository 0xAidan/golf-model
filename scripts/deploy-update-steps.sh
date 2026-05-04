#!/usr/bin/env bash
# Run on the VPS (or any host that holds the repo). Do not invoke via SSH to "self".
# Expects: DEPLOY_PATH, DEPLOY_BRANCH (defaults set by caller).
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

cd "$DEPLOY_PATH"

# Backup before update
if [ -x venv/bin/python ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    DB_PATH="$(python -m src.backup --print-path 2>/dev/null || echo "data/golf.db")"
    if [ -f "$DB_PATH" ]; then
        echo "[deploy] backing up $DB_PATH"
        python -m src.backup --keep 14 || true
    else
        echo "[deploy] no DB at $DB_PATH yet; skipping pre-update backup"
    fi
else
    echo "[deploy] venv not available; skipping pre-update backup"
fi

# Built artifacts / runtime snapshot can block git pull if tracked; stash then rebuild
STASH_TS="$(date -u +%Y%m%dT%H%M%SZ)"
git stash push -m "[deploy] auto-stash pre-pull ${STASH_TS}" -- frontend/dist data/live_refresh_snapshot.json || true

git fetch origin
git checkout "$DEPLOY_BRANCH"
git pull origin "$DEPLOY_BRANCH"

# shellcheck disable=SC1091
source venv/bin/activate
pip install -q -r requirements.txt

if [ -f "frontend/package.json" ]; then
    cd frontend
    export NODE_OPTIONS=--max-old-space-size=2048
    # Cockpit Lab UI: Vite bakes this at build time. Default on for operator VPS deploys;
    # set VITE_COCKPIT_LAB=0 before deploy to omit the lab nav and /cockpit-lab route.
    export VITE_COCKPIT_LAB="${VITE_COCKPIT_LAB:-1}"
    npm ci
    npm run build
    cd "$DEPLOY_PATH"
fi

python -c "from src.db import init_db; init_db()"

systemctl restart golf-dashboard golf-agent golf-live-refresh

echo "Update complete."
