# 14 — Grading Trust Contract

**Status:** Phase 2 + Phase 5  
**Branch:** `feat/monitoring-v3-complete`

## +EV-only policy (non-negotiable)

Only picks with **strictly positive expected value** (`ev > 0`) may:

1. Appear in dashboard / lab pick tables and top-play strips  
2. Be persisted into the `picks` table (`run_predictions`, `golf_model_service`, lab log, market backfill)  
3. Receive `pick_outcomes` rows when a tournament is graded  

Negative or zero-EV lines may appear in **diagnostics** (`failed_candidates`) but are never graded and never counted in trust metrics.

Scoring (`src/learning.py`):

- Skips rows with `ev <= 0` and logs `skipped_non_positive_ev`  
- `model_hit` is `1` when the bet wins, else `0` (no inverted logic for negative EV)

## Pick sources

| Source | UI label | Grading filter (`pick_source`) |
|--------|----------|--------------------------------|
| `cockpit`, `ui_display` | Dashboard | `cockpit` |
| `lab_sandbox`, `lab_sandbox_candidate` | Lab | `lab` |
| (all) | All | `all` |

## Trust strip (`/grading`, `/track-record`)

Rendered by `GradingTrustStrip` with metrics from `buildGradingTrustMetrics()`:

| Cell | Meaning |
|------|---------|
| Last graded | `last_graded_at` from latest graded tournament in history or dashboard |
| +EV picks | Combined graded pick count from history summary (all persisted picks are +EV) |
| Ungraded +EV | `picks_count - graded_pick_count` on `latest_graded_tournament`, or operator signal when `latest_completed_event` ≠ graded event |

When **Ungraded +EV > 0**, show banner `data-testid="grading-ungraded-banner"` prompting **Grade event** in the shell header.

## Auto-grade path

After schedule ingest marks an event complete, `backtester/dashboard_runtime.py` may auto-grade when tracked picks exist and `graded_count < picks_count`. Operators should still verify the trust strip after each week.

## Operator weekly checklist

1. Confirm live snapshot ran through the completed event.  
2. Open `/grading` — trust strip shows **Ungraded +EV = 0** (or run **Grade event** until clear).  
3. Toggle **Dashboard** vs **Lab** source and confirm P&L matches expectations.  
4. Spot-check expanded event rows: every graded pick has `ev > 0` in the grid.  
5. Run `python3 -m pytest tests/test_learning.py tests/test_grading_integration.py -q`.  
6. Run `cd frontend && npm run test -- grading-trust legacy-routes`.

## Frontend tests

- `frontend/src/lib/grading-trust.test.ts` — metric builder  
- `frontend/src/pages/legacy-routes.test.tsx` — trust strip + banner + source toggle  
- `frontend/src/__fixtures__/*.json` — stable fixture contract (`fixtures.snapshot.test.ts`)
