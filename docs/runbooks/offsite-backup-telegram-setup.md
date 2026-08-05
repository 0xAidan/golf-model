# Off-site backup + Telegram ops alerts setup

Do this once after deploying the storage-durability PR. Takes about 10 minutes.

## 1. Telegram ops alerts (~2 minutes)

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, follow prompts, copy the **bot token**.
3. Start a chat with your new bot (press Start), then get your chat id:
   - Easiest: message [@userinfobot](https://t.me/userinfobot) and copy your Id, **or**
   - Open `https://api.telegram.org/bot<TOKEN>/getUpdates` after messaging your bot and read `chat.id`.
4. On the VPS, edit `/opt/golf-model/.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

5. Restart services so they pick up the env:

```bash
systemctl restart golf-dashboard golf-live-refresh golf-disk-watchdog.timer golf-backup.timer
```

6. Smoke test:

```bash
cd /opt/golf-model && source venv/bin/activate
python3 - <<'PY'
from src.telegram_alerts import send_ops_alert
print(send_ops_alert("Golf Model ops alert test — you can ignore this.", severity="info"))
PY
```

You should get a Telegram message. After that, backup failures, low-disk watchdog trips, and live-refresh restarts will notify you automatically.

## 2. Backblaze B2 off-site backups (~5 minutes)

1. Create a free account at https://www.backblaze.com/b2/sign-up.html
2. **Buckets** → **Create a Bucket**
   - Name: `golf-model-backups` (or similar)
   - Files: Private
3. **App Keys** → **Add a New Application Key**
   - Allow access to the bucket you just created
   - Copy **keyID** and **applicationKey** (shown once)
4. On the VPS, edit `/opt/golf-model/.env`:

```bash
B2_APPLICATION_KEY_ID=...
B2_APPLICATION_KEY=...
B2_BUCKET_NAME=golf-model-backups
B2_OFFSITE_PREFIX=golf-model
B2_KEEP=4
```

5. Test an upload of the latest local backup:

```bash
cd /opt/golf-model && source venv/bin/activate
python3 - <<'PY'
from src.backup import list_backups
from src.offsite_backup import upload_backup_offsite
backs = list_backups()
assert backs, "no local backup"
print(upload_backup_offsite(backs[0]["path"]))
PY
```

Expect `ok: True` and a `remote_name`. Confirm the object appears in the B2 bucket UI.

Nightly `golf-backup.service` will upload automatically after each successful compressed backup.

## 3. What "healthy" looks like afterward

- `df -h /` shows comfortable free space (target: >15 GB)
- `ls -lah backups/` shows recent `*.db.gz` files (not multi-GB uncompressed `.db`)
- `/system` Storage panel shows a recent backup age in hours (not "no backup found")
- `GET /api/ops/health` includes `"backup": {"ok": true, "status": "ok", ...}`
- Telegram receives alerts if disk drops below warn/hard or backups fail
