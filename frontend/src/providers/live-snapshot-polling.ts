import { POLLING } from "@/lib/query-polling"
import type { LiveRefreshSnapshotResponse, LiveRefreshStatusResponse } from "@/lib/types"

export const IDLE_SNAPSHOT_POLL_MS = 60_000
const ACTIVE_REFRESH_STATES = new Set(["queued", "running", "busy", "refreshing"])

export function refreshIsActive(status: LiveRefreshStatusResponse | undefined, manualRefreshPending: boolean): boolean {
  if (manualRefreshPending) return true
  // `running` means the long-lived worker is alive, including between hourly
  // cycles. Only actual refresh progress should trigger rapid status polling.
  return [status?.status?.refresh_state, status?.status?.progress?.refresh_state]
    .some(state => ACTIVE_REFRESH_STATES.has(state?.toLowerCase() ?? ""))
}

export function statusPollInterval(
  status: LiveRefreshStatusResponse | undefined,
  manualRefreshPending: boolean,
  hidden: boolean,
): number | false {
  if (hidden) return false
  return refreshIsActive(status, manualRefreshPending)
    ? POLLING.liveRefreshStatusBusy
    : POLLING.liveRefreshStatusIdle
}

export function snapshotPollInterval({
  envelope,
  updatedAt,
  refreshing,
  hidden,
  now = Date.now(),
}: {
  envelope: LiveRefreshSnapshotResponse | undefined
  updatedAt: number
  refreshing: boolean
  hidden: boolean
  now?: number
}): number | false {
  if (hidden) return false
  const interval = refreshing || envelope?.snapshot?.live_tournament?.active
    ? POLLING.liveSnapshot
    : IDLE_SNAPSHOT_POLL_MS
  const age = envelope?.age_seconds
  const staleAfter = envelope?.stale_after_seconds
  if (envelope?.ok && envelope.snapshot && envelope.data_state !== "stale"
    && updatedAt > 0 && typeof age === "number" && Number.isFinite(age)
    && typeof staleAfter === "number" && Number.isFinite(staleAfter)) {
    // Do not let the slower idle cadence carry a fresh server decision beyond
    // its deadline. Use the received age, avoiding client/server clock skew.
    const untilStale = updatedAt + (staleAfter - age + 1) * 1_000 - now
    return Math.min(interval, Math.max(1_000, untilStale))
  }
  return interval
}
