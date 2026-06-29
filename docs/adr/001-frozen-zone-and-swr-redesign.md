# ADR 001: Frozen Zone and Stale-While-Revalidate Redesign

**Status:** Accepted  
**Date:** 2026-06-29

## Context

Dashboard pick outputs must remain identical while we fix operator UX (perf, trust, analytics). The live snapshot API currently fail-closes on stale data, leaving an empty board despite last-good data on disk and in the browser.

## Decision

1. **Frozen zone:** Prediction model paths listed in `docs/frozen-zone-paths.txt` cannot change without `frozen-zone-override` PR label. CI job `frozen-zone-guard` enforces this.

2. **Hybrid SWR:**
   - `GET /api/live-refresh/summary` — always serves last-good snapshot from disk with honest `data_state` (`fresh` | `stale`).
   - `GET /api/live-refresh/snapshot` — remains fail-closed for contract integrity on full board.
   - Client: `displaySnapshot = full ?? summary ?? sessionStorage ?? IndexedDB`.

3. **Background ops jobs:** Grade and refresh report progress via SQLite `ops_jobs` table; shell shows instant feedback.

## Consequences

- Operators see data instantly on tab start; stale state is visible, not hidden.
- Model/composite logic stays untouched; serve/cache/query layers change.
