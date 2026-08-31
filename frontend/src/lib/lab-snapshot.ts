import type { LiveRefreshSnapshot } from "@/lib/types"

/**
 * Build a snapshot object whose ``live_tournament`` / ``upcoming_tournament`` keys
 * point at parallel lab lane sections (for `/lab` board hydration).
 * Returns null when lab sections are absent or both null (lane disabled / failed).
 * Never copies Champion/production boards into the lab lane.
 */
export const mergeLabSnapshotSections = (snapshot: LiveRefreshSnapshot | null): LiveRefreshSnapshot | null => {
  if (!snapshot) {
    return null
  }
  if (!("lab_live_tournament" in snapshot) && !("lab_upcoming_tournament" in snapshot)) {
    return null
  }
  const ll = snapshot.lab_live_tournament
  const lu = snapshot.lab_upcoming_tournament
  if (ll == null && lu == null) {
    return null
  }
  return {
    ...snapshot,
    live_tournament: ll ?? undefined,
    upcoming_tournament: lu ?? undefined,
  }
}
