# Never-down go-live checklist

This is the punch list from the Aug 16 hardening plan. The **code** can ship while a tournament is live. The **volume move** waits until play is quiet. The **Caddy static-SPA cutover** is a different hour the next day.

We do **not** promise the site can never go down. We promise the Aug 5 (disk full) and Aug 16 (corrupt SQLite → bare 502, week of data gone, no text) failure class cannot silently repeat.

The plan is **not done** until all three gates below have actually happened.

## Gate 1 — Phone alerts (ntfy)

On the VPS after deploy:

```bash
grep NTFY_TOPIC /opt/golf-model/.env
```

Subscribe on your phone: `https://ntfy.sh/<that-topic>`

Then send a test:

```bash
cd /opt/golf-model && source venv/bin/activate
python3 - <<'PY'
from src.telegram_alerts import send_ops_alert
print(send_ops_alert("Golf Model ops alert test — you can ignore this.", severity="info"))
PY
```

You must see the notification. If you do not, this gate has not passed.

## Gate 2 — Off-site copy we have restored from (Backblaze B2)

Put keys in `/opt/golf-model/.env` only. Do not paste them in chat.

```
B2_APPLICATION_KEY_ID=...
B2_APPLICATION_KEY=...
B2_BUCKET_NAME=...
B2_S3_ENDPOINT=s3.us-west-000.backblazeb2.com
```

Then, on the VPS (side copy — this does **not** replace the live database):

```bash
cd /opt/golf-model && source venv/bin/activate
python3 scripts/b2_restore_fire_drill.py --json
```

Expect `ok: true`. If this fails, Litestream/gzip off-site is not proven.

## Gate 3 — Bigger disk (Hetzner volume)

1. In the Hetzner console, create a **~160GB** volume and attach it to this VPS.
2. **Tonight after St. Jude play is quiet** (15–30 min planned pause). Do **not** also change Caddy in the same hour.
3. On the VPS:

```bash
# confirm the new disk name first (often /dev/sdb)
lsblk
DEVICE=/dev/sdb MOUNT=/mnt/golf-data /opt/golf-model/scripts/migrate_data_to_volume.sh
```

4. Confirm https://golf.shermandavison.com/ loads and the snapshot is this week's event.

## Next day (separate hour) — Caddy static SPA

Copy `deploy/caddy/Caddyfile` to `/etc/caddy/Caddyfile` (or import the site block), then `caddy reload`. After that, a dead Python process still shows the golf UI instead of a bare 502.

## After deploy, on this VPS

- `golf-agent` must be **stopped and disabled**. This box is the public site, not a research lab.
- Confirm timers: `golf-disk-watchdog`, `golf-db-integrity`, `golf-backup`, `golf-backup-interval`, `golf-dashboard-watchdog`, `golf-external-uptime`.
- If B2 keys are present, `golf-litestream` should be running.
- Soak 24 hours: backup timer, integrity timer, ntfy test, snapshot age.
- Fire drill is a **side copy** during St. Jude week — do not flip the live database during the event.

## What you do vs what the server does

| You | Server |
|---|---|
| Subscribe to ntfy and confirm the test text | Generate `NTFY_TOPIC` on deploy if missing |
| Create/attach the Hetzner volume in the console | Mount it and move `data/` + `backups/` when you say play is quiet |
| Put B2 keys in `.env` (never in chat) | Upload gzip + Litestream; run the side-copy restore test |
