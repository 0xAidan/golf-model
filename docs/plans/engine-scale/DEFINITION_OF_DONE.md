# Engine Scale — Definition of Done & Evidence Packet

Mirrors section K of the master plan. Each item links to the PR/commit/artifact that
satisfies it. "Looks fine locally" is not evidence. Branches stack: Wave 1 (#148) →
Wave 2 (#149) → Wave 3 (#150) → Wave 4.

## Status legend
- ✅ done with committed evidence
- 🟡 implemented; final evidence requires production data/soak (documented)
- ⬜ deferred (tracked)

## Waves shipped

| Wave | PR | Scope |
|------|----|-------|
| 1 | #148 `program/engine-scale-wave-1` | CI restore + doc drift; P1 defects incl. book filter; track registry + provenance; grading reconciliation + read-only `/compare` |
| 2 | #149 `program/engine-scale-wave-2` | field-complete player board + `/players/:key`; promotion workflow MVP + `/eval` Promotion tab |
| 3 | #150 `program/engine-scale-wave-3` | eval platform (`/api/eval/track-comparison` + `/eval` Track compare); trial-327 revalidation harness; lab challenger shadow rails |
| 4 | `program/engine-scale-wave-4` | ops/worker hardening; rollback drill; ops route extraction; this evidence packet |

## DoD checklist

- ✅ **Tracks:** `GET /api/tracks` shows both slots with stable `config_hash`; `picks.model_config_hash` + snapshot `strategy_meta.config_hash` provenance. Tests: `tests/test_track_registry.py`.
- 🟡 **Promotion + rollback:** workflow + gates + audit trail + one-action rollback (`tests/test_track_registry.py::test_promote_and_rollback_round_trip`); flag-gated OFF. Production round-trip with `TRACK_PROMOTION_ENABLED=1` against a staging DB → drill log in `docs/runbooks/rollback-drill.md` (pending).
- ✅ **Compare/Eval UI:** `/compare` (read-only, both tracks) + `/eval` (Track compare + Promotion). Tests: `compare-page.test.tsx`, `eval-page.test.tsx`, `track-badge.test.tsx`. Visual baseline recapture pending (see below).
- ✅ **Eval API:** `/api/eval/track-comparison` live-graded metrics + overlap; segregated from sim. Tests: `tests/test_eval_aggregates.py`.
- ✅ **Players field-complete:** `/api/players/field-board` (single-pass, cached) + `/players` field board + `/players/:key` deep link. Tests: `tests/test_field_board.py`, `field-board-panel.test.tsx`.
- ✅ **Grading trust:** reconciliation tool + example report (`output/audits/grading_reconciliation_20260610.md`); +EV-only invariants intact. Tests: `tests/test_grading_reconciliation.py`. Production reconciliation run pending (VPS).
- 🟡 **Algo:** trial-327 revalidation harness + committed dossier (`docs/research/experiments/trial_327_revalidation.md`); lab challenger shadow rails. Production numbers PENDING — lab track labelled "challenger (validation pending)". No dashboard-slot algo change shipped (gated).
- ✅ **Defects:** Wave-1 P1s closed with tests; register updated (`docs/recovery_defect_register.md`). Deferred items (P1-6 field enforcement, P1-7 frontend per-query errors) re-triaged with rationale.
- ✅ **Platform:** CI gates restored (a11y/visual-diff/bundle-budget); ops health exposes track state; worker stale-pidfile hardening; ops route extracted. Tests green.
- 🟡 **Deploy/observability:** `/api/ops/health` artifact + rollback drill log to be captured post-deploy per wave.

## Verification (every PR, all green)

- `python3 -m pytest tests/` — Wave 4 tip: **516+ passed, 1 skipped**.
- `cd frontend && npm run lint`* `&& npm run typecheck && npm run test && npm run build && npm run bundle:budget && npm run test:a11y` — 135 vitest tests, a11y 0 critical, bundle within +5%.
- `ruff check` clean on all new/modified Python.

*`npm run lint` has pre-existing errors on `main` (unused-vars / react-refresh across ~20 files) unrelated to this program; no new violations were introduced. Tracked separately.

## Remaining to reach 100% (post-merge, production)

- ⬜ Capture the `docs/screenshots/engine-scale-v1/` visual baseline against real data (the committed baseline predates PR #145; CI visual-diff skips until then).
- ⬜ Run `scripts/grading_reconciliation.py --write` + `scripts/revalidate_trial327.py --write` on the VPS; fill the dossier; decide promote/replace for the lab slot.
- ⬜ Execute the rollback drill (code + registry + variant) and record in `docs/runbooks/rollback-drill.md`.
- ⬜ Continue app.py decomposition beyond `/api/ops/health` (players, live-refresh, autoresearch blocks) — behavior-preserving, one router per PR.
- ⬜ Per-query frontend error surfacing (defect P1-7) and field-enforcement fail-closed (P1-6) with a representative-field fixture.
