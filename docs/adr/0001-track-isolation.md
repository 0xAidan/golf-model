# ADR 0001: Champion and Challenger Track Isolation

- **Status:** Accepted
- **Date:** 2026-07-31
- **Decision owners:** Operator Site Recovery

## Context

The operator site presents a live reference model and a separately evaluated
candidate model. Mixing the two would make current decisions, historical
evaluation, and provenance untrustworthy.

## Decision

Champion and Challenger are independent tracks.

1. Dashboard reads Champion data only; Lab reads Challenger data only.
2. Lab has no Champion-to-Challenger fallback. If Challenger data is absent,
   the UI must show that unavailable state.
3. Every track-bound API response, cache entry, URL/query state, and Results
   record retains its track provenance.
4. Compare is restricted to same-event disagreement. Results is restricted to
   historical A/B evidence.
5. The site does not declare a winner. Promotion remains a separately governed
   operating decision with auditable evidence.

## Consequences

- Missing Challenger data is visible rather than silently substituted.
- Caches must use a track-aware key; route and query state must not reuse
  Champion values for Lab.
- Results joins and exports must preserve both track identifier and source
  provenance.
- Any future shortcut that introduces fallback is a contract violation and
  needs an explicit ADR superseding this one.

## References

- [`../../CONTEXT.md`](../../CONTEXT.md)
- [`../frontend-recovery/acceptance.md`](../frontend-recovery/acceptance.md)
