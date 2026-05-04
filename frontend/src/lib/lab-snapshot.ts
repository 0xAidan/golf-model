import type { LiveRefreshSnapshot } from "@/lib/types"

/**
 * Build a snapshot object whose ``live_tournament`` / ``upcoming_tournament`` keys
 * point at parallel lab lane sections (for cockpit-lab hydration).
 * Returns null when lab sections are absent or both null (lane disabled / failed).
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
  if (ll === null && lu === null) {
    return null
  }
  return {
    ...snapshot,
    live_tournament: ll != null ? ll : snapshot.live_tournament,
    upcoming_tournament: lu != null ? lu : snapshot.upcoming_tournament,
  }
}
