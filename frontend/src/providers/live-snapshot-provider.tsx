import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { mergeLabSnapshotSections } from "@/lib/lab-snapshot"
import { POLLING, SUSTAINED_FAILURE_THRESHOLD } from "@/lib/query-polling"
import type {
  LiveRefreshSnapshot,
  LiveRefreshSnapshotResponse,
  LiveRefreshStatusResponse,
  LiveTournamentSnapshot,
} from "@/lib/types"
import { readWarmSnapshotEnvelope, writeWarmSnapshotEnvelope } from "@/lib/warm-snapshot"

export type RuntimeStatus = {
  label: string
  tone: "good" | "warn" | "bad"
}

export type LiveSnapshotContextValue = {
  envelope: LiveRefreshSnapshotResponse | undefined
  snapshot: LiveRefreshSnapshot | null
  warmSnapshot: LiveRefreshSnapshot | null
  displaySnapshot: LiveRefreshSnapshot | null
  labSnapshotMerged: LiveRefreshSnapshot | null
  liveTournament: LiveTournamentSnapshot | undefined
  upcomingTournament: LiveTournamentSnapshot | undefined
  labLiveTournament: LiveTournamentSnapshot | null | undefined
  labUpcomingTournament: LiveTournamentSnapshot | null | undefined
  isLiveActive: boolean
  ageSeconds: number | null
  isLoading: boolean
  isFetching: boolean
  isError: boolean
  error: Error | null
  failureCount: number
  sustainedFailure: boolean
  runtimeStatus: RuntimeStatus
  liveRuntimeRunning: boolean
  liveRefreshStatus: LiveRefreshStatusResponse | undefined
  snapshotNoticeBase: string | null
}

const LiveSnapshotContext = createContext<LiveSnapshotContextValue | null>(null)

function useTabPollingSuspended(): boolean {
  return useSyncExternalStore(
    (onStoreChange) => {
      if (typeof document === "undefined") return () => {}
      const onVis = () => onStoreChange()
      document.addEventListener("visibilitychange", onVis)
      return () => document.removeEventListener("visibilitychange", onVis)
    },
    () => (typeof document !== "undefined" ? document.visibilityState === "hidden" : false),
    () => false,
  )
}

export type LiveSnapshotProviderProps = {
  children: ReactNode
  manualRefreshPending?: boolean
  uiAlert?: string | null
}

export function LiveSnapshotProvider({
  children,
  manualRefreshPending = false,
  uiAlert = null,
}: LiveSnapshotProviderProps) {
  const tabPollingSuspended = useTabPollingSuspended()
  const warmEnvelope = useMemo(() => readWarmSnapshotEnvelope(), [])

  const liveSnapshotQuery = useQuery({
    queryKey: ["live-refresh-snapshot"],
    queryFn: api.getLiveRefreshSnapshot,
    refetchInterval: tabPollingSuspended ? false : POLLING.liveSnapshot,
    placeholderData: keepPreviousData,
    initialData: warmEnvelope ?? undefined,
  })

  const liveRefreshStatusQuery = useQuery({
    queryKey: ["live-refresh-status", manualRefreshPending],
    queryFn: api.getLiveRefreshStatus,
    refetchInterval: (query) => {
      if (tabPollingSuspended) return false
      const data = query.state.data
      const pr = data?.status?.progress?.refresh_state
      if (manualRefreshPending || data?.status?.running || pr === "busy") {
        return POLLING.liveRefreshStatusBusy
      }
      return POLLING.liveRefreshStatusIdle
    },
    placeholderData: keepPreviousData,
  })

  const envelope = liveSnapshotQuery.data
  const snapshot = envelope?.snapshot ?? null
  const warmSnapshot = warmEnvelope?.snapshot ?? null
  const displaySnapshot = snapshot ?? warmSnapshot

  useEffect(() => {
    if (!liveSnapshotQuery.data?.snapshot) return
    writeWarmSnapshotEnvelope(liveSnapshotQuery.data)
  }, [liveSnapshotQuery.data])

  const labSnapshotMerged = useMemo(() => mergeLabSnapshotSections(snapshot), [snapshot])

  const snapshotSustainedFailure =
    liveSnapshotQuery.isError && liveSnapshotQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD
  const statusSustainedFailure =
    liveRefreshStatusQuery.isError &&
    liveRefreshStatusQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD

  const liveRuntimeRunning = Boolean(liveRefreshStatusQuery.data?.status?.running)

  const runtimeStatus = useMemo<RuntimeStatus>(() => {
    if (statusSustainedFailure || snapshotSustainedFailure) {
      return { label: "Runtime error", tone: "bad" }
    }
    if (!liveRuntimeRunning) {
      return { label: "Offline", tone: "warn" }
    }
    if (envelope?.stale_reason) {
      return { label: "Degraded", tone: "warn" }
    }
    return { label: "Live", tone: "good" }
  }, [
    statusSustainedFailure,
    snapshotSustainedFailure,
    liveRuntimeRunning,
    envelope?.stale_reason,
  ])

  const snapshotNoticeBase =
    snapshotSustainedFailure
      ? "Live snapshot request failed. Retry after checking API health."
      : envelope?.stale_reason ?? envelope?.fallback_reason ?? uiAlert

  const value = useMemo<LiveSnapshotContextValue>(
    () => ({
      envelope,
      snapshot,
      warmSnapshot,
      displaySnapshot,
      labSnapshotMerged,
      liveTournament: displaySnapshot?.live_tournament,
      upcomingTournament: displaySnapshot?.upcoming_tournament,
      labLiveTournament: displaySnapshot?.lab_live_tournament,
      labUpcomingTournament: displaySnapshot?.lab_upcoming_tournament,
      isLiveActive: Boolean(displaySnapshot?.live_tournament?.active),
      ageSeconds: envelope?.age_seconds ?? null,
      isLoading: liveSnapshotQuery.isLoading,
      isFetching: liveSnapshotQuery.isFetching,
      isError: liveSnapshotQuery.isError,
      error: liveSnapshotQuery.error instanceof Error ? liveSnapshotQuery.error : null,
      failureCount: liveSnapshotQuery.failureCount,
      sustainedFailure: snapshotSustainedFailure,
      runtimeStatus,
      liveRuntimeRunning,
      liveRefreshStatus: liveRefreshStatusQuery.data,
      snapshotNoticeBase,
    }),
    [
      envelope,
      snapshot,
      warmSnapshot,
      displaySnapshot,
      labSnapshotMerged,
      liveSnapshotQuery.isLoading,
      liveSnapshotQuery.isFetching,
      liveSnapshotQuery.isError,
      liveSnapshotQuery.error,
      liveSnapshotQuery.failureCount,
      snapshotSustainedFailure,
      runtimeStatus,
      liveRuntimeRunning,
      liveRefreshStatusQuery.data,
      snapshotNoticeBase,
    ],
  )

  return <LiveSnapshotContext.Provider value={value}>{children}</LiveSnapshotContext.Provider>
}

export function useLiveSnapshot(): LiveSnapshotContextValue {
  const ctx = useContext(LiveSnapshotContext)
  if (!ctx) {
    throw new Error("useLiveSnapshot must be used within LiveSnapshotProvider")
  }
  return ctx
}
