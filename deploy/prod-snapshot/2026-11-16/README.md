# Production snapshot, 2026-11-16

What the server at `/opt/golf-model` was actually running on 2026-11-16, recorded against this branch's base commit `a87d42f` (`codex/matchup-workspace`).

The server's git checkout was `main` at `cb86850` with release files copied over it by install scripts, so its state was not a commit. This folder closes that gap.

## Result of the comparison

Every file in `a87d42f` was compared with the server's copy by git blob hash. Counts are in `deployed_files.json`.

| Status | Files | Meaning |
|---|---|---|
| identical | 1,190 | Server matches this branch |
| server_differs | 1 | `app.py`: the server lacks the `market_evidence` router import and include, and one `p.tournament_id,` column |
| server_has_older_main_version | 45 | The branch changed these but no release installed them. Seven are runtime code or config: `src/autoresearch_operator.py`, `src/clv.py`, `src/operator_contract.py`, `src/operator_read_model.py`, `src/routes/grading_season.py`, `src/routes/operator_ui.py`, `deploy/caddy/Caddyfile`. The rest are tests, docs and frontend source |
| not_installed_on_server | 196 | Frontend source, tests, docs, and code that runs from other directories (`/opt/golf-evidence`, `/opt/golf-learning`) |

The deployed frontend is a built bundle (`market-generation-20261016-02ca588`) whose source is this branch; the server's own `frontend/src` is stale and unused.

## Files here

- `deployed_files.json`: per-file status with hashes.
- `server-vs-branch.patch`: `git diff a87d42f` for the non-frontend, non-test, non-doc files that differ. To reproduce the server's bytes: `git checkout prod-2026-11-16 && git apply deploy/prod-snapshot/2026-11-16/server-vs-branch.patch`.
- `systemd/`: four unit files that existed only on the server (`golf-backup`, `golf-disk-watchdog`). All other live units matched `deploy/systemd/`. Note that `golf-disk-watchdog.service` points at `scripts/disk_watchdog.py`, which does not exist.
- `caddy/golf-site-block.Caddyfile`: the live `golf.shermandavison.com` block. The server's Caddyfile also configures unrelated sites, which are left out.
- `releases.json`: summary of the install receipts under `/opt/golf-model-releases` and `/opt/golf-frontend/releases`.

Also added on this commit: 20 generated course profiles under `data/courses/` that existed only on the server.

Not included: `.env` files, the database, backups, `output/` audit files, and the server's 52 local git stashes.
