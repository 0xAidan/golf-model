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
        echo "[deploy] backing up $DB_PATH"
        python -m src.backup --keep "$DEPLOY_BACKUP_KEEP" || true
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

systemctl restart golf-dashboard golf-agent golf-live-refresh

echo "Update complete."
