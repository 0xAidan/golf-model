#!/usr/bin/env bash
# Move data/ and backups/ onto a dedicated Hetzner volume.
# Planned 15–30 min pause. Do NOT run during a live round, and do NOT
# stack a Caddy cutover in the same hour.
#
# Usage (on the VPS, after the volume is attached as e.g. /dev/sdb):
#   DEVICE=/dev/sdb MOUNT=/mnt/golf-data ./scripts/migrate_data_to_volume.sh
set -euo pipefail

REPO="${DEPLOY_PATH:-/opt/golf-model}"
DEVICE="${DEVICE:-}"
MOUNT="${MOUNT:-/mnt/golf-data}"
LABEL="${VOLUME_LABEL:-golf-data}"

if [ -z "$DEVICE" ]; then
    echo "Set DEVICE to the attached volume (e.g. /dev/sdb)" >&2
    exit 1
fi
if [ ! -b "$DEVICE" ]; then
    echo "DEVICE $DEVICE is not a block device" >&2
    exit 1
fi

echo "[volume] formatting $DEVICE only if it has no filesystem"
if ! blkid "$DEVICE" >/dev/null 2>&1; then
    mkfs.ext4 -L "$LABEL" "$DEVICE"
fi

mkdir -p "$MOUNT"
if ! findmnt "$MOUNT" >/dev/null 2>&1; then
    mount "$DEVICE" "$MOUNT"
fi

uuid="$(blkid -s UUID -o value "$DEVICE")"
if ! grep -q "$uuid" /etc/fstab; then
    echo "UUID=$uuid $MOUNT ext4 defaults,nofail 0 2" >> /etc/fstab
    echo "[volume] added $MOUNT to /etc/fstab"
fi

mkdir -p "$MOUNT/data" "$MOUNT/backups"

echo "[volume] stopping golf services"
systemctl stop golf-dashboard golf-live-refresh golf-agent || true

echo "[volume] copying data and backups (this is the long step)"
rsync -aH --info=progress2 "$REPO/data/" "$MOUNT/data/"
rsync -aH --info=progress2 "$REPO/backups/" "$MOUNT/backups/"

env_file="$REPO/.env"
touch "$env_file"
python3 - <<PY
from pathlib import Path
path = Path("$env_file")
text = path.read_text(encoding="utf-8") if path.exists() else ""
updates = {
    "GOLF_DATA_DIR": "$MOUNT/data",
    "GOLF_DB_PATH": "$MOUNT/data/golf.db",
}
for key, value in updates.items():
    line = f"{key}={value}"
    if any(row.startswith(f"{key}=") for row in text.splitlines()):
        rows = []
        for row in text.splitlines():
            if row.startswith(f"{key}="):
                rows.append(line)
            else:
                rows.append(row)
        text = "\n".join(rows) + ("\n" if text.endswith("\n") else "")
    else:
        text = text.rstrip() + f"\n{line}\n"
path.write_text(text, encoding="utf-8")
print("[volume] updated .env GOLF_DATA_DIR / GOLF_DB_PATH")
PY

# Keep a pointer so old paths still resolve during the first restart.
if [ ! -L "$REPO/data" ]; then
    mv "$REPO/data" "$REPO/data.root-disk-copy"
    ln -s "$MOUNT/data" "$REPO/data"
fi
if [ ! -L "$REPO/backups" ]; then
    mv "$REPO/backups" "$REPO/backups.root-disk-copy"
    ln -s "$MOUNT/backups" "$REPO/backups"
fi

systemctl daemon-reload
systemctl reset-failed golf-dashboard golf-live-refresh || true
systemctl start golf-dashboard golf-live-refresh
echo "[volume] services started. Confirm https://golf.shermandavison.com/ and snapshot age."
echo "[volume] after soak, you may delete $REPO/data.root-disk-copy and backups.root-disk-copy"
