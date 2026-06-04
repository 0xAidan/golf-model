# 08 — Rollout and Rollback Plan

## Merge path
1. Open PR from `feat/frontend-overhaul-stability`
2. CI must pass (frontend typecheck, test, build + python tests)
3. Attach screenshot matrix + DoD checklist to PR body
4. Merge to `main`
5. Deploy: `./deploy.sh --update` (laptop) or `./deploy.sh --update-local` (on VPS)

## Post-deploy soak (10 minutes)
- `GET /api/live-refresh/status` → running
- `GET /api/live-refresh/snapshot` → ok + sections populated
- Load `/` — upcoming tab shows model-centric rankings
- Load `/` — live tab shows movement columns
- No sustained runtime error banner

## Rollback
```bash
git revert <merge-commit-sha>
./deploy.sh --update-local   # on server
```
Or checkout previous `main` SHA and redeploy.

## Risk notes
- Tabbed center column changes default visible board (Top picks first) — intentional.
- Users must click **Rankings** tab to see power rankings on desktop.
