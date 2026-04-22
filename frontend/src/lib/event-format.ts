/**
 * Frontend mirror of the backend `event_format` contract (see
 * `src/event_format.py`). Kept in `lib/` rather than co-located with the
 * component so Fast Refresh stays happy (components files should export
 * components only).
 */

export type EventFormat = "individual" | "team"

/**
 * Predicate helper so call-sites consistently decide whether to render the
 * team-event notice. The `"team"` string is the single source of truth
 * agreed between backend (`src/event_format.py::EVENT_FORMAT_TEAM`) and
 * frontend renderers.
 */
export function isTeamEvent(
  snapshot: { event_format?: string | null } | null | undefined,
): boolean {
  return snapshot?.event_format === "team"
}
