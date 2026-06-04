# 01 — Goals and Non-Negotiables

## Product goals
1. UI must look **materially different** and more polished on primary workflows (`/`, `/matchups`, `/players`, `/lab`).
2. Preserve all core route pathways and API contracts.
3. Fix slow/clunky interactions; remove draggable resize handles.
4. Restore **upcoming** rankings table behavior; keep **live-only** delta/leaderboard columns for live mode only.

## Non-regression constraints (from prior failed runs)
- No "done/live" claims without route-by-route screenshot evidence.
- No theme-only passes presented as full overhaul.
- CSS import order must keep `terminal-visual-v2.css` after base tokens.
- Deploy must use correct mode (`--update-local` on server, `--update` from laptop).
- Rankings behavior must be validated by automated tests, not manual spot-check only.

## Routes that must remain functional
`/`, `/matchups`, `/players`, `/lab`, `/lab/picks`, `/grading`, `/track-record`, `/research/legacy-model`, `/research/champion-challenger`, `/research/diagnostics`

## Out of scope
- Backend API contract changes
- Database schema changes
- New betting logic or model changes
