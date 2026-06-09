#!/usr/bin/env bash
# Run on the VPS (or any host that holds the repo). Do not invoke via SSH to "self".
# Expects: DEPLOY_PATH, DEPLOY_BRANCH (defaults set by caller).
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
# Disk budget: typical golf.db ~6GB; 14 retained copies can exceed a small VPS root volume.
# Aligns with ``golf-backup.service`` on the server: set ``DEPLOY_BACKUP_KEEP`` in ``.env``;
# the oneshot unit runs ``bash -lc`` that sources ``.env`` then ``python -m src.backup --keep "${DEPLOY_BACKUP_KEEP:-4}"``.
DEPLOY_BACKUP_KEEP="${DEPLOY_BACKUP_KEEP:-4}"

cd "$DEPLOY_PATH"

# Backup before update
if [ -x venv/bin/python ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    DB_PATH="$(python -m src.backup --print-path 2>/dev/null || echo "data/golf.db")"
    if [ -f "$DB_PATH" ]; then
        # Full SQLite copies can require ~= DB size in additional free space.
        # If disk is too tight, skip pre-update backup instead of failing noisy.
        if venv/bin/python - "$DB_PATH" <<'PY'
from __future__ import annotations

import os
import shutil
import sys

db_path = sys.argv[1]
db_size = os.path.getsize(db_path)
free = shutil.disk_usage(os.path.dirname(db_path)).free

# Require 1.25x DB size free before attempting another full copy.
required = int(db_size * 1.25)
if free < required:
    print(
        f"[deploy] skipping pre-update backup (free={free // (1024*1024)} MiB, "
        f"required={required // (1024*1024)} MiB, db={db_size // (1024*1024)} MiB)"
    )
    raise SystemExit(1)
print(f"[deploy] backing up {db_path}")
PY
        then
            python -m src.backup --keep "$DEPLOY_BACKUP_KEEP" || true
        fi
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
    npm ci
    npm run build
    cd "$DEPLOY_PATH"
    # Fail fast if index.html references missing bundles (prevents white-screen deploys).
    venv/bin/python - <<'PY' || { echo "[deploy] ERROR: frontend build verification failed" >&2; exit 1; }
from __future__ import annotations

import re
import sys
from pathlib import Path

dist = Path("frontend/dist")
index = dist / "index.html"
if not index.is_file():
    print("[deploy] missing frontend/dist/index.html", file=sys.stderr)
    sys.exit(1)

html = index.read_text(encoding="utf-8")
refs = re.findall(r'(?:src|href)="\./assets/([^"]+)"', html)
missing = [name for name in refs if not (dist / "assets" / name).is_file()]
if missing:
    print("[deploy] index.html references missing assets:", ", ".join(missing), file=sys.stderr)
    sys.exit(1)
print(f"[deploy] frontend build OK ({len(refs)} assets referenced by index.html)")
PY
fi

SERVICES_STOPPED=0
restart_services() {
    if [ "$SERVICES_STOPPED" -eq 1 ]; then
        systemctl restart golf-dashboard golf-agent golf-live-refresh
        SERVICES_STOPPED=0
    fi
}
trap restart_services EXIT

install_systemd_units() {
    if [ ! -d "${DEPLOY_PATH}/deploy/systemd" ]; then
        echo "[deploy] deploy/systemd missing; skipping unit sync"
        return 0
    fi
    for unit in golf-dashboard.service golf-live-refresh.service golf-agent.service; do
        if [ -f "${DEPLOY_PATH}/deploy/systemd/${unit}" ]; then
            cp "${DEPLOY_PATH}/deploy/systemd/${unit}" "/etc/systemd/system/${unit}"
            echo "[deploy] synced ${unit}"
        fi
    done
    systemctl daemon-reload
}

install_systemd_units

systemctl stop golf-live-refresh golf-agent golf-dashboard || true
SERVICES_STOPPED=1
python -c "from src.db import init_db; init_db()"

# Lab board (/lab): ensure parallel lab lane is on for the live-refresh worker + API unless
# operators already set LIVE_REFRESH_LAB_PROFILE_ENABLED in .env (set to 0 on tiny VPS to save CPU).
venv/bin/python - <<'PY'
from __future__ import annotations

import re
from pathlib import Path

env_path = Path(".env")
prior = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
if re.search(r"^\s*LIVE_REFRESH_LAB_PROFILE_ENABLED\s*=", prior, flags=re.MULTILINE):
    print("[deploy] LIVE_REFRESH_LAB_PROFILE_ENABLED already present in .env; leaving unchanged.")
else:
    block = (
        "\n# Lab board (/lab): parallel snapshot lane (profiles.yaml lab_sandbox). "
        "Set to 0/false on very small hosts to skip extra model passes.\n"
        "LIVE_REFRESH_LAB_PROFILE_ENABLED=1\n"
    )
    env_path.write_text(prior + block, encoding="utf-8")
    print("[deploy] appended LIVE_REFRESH_LAB_PROFILE_ENABLED=1 to .env")
PY

restart_services
trap - EXIT

if [ -x "${DEPLOY_PATH}/scripts/ops_verify_production.sh" ] && [ "${DEPLOY_PATH}" = "/opt/golf-model" ]; then
    echo "[deploy] running post-update production verification"
    DEPLOY_PATH="${DEPLOY_PATH}" "${DEPLOY_PATH}/scripts/ops_verify_production.sh" || {
        echo "[deploy] ERROR: post-update verification failed" >&2
        exit 1
    }
fi

echo "Update complete."
