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
  _ageSeconds: number | null,
  _formatAge: (seconds: number | null) => string,
): string => {
  switch (state) {
    case "fresh":
      return "LIVE"
    case "updating":
      return "UPDATING"
    case "stale":
      return "STALE"
    case "offline":
    case "error":
      return "DOWN"
    default: {
      const _exhaustive: never = state
      return _exhaustive
    }
  }
}
