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

snapshot_id_before_deploy="$(
    python3 - <<'PY'
import json
from pathlib import Path

path = Path("data/live_refresh_snapshot.json")
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError):
    payload = {}
print(payload.get("snapshot_id") or "")
PY
)"

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[deploy] ERROR: refusing to deploy from a dirty worktree" >&2
    exit 1
fi
git fetch origin
git checkout "$DEPLOY_BRANCH"
if ! git merge-base --is-ancestor HEAD "origin/$DEPLOY_BRANCH"; then
    echo "[deploy] ERROR: local branch diverges from origin/$DEPLOY_BRANCH; resolve it before deploying" >&2
    exit 1
fi
git pull --ff-only origin "$DEPLOY_BRANCH"

if [ -n "$snapshot_id_before_deploy" ]; then
    snapshot_id_after_pull="$(
        python3 - <<'PY'
import json
from pathlib import Path

path = Path("data/live_refresh_snapshot.json")
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError):
    payload = {}
print(payload.get("snapshot_id") or "")
PY
)"
    if [ "$snapshot_id_after_pull" != "$snapshot_id_before_deploy" ]; then
        echo "[deploy] ERROR: runtime snapshot changed during source update; refusing deploy" >&2
        exit 1
    fi
    echo "[deploy] verified runtime snapshot preserved (snapshot_id=$snapshot_id_after_pull)"
fi

if [ ! -x venv/bin/python ]; then
    echo "[deploy] ERROR: venv/bin/python is required for a verified backup" >&2
    exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate
DB_PATH="$(venv/bin/python -m src.backup --print-path)"
if [ -f "$DB_PATH" ]; then
    if ! venv/bin/python -m src.backup --keep "$DEPLOY_BACKUP_KEEP"; then
        if [ "${DEPLOY_ALLOW_UNVERIFIED_BACKUP:-0}" != "1" ]; then
            echo "[deploy] ERROR: verified backup failed; set DEPLOY_ALLOW_UNVERIFIED_BACKUP=1 only after auditing the risk" >&2
            exit 1
        fi
        echo "[deploy] WARNING: proceeding with explicit unaudited-backup override" >&2
    fi
else
    echo "[deploy] no DB at $DB_PATH yet; no backup required"
fi

FRONTEND_BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/golf-frontend-build.XXXXXX")"
cleanup_frontend_build() {
    rm -rf "$FRONTEND_BUILD_DIR"
}
trap cleanup_frontend_build EXIT

pip install -q -r requirements.txt

if [ -f "frontend/package.json" ]; then
    cd frontend
    export NODE_OPTIONS=--max-old-space-size=2048
    npm ci
    npm run build -- --outDir "$FRONTEND_BUILD_DIR"
    cd "$DEPLOY_PATH"
    venv/bin/python scripts/promote_frontend_build.py "$FRONTEND_BUILD_DIR" --verify-only
fi

SERVICES_STOPPED=0
restart_services() {
    if [ "$SERVICES_STOPPED" -eq 1 ]; then
        systemctl restart golf-dashboard golf-agent golf-live-refresh
        SERVICES_STOPPED=0
    fi
    cleanup_frontend_build
}
trap restart_services EXIT

install_systemd_units() {
    if [ ! -d "${DEPLOY_PATH}/deploy/systemd" ]; then
        echo "[deploy] deploy/systemd missing; skipping unit sync"
        return 0
    fi
    for unit in golf-dashboard.service golf-live-refresh.service golf-agent.service golf-live-refresh-watchdog.service golf-live-refresh-watchdog.timer golf-grading-sweep.service golf-grading-sweep.timer golf-retention.service golf-retention.timer golf-storage-janitor.service golf-storage-janitor.timer golf-db-integrity.service golf-db-integrity.timer; do
        if [ -f "${DEPLOY_PATH}/deploy/systemd/${unit}" ]; then
            cp "${DEPLOY_PATH}/deploy/systemd/${unit}" "/etc/systemd/system/${unit}"
            echo "[deploy] synced ${unit}"
        fi
    done
    if [ -f "${DEPLOY_PATH}/deploy/systemd/journald-golf-model.conf" ]; then
        mkdir -p /etc/systemd/journald.conf.d
        cp "${DEPLOY_PATH}/deploy/systemd/journald-golf-model.conf" "/etc/systemd/journald.conf.d/golf-model.conf"
        systemctl restart systemd-journald || true
        journalctl --vacuum-size=1G || true
        echo "[deploy] applied journald SystemMaxUse=1G cap"
    fi
    systemctl daemon-reload
    if systemctl list-unit-files golf-live-refresh-watchdog.timer >/dev/null 2>&1; then
        systemctl enable --now golf-live-refresh-watchdog.timer || true
        echo "[deploy] enabled golf-live-refresh-watchdog.timer"
    fi
    if systemctl list-unit-files golf-grading-sweep.timer >/dev/null 2>&1; then
        systemctl enable --now golf-grading-sweep.timer || true
        echo "[deploy] enabled golf-grading-sweep.timer"
    fi
    if systemctl list-unit-files golf-retention.timer >/dev/null 2>&1; then
        systemctl enable --now golf-retention.timer || true
        echo "[deploy] enabled golf-retention.timer"
    fi
    if systemctl list-unit-files golf-storage-janitor.timer >/dev/null 2>&1; then
        systemctl enable --now golf-storage-janitor.timer || true
        echo "[deploy] enabled golf-storage-janitor.timer"
    fi
    if systemctl list-unit-files golf-db-integrity.timer >/dev/null 2>&1; then
        systemctl enable --now golf-db-integrity.timer || true
        echo "[deploy] enabled golf-db-integrity.timer"
    fi
}

install_systemd_units

systemctl stop golf-live-refresh golf-agent golf-dashboard || true
SERVICES_STOPPED=1
python -c "from src.db import init_db; init_db()"

if [ -f "frontend/package.json" ]; then
    venv/bin/python scripts/promote_frontend_build.py "$FRONTEND_BUILD_DIR"
fi

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

# Disk guards + snapshot retention defaults (append to .env when absent).
venv/bin/python - <<'PY'
from __future__ import annotations

import re
from pathlib import Path

env_path = Path(".env")
prior = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
defaults = {
    "DISK_FREE_MB_WARN": "10240",
    "DISK_FREE_MB_HARD": "5120",
    "SNAPSHOT_HISTORY_RETAIN_DAYS": "210",
    "MARKET_PREDICTION_SLIM_PAYLOAD": "1",
}
appended: list[str] = []
for key, value in defaults.items():
    if re.search(rf"^\s*{re.escape(key)}\s*=", prior, flags=re.MULTILINE):
        print(f"[deploy] {key} already present in .env; leaving unchanged.")
        continue
    appended.append(f"{key}={value}")
if appended:
    block = "\n# Deploy defaults (disk guards + snapshot retention + slim market payloads). See docs/storage-retention.md\n"
    block += "\n".join(appended) + "\n"
    env_path.write_text(prior + block, encoding="utf-8")
    print("[deploy] appended env keys:", ", ".join(appended))
PY

restart_services
trap - EXIT
cleanup_frontend_build

if [ -x "${DEPLOY_PATH}/scripts/ops_verify_production.sh" ] && [ "${DEPLOY_PATH}" = "/opt/golf-model" ]; then
    echo "[deploy] running post-update production verification"
    DEPLOY_PATH="${DEPLOY_PATH}" "${DEPLOY_PATH}/scripts/ops_verify_production.sh" || {
        echo "[deploy] ERROR: post-update verification failed" >&2
        exit 1
    }
fi

echo "Update complete."
