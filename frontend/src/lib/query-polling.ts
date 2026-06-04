/** Centralized polling intervals for TanStack Query (ms). */
export const POLLING = {
  dashboard: 30_000,
  liveSnapshot: 10_000,
  liveRefreshStatusIdle: 15_000,
  liveRefreshStatusBusy: 2_500,
  playerProfileStale: 60_000,
  queryDefaultStale: 15_000,
} as const

export const SUSTAINED_FAILURE_THRESHOLD = 2
