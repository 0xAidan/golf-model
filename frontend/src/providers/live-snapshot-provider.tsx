import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
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
import { readIdbWarmSnapshotEnvelope, writeIdbWarmSnapshotEnvelope } from "@/lib/warm-snapshot-idb"
import { readWarmSnapshotEnvelope, writeWarmSnapshotEnvelope } from "@/lib/warm-snapshot"

export type RuntimeStatus = {
  label: string
  tone: "good" | "warn" | "bad"
}

export type LiveSnapshotContextValue = {
  envelope: LiveRefreshSnapshotResponse | undefined
  summaryEnvelope: LiveRefreshSnapshotResponse | undefined
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
  staleAfterSeconds: number | null
  dataState?: string | null
  operatorMessage?: string | null
  splitBrainSuspected?: boolean
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
  const [idbEnvelope, setIdbEnvelope] = useState<LiveRefreshSnapshotResponse | null>(null)

  useEffect(() => {
    void readIdbWarmSnapshotEnvelope().then(setIdbEnvelope)
  }, [])

  const summaryQuery = useQuery({
    queryKey: ["live-refresh-summary"],
    queryFn: api.getLiveRefreshSummary,
    refetchInterval: tabPollingSuspended ? false : POLLING.liveSnapshot,
    placeholderData: keepPreviousData,
    initialData: warmEnvelope ?? idbEnvelope ?? undefined,
  })

  const liveSnapshotQuery = useQuery({
    queryKey: ["live-refresh-snapshot"],
    queryFn: api.getLiveRefreshSnapshot,
    refetchInterval: tabPollingSuspended ? false : POLLING.liveSnapshot,
    placeholderData: keepPreviousData,
    initialData: warmEnvelope ?? idbEnvelope ?? undefined,
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
  const summaryEnvelope = summaryQuery.data
  const contractSnapshot = envelope?.ok === false ? null : envelope?.snapshot ?? null
  const summarySnapshot = summaryEnvelope?.snapshot ?? null
  const warmSnapshot =
    warmEnvelope?.snapshot ?? idbEnvelope?.snapshot ?? null
  const displaySnapshot = contractSnapshot ?? summarySnapshot ?? warmSnapshot
  const dataState =
    envelope?.data_state ?? summaryEnvelope?.data_state ?? (displaySnapshot ? "stale" : null)
  const operatorMessage = envelope?.operator_message ?? summaryEnvelope?.operator_message ?? null
  const splitBrainSuspected = Boolean(
    envelope?.split_brain_suspected ||
      summaryEnvelope?.split_brain_suspected ||
      envelope?.data_state === "split_brain",
  )
  const staleAfterSeconds =
    envelope?.stale_after_seconds ?? summaryEnvelope?.stale_after_seconds ?? null

  useEffect(() => {
    const toPersist = liveSnapshotQuery.data?.snapshot
      ? liveSnapshotQuery.data
      : summaryQuery.data?.snapshot
        ? summaryQuery.data
        : null
    if (!toPersist?.snapshot) return
    writeWarmSnapshotEnvelope(toPersist)
    void writeIdbWarmSnapshotEnvelope(toPersist)
  }, [liveSnapshotQuery.data, summaryQuery.data])

  const labSnapshotMerged = useMemo(() => mergeLabSnapshotSections(displaySnapshot), [displaySnapshot])

  const snapshotSustainedFailure =
    liveSnapshotQuery.isError && liveSnapshotQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD
  const statusSustainedFailure =
    liveRefreshStatusQuery.isError &&
    liveRefreshStatusQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD

  const liveRuntimeRunning = Boolean(liveRefreshStatusQuery.data?.status?.running)

  const runtimeStatus = useMemo<RuntimeStatus>(() => {
    if (splitBrainSuspected) {
      return { label: "Path mismatch", tone: "bad" }
    }
    if (statusSustainedFailure || snapshotSustainedFailure) {
      return { label: "Runtime error", tone: "bad" }
    }
    if (dataState === "stale") {
      return { label: "Stale data", tone: "warn" }
    }
    if (!liveRuntimeRunning) {
      return { label: "Offline", tone: "warn" }
    }
    if (envelope?.stale_reason) {
      return { label: "Degraded", tone: "warn" }
    }
    return { label: "Live", tone: "good" }
  }, [
    splitBrainSuspected,
    statusSustainedFailure,
    snapshotSustainedFailure,
    dataState,
    liveRuntimeRunning,
    envelope?.stale_reason,
  ])

  const snapshotNoticeBase =
    splitBrainSuspected
      ? operatorMessage ??
        "Dashboard and refresh worker may be using different data folders. Rankings are hidden."
      : snapshotSustainedFailure
        ? "Live snapshot request failed. Retry after checking System health."
        : operatorMessage ?? envelope?.stale_reason ?? envelope?.fallback_reason ?? uiAlert

  const ageSeconds = envelope?.age_seconds ?? summaryEnvelope?.age_seconds ?? null

  const value = useMemo<LiveSnapshotContextValue>(
    () => ({
      envelope,
      summaryEnvelope,
      snapshot: contractSnapshot,
      warmSnapshot,
      displaySnapshot,
      labSnapshotMerged,
      liveTournament: displaySnapshot?.live_tournament,
      upcomingTournament: displaySnapshot?.upcoming_tournament,
      labLiveTournament: displaySnapshot?.lab_live_tournament,
      labUpcomingTournament: displaySnapshot?.lab_upcoming_tournament,
      isLiveActive: Boolean(displaySnapshot?.live_tournament?.active),
      ageSeconds,
      staleAfterSeconds,
      dataState,
      operatorMessage,
      splitBrainSuspected,
      isLoading: liveSnapshotQuery.isLoading && !displaySnapshot,
      isFetching: liveSnapshotQuery.isFetching || summaryQuery.isFetching,
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
      summaryEnvelope,
      contractSnapshot,
      warmSnapshot,
      displaySnapshot,
      labSnapshotMerged,
      liveSnapshotQuery.isLoading,
      liveSnapshotQuery.isFetching,
      liveSnapshotQuery.isError,
      liveSnapshotQuery.error,
      liveSnapshotQuery.failureCount,
      summaryQuery.isFetching,
      snapshotSustainedFailure,
      runtimeStatus,
      liveRuntimeRunning,
      liveRefreshStatusQuery.data,
      snapshotNoticeBase,
      ageSeconds,
      staleAfterSeconds,
      dataState,
      operatorMessage,
      splitBrainSuspected,
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
