# Live Dashboard Validation Summary

## Scope

This package validates live dashboard reliability across event context, rankings provenance, and matchup visibility.

## What Is Now Deterministic

- Live/upcoming snapshot sections carry explicit provenance metadata:
  - `source_event_id`
  - `source_event_name`
  - `source_card_path`
  - `ranking_source`
- When no event is currently live, the live section attempts to load rankings from the previous event card snapshot (`ranking_source=previous_card_snapshot`) before falling back.
- Matchup generation now emits structured diagnostics and classifier states:
  - `no_market_posted_yet`
  - `market_available_no_edges`
  - `pipeline_error`
  - `edges_available`

## Operator Guarantees

- Empty matchup surfaces are no longer ambiguous. Operators can distinguish:
  - no lines posted yet,
  - lines posted but no qualifying edges,
  - genuine pipeline failures.
- UI now reports raw-vs-filtered matchup counts and snapshot classifier state directly in the board.
- Board source is explicit (`active snapshot tab` vs `stored manual run`) to prevent silent stale-run shadowing.

## Remaining Expected Variability

- Early-week books can legitimately publish zero matchup rows.
- Market availability can differ between tournament and round-matchup markets depending on cadence window and book coverage.
- If card artifacts for the latest completed event are missing, ranking provenance falls back to current-model data and is labeled accordingly.

## Verification Checklist

- Backend:
  - `python3 -m pytest tests/test_matchup_value.py tests/test_live_refresh_runtime.py tests/test_simple_dashboard.py`
- Frontend:
  - `npm run lint && npm run build` in `frontend/`
- Runtime sanity:
  - `GET /api/live-refresh/snapshot` shows diagnostics and provenance fields.
  - Empty matchup state maps to an explicit classifier, not a generic message.
