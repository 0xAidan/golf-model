# Caddy static fallback

When Python is dead, visitors should still get the last built React app — not a blank 502.

## Why

`golf-dashboard` crash-loops if `golf.db` is corrupt (import-time SQLite open). Caddy only reverse-proxied `:8000`, so the public site was empty.

## Cut over

1. Merge the `golf.shermandavison.com` block from [`deploy/caddy/Caddyfile`](../../deploy/caddy/Caddyfile) into `/etc/caddy/Caddyfile`. Keep the other Sherman-Davison site blocks.
2. `caddy validate --config /etc/caddy/Caddyfile`
3. `systemctl reload caddy`

Do this on a quiet minute, not in the same hour as a disk migrate.

## What you should see

- Backend up: unchanged. HTML and `/api/*` come from FastAPI.
- Backend down: `/` serves `frontend/dist/index.html`. `/api/*` returns JSON `503` with `db_unavailable: true` so the SPA can show the rebuild banner from cache.

## Rollback

Restore the previous `/etc/caddy/Caddyfile` (proxy-only golf block) and `systemctl reload caddy`.
