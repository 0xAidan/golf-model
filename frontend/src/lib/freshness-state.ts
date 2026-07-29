export type FreshnessState = "fresh" | "updating" | "stale" | "offline" | "error"

export type FreshnessInput = {
  dataState?: string | null
  ageSeconds?: number | null
  staleAfterSeconds?: number | null
  isFetching: boolean
  refreshQueued?: boolean
  /** True when boards already have a usable snapshot — background polls stay quiet. */
  hasDisplayData?: boolean
  isOnline: boolean
  isError: boolean
  splitBrain?: boolean
}

export const deriveFreshnessState = (input: FreshnessInput): FreshnessState => {
  if (!input.isOnline) return "offline"
  if (input.splitBrain || input.isError) return "error"
  // Manual refresh / queue always surfaces; background poll only when nothing usable yet.
  if (input.refreshQueued) return "updating"
  if (input.isFetching && !input.hasDisplayData) return "updating"
  if (input.dataState === "stale") return "stale"
  if (
    input.ageSeconds != null &&
    input.staleAfterSeconds != null &&
    input.ageSeconds > input.staleAfterSeconds
  ) {
    return "stale"
  }
  return "fresh"
}

export const freshnessLabel = (
  state: FreshnessState,
  ageSeconds: number | null,
  formatAge: (seconds: number | null) => string,
): string => {
  const age = formatAge(ageSeconds)
  switch (state) {
    case "fresh":
      return `Live · ${age}`
    case "updating":
      return "Updating…"
    case "stale":
      return `Stale · ${age}`
    case "offline":
      return "Offline — showing last data"
    case "error":
      return "Update failed — check System"
    default: {
      const _exhaustive: never = state
      return _exhaustive
    }
  }
}
