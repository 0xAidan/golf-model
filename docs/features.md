# Features Log

Chronological register of shipped features with status. Distinct from the defect register (`recovery_defect_register.md`), which tracks bugs / tech debt.

## 2026-04-22 — T3 Phase 0 + Phase 1: Pair / Team Matchup Model (analytics-only) ✅ DONE

**Tracking issue:** #47. **Scope:** Zurich Classic 2026 (April 23–26) and any future team events.

**Delivered:**
- Phase 0 data audit script (`research/pair_matchup_phase0.py`) + audit report (`docs/research/pair_matchup_phase0_audit.md`). Verdict documented automatically from the local rounds table.
- Phase 1 pair matchup estimator (`src/models/pair_matchup_v1.py`) with format-aware combiners (foursomes: geometric mean of skills; fourball: Gaussian E[max] approximation) and a DG-composite fallback for the insufficient-data case flagged by the audit.
- Shadow table `pair_matchup_predictions` (id, event_id, team_a_p1/p2, team_b_p1/p2, format, predicted_p_a, ts) created on demand when the flag is on. No snapshot or card wiring.
- Admin research endpoint `GET /api/research/pair-matchups` returning 404 when the flag is off.
- Config flag `PAIR_MATCHUP_V1` (`src/config.py`), default **OFF**, env override `PAIR_MATCHUP_V1=1`.

**Ship guarantees:**
- Production card, value path, and live bot are byte-identical to `main` when the flag is off. Golden test: `tests/test_pair_matchup_v1.py::test_zurich_card_byte_identical_when_flag_toggled` also asserts byte-identity with the flag on (shadow writes must not leak into user-facing output).
- No card output. No route on the live dashboard. No snapshot additions.

**Deferred (NOT in this PR):**
- Phase 2 — walk-forward calibration of the v1 estimator against historical Zurich pair results.
- Phase 3 — card output, live API exposure, frontend banner swap.
