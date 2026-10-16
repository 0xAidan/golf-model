import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { mergeLabSnapshotSections } from "@/lib/lab-snapshot"
import { SUSTAINED_FAILURE_THRESHOLD } from "@/lib/query-polling"
import type {
  LiveRefreshSnapshot,
  LiveRefreshSnapshotResponse,
  LiveRefreshStatusResponse,
  LiveTournamentSnapshot,
} from "@/lib/types"
import { readIdbWarmSnapshotEnvelope, writeIdbWarmSnapshotEnvelope } from "@/lib/warm-snapshot-idb"
import { readWarmSnapshotEnvelope, writeWarmSnapshotEnvelope } from "@/lib/warm-snapshot"
import { IDLE_SNAPSHOT_POLL_MS, refreshIsActive, snapshotPollInterval, statusPollInterval } from "./live-snapshot-polling"

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
  dbUnavailable: boolean
  dbRestoreInProgress: boolean
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
  const [lastGoodEnvelope, setLastGoodEnvelope] = useState<LiveRefreshSnapshotResponse | null>(null)

  useEffect(() => {
    void readIdbWarmSnapshotEnvelope().then(setIdbEnvelope)
  }, [])

  const liveRefreshStatusQuery = useQuery({
    // Share the same status cache as the results/tools panels. Manual refresh
    // changes cadence, not the identity of the resource being requested.
    queryKey: ["live-refresh-status"],
    queryFn: api.getLiveRefreshStatus,
    enabled: !tabPollingSuspended,
    refetchInterval: query => statusPollInterval(query.state.data, manualRefreshPending, tabPollingSuspended),
    placeholderData: keepPreviousData,
  })
  const refreshing = refreshIsActive(liveRefreshStatusQuery.data, manualRefreshPending)

  const liveSnapshotQuery = useQuery({
    queryKey: ["live-refresh-snapshot"],
    queryFn: api.getLiveRefreshSnapshot,
    enabled: !tabPollingSuspended,
    refetchInterval: query => snapshotPollInterval({
      envelope: query.state.data,
      updatedAt: query.state.dataUpdatedAt,
      refreshing,
      hidden: tabPollingSuspended,
    }),
    placeholderData: keepPreviousData,
    initialData: warmEnvelope ?? idbEnvelope ?? undefined,
    initialDataUpdatedAt: 0,
  })
  const wasRefreshing = useRef(refreshing)
  const refetchSnapshot = liveSnapshotQuery.refetch
  useEffect(() => {
    // Fetch the completed cycle immediately rather than switching to the idle
    // interval while the screen still holds the previous cycle's snapshot.
    if (wasRefreshing.current && !refreshing && !tabPollingSuspended) {
      void refetchSnapshot()
    }
    wasRefreshing.current = refreshing
  }, [refreshing, tabPollingSuspended, refetchSnapshot])

  // The "summary" contains another full snapshot. Fetch it only to recover
  // display context when the authoritative contract cannot provide a board.
  const summaryNeeded = !liveSnapshotQuery.isPending
    && (liveSnapshotQuery.isError || !liveSnapshotQuery.data?.snapshot || liveSnapshotQuery.data?.ok === false)
  const summaryQuery = useQuery({
    queryKey: ["live-refresh-summary"],
    queryFn: api.getLiveRefreshSummary,
    enabled: !tabPollingSuspended && summaryNeeded,
    staleTime: IDLE_SNAPSHOT_POLL_MS,
    refetchInterval: !tabPollingSuspended && summaryNeeded ? IDLE_SNAPSHOT_POLL_MS : false,
    placeholderData: keepPreviousData,
  })

  const receivedEnvelope = liveSnapshotQuery.data?.snapshot
    ? liveSnapshotQuery.data
    : summaryNeeded && summaryQuery.data?.snapshot ? summaryQuery.data : null
  // Retain the last complete payload when a later contract intentionally hides
  // stale rows. React Query shares unchanged snapshot objects between polls;
  // age-only envelope changes need neither another state update nor disk writes.
  if (receivedEnvelope?.snapshot && receivedEnvelope.snapshot !== lastGoodEnvelope?.snapshot) {
    setLastGoodEnvelope(receivedEnvelope)
  }

  const envelope = liveSnapshotQuery.data
  const summaryEnvelope = summaryNeeded ? summaryQuery.data : undefined
  const contractSnapshot = envelope?.ok === false ? null : envelope?.snapshot ?? null
  const summarySnapshot = summaryEnvelope?.snapshot ?? null
  const warmSnapshot =
    lastGoodEnvelope?.snapshot ?? warmEnvelope?.snapshot ?? idbEnvelope?.snapshot ?? null
  const displaySnapshot = contractSnapshot ?? summarySnapshot ?? warmSnapshot
  const dataState =
    envelope?.data_state ?? summaryEnvelope?.data_state ?? (displaySnapshot ? "stale" : null)
  const operatorMessage = envelope?.operator_message ?? summaryEnvelope?.operator_message ?? null
  const splitBrainSuspected = Boolean(
    envelope?.split_brain_suspected ||
      summaryEnvelope?.split_brain_suspected ||
      envelope?.data_state === "split_brain",
  )
  const dbUnavailable = Boolean(
    envelope?.db_unavailable ||
      summaryEnvelope?.db_unavailable ||
      liveRefreshStatusQuery.data?.db_unavailable,
  )
  const dbRestoreInProgress = Boolean(
    envelope?.db_restore_in_progress || summaryEnvelope?.db_restore_in_progress,
  )
  const staleAfterSeconds =
    envelope?.stale_after_seconds ?? summaryEnvelope?.stale_after_seconds ?? null

  useEffect(() => {
    if (!lastGoodEnvelope?.snapshot) return
    writeWarmSnapshotEnvelope(lastGoodEnvelope)
    void writeIdbWarmSnapshotEnvelope(lastGoodEnvelope)
  }, [lastGoodEnvelope])

  const labSnapshotMerged = useMemo(() => mergeLabSnapshotSections(displaySnapshot), [displaySnapshot])

  const snapshotSustainedFailure =
    liveSnapshotQuery.isError && liveSnapshotQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD
  const statusSustainedFailure =
    liveRefreshStatusQuery.isError &&
    liveRefreshStatusQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD

  const liveRuntimeRunning = Boolean(liveRefreshStatusQuery.data?.status?.running)
  const heartbeatAgeSeconds = liveRefreshStatusQuery.data?.status?.heartbeat_age_seconds

  const runtimeStatus = useMemo<RuntimeStatus>(() => {
    if (dbUnavailable) {
      return { label: "DB down", tone: "bad" }
    }
    if (splitBrainSuspected) {
      return { label: "Path mismatch", tone: "bad" }
    }
    if (statusSustainedFailure || snapshotSustainedFailure) {
      return { label: "Runtime error", tone: "bad" }
    }
    if (
      heartbeatAgeSeconds != null &&
      heartbeatAgeSeconds > 900 &&
      liveRuntimeRunning
    ) {
      return { label: "Worker stale", tone: "bad" }
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
    dbUnavailable,
    splitBrainSuspected,
    statusSustainedFailure,
    snapshotSustainedFailure,
    dataState,
    liveRuntimeRunning,
    heartbeatAgeSeconds,
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
      dbUnavailable,
      dbRestoreInProgress,
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
      dbUnavailable,
      dbRestoreInProgress,
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
