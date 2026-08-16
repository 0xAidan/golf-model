#!/usr/bin/env bash
# Run on the VPS (or any host that holds the repo). Do not invoke via SSH to "self".
# Expects: DEPLOY_PATH, DEPLOY_BRANCH (defaults set by caller).
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/golf-model}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
# Disk budget: compressed golf.db backups are ~1GB; keep 2 local copies on a 75GB VPS.
# Aligns with ``golf-backup.service``: set ``DEPLOY_BACKUP_KEEP`` in ``.env``;
# the oneshot unit runs ``bash -lc`` that sources ``.env`` then
# ``python -m src.backup --keep "${DEPLOY_BACKUP_KEEP:-2}" --compress``.
DEPLOY_BACKUP_KEEP="${DEPLOY_BACKUP_KEEP:-2}"

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
        systemctl restart golf-dashboard golf-live-refresh
        systemctl stop golf-agent >/dev/null 2>&1 || true
        SERVICES_STOPPED=0
    fi
}
trap restart_services EXIT

install_systemd_units() {
    if [ ! -d "${DEPLOY_PATH}/deploy/systemd" ]; then
        echo "[deploy] deploy/systemd missing; skipping unit sync"
        return 0
    fi
    for unit in golf-dashboard.service golf-live-refresh.service golf-agent.service golf-live-refresh-watchdog.service golf-live-refresh-watchdog.timer golf-grading-sweep.service golf-grading-sweep.timer golf-retention.service golf-retention.timer golf-backup.service golf-backup.timer golf-backup-interval.timer golf-disk-watchdog.service golf-disk-watchdog.timer golf-db-integrity.service golf-db-integrity.timer golf-db-recover.service golf-dashboard-watchdog.service golf-dashboard-watchdog.timer golf-litestream.service golf-external-uptime.service golf-external-uptime.timer; do
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
    if systemctl list-unit-files golf-backup.timer >/dev/null 2>&1; then
        systemctl enable --now golf-backup.timer || true
        echo "[deploy] enabled golf-backup.timer"
    fi
    if systemctl list-unit-files golf-disk-watchdog.timer >/dev/null 2>&1; then
        systemctl enable --now golf-disk-watchdog.timer || true
        echo "[deploy] enabled golf-disk-watchdog.timer"
    fi
    if systemctl list-unit-files golf-backup-interval.timer >/dev/null 2>&1; then
        systemctl enable --now golf-backup-interval.timer || true
        echo "[deploy] enabled golf-backup-interval.timer"
    fi
    if systemctl list-unit-files golf-db-integrity.timer >/dev/null 2>&1; then
        systemctl enable --now golf-db-integrity.timer || true
        echo "[deploy] enabled golf-db-integrity.timer"
    fi
    if systemctl list-unit-files golf-dashboard-watchdog.timer >/dev/null 2>&1; then
        systemctl enable --now golf-dashboard-watchdog.timer || true
        echo "[deploy] enabled golf-dashboard-watchdog.timer"
    fi
    if systemctl list-unit-files golf-external-uptime.timer >/dev/null 2>&1; then
        systemctl enable --now golf-external-uptime.timer || true
        echo "[deploy] enabled golf-external-uptime.timer"
    fi
    # Production box is a site server, not a research lab.
    systemctl disable --now golf-agent.service >/dev/null 2>&1 || true
    echo "[deploy] golf-agent disabled on this host"
}

install_systemd_units

systemctl stop golf-live-refresh golf-dashboard || true
systemctl stop golf-agent >/dev/null 2>&1 || true
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
    "SNAPSHOT_HISTORY_RETAIN_DAYS": "120",
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

# ntfy topic: generate once so phone alerts work without Telegram.
venv/bin/python - <<'PY'
from __future__ import annotations

import re
import secrets
from pathlib import Path

env_path = Path(".env")
prior = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
if re.search(r"^\s*NTFY_TOPIC\s*=", prior, flags=re.MULTILINE):
    print("[deploy] NTFY_TOPIC already present in .env")
else:
    topic = "golf-model-" + secrets.token_hex(8)
    prior = prior.rstrip() + f"\nNTFY_SERVER=https://ntfy.sh\nNTFY_TOPIC={topic}\n"
    env_path.write_text(prior + "\n", encoding="utf-8")
    print(f"[deploy] generated NTFY_TOPIC. Subscribe on your phone: https://ntfy.sh/{topic}")
PY

if [ -x "${DEPLOY_PATH}/scripts/install_litestream.sh" ]; then
    "${DEPLOY_PATH}/scripts/install_litestream.sh" || echo "[deploy] litestream install skipped"
fi
if systemctl list-unit-files golf-litestream.service >/dev/null 2>&1; then
    if grep -q "^B2_APPLICATION_KEY_ID=" "${DEPLOY_PATH}/.env" 2>/dev/null; then
        systemctl enable --now golf-litestream.service || true
        echo "[deploy] enabled golf-litestream.service"
    else
        echo "[deploy] B2 keys not in .env; litestream left disabled"
    fi
fi

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
