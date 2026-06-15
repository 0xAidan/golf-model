import { Suspense, useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Route, Routes, Navigate, useLocation, useParams } from "react-router-dom"
import { RefreshCw, Star } from "lucide-react"
import { toast } from "sonner"

import { CommandMenu, CommandMenuTrigger } from "@/components/command-menu"
import { CockpitModeSwitch } from "@/components/cockpit/workspace"
import { MonitoringShell } from "@/components/monitoring/monitoring-shell"
import { RouteErrorBoundaryGate } from "@/components/route-error-boundary-gate"
import { SidebarStatus } from "@/components/shell"
import { SnapshotChip } from "@/components/snapshot-chip"
import { useLiveRefreshRuntime } from "@/hooks/use-live-refresh-runtime"
import { usePredictionTab } from "@/hooks/use-prediction-tab"
import { api } from "@/lib/api"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import { formatDateTime } from "@/lib/format"
import { lazyWithRetry } from "@/lib/lazy-import"
import {
  buildHydratedPredictionRun,
  collectBooksForFilter,
  flattenSecondaryBets,
  NON_BOOK_SOURCES,
  normalizeSportsbook,
} from "@/lib/prediction-board"
import { POLLING } from "@/lib/query-polling"
import { useLocalStorageState } from "@/lib/storage"
import type { CompositePlayer, FlattenedSecondaryBet, PredictionRunRequest, PredictionRunResponse } from "@/lib/types"
import { InteractionProvider } from "@/providers/interaction-provider"
import { LiveSnapshotProvider, useLiveSnapshot } from "@/providers/live-snapshot-provider"
import { CockpitLabPage } from "@/pages/cockpit-lab-page"
import { PredictionWorkspacePage, type PredictionWorkspacePageProps } from "@/pages/prediction-workspace-page"

// Code-split heavy / rarely-visited routes. The default "/" route
// (PredictionWorkspacePage) and the primary Picks route stay eager so the
// dashboard boots without a Suspense flicker. Players, Grading,
// Track Record, and Champion-Challenger are all secondary nav targets — the
// operator clicks into them, so a single network round-trip on first visit
// is acceptable and trims ~400-600 kB off the initial bundle.
const PlayersPage = lazyWithRetry(() =>
  import("@/pages/players-page").then((mod) => ({ default: mod.PlayersPage })),
)
const GradingPage = lazyWithRetry(() =>
  import("@/pages/legacy-routes").then((mod) => ({ default: mod.GradingPage })),
)
const TrackRecordPage = lazyWithRetry(() =>
  import("@/pages/legacy-routes").then((mod) => ({ default: mod.TrackRecordPage })),
)
const ChampionChallengerPage = lazyWithRetry(() =>
  import("@/pages/champion-challenger-page").then((mod) => ({
    default: mod.ChampionChallengerPage,
  })),
)
const LegacyModelPage = lazyWithRetry(() =>
  import("@/pages/legacy-model-page").then((mod) => ({ default: mod.LegacyModelPage })),
)
const DiagnosticsPage = lazyWithRetry(() =>
  import("@/pages/diagnostics-page").then((mod) => ({ default: mod.DiagnosticsPage })),
)
const ResultsPage = lazyWithRetry(() =>
  import("@/pages/results-page").then((mod) => ({ default: mod.ResultsPage })),
)
const SystemPage = lazyWithRetry(() =>
  import("@/pages/system-page").then((mod) => ({ default: mod.SystemPage })),
)
const ComparePage = lazyWithRetry(() =>
  import("@/pages/compare-page").then((mod) => ({ default: mod.ComparePage })),
)
const EvalPage = lazyWithRetry(() =>
  import("@/pages/eval-page").then((mod) => ({ default: mod.EvalPage })),
)

/** Deep-link wrapper: /players/:playerKey renders PlayersPage focused on that player. */
function PlayersDeepLink({ players }: { players: CompositePlayer[] }) {
  const { playerKey } = useParams<{ playerKey: string }>()
  return <PlayersPage key={playerKey} players={players} initialPlayerKey={playerKey ?? null} />
}

function RouteFallback() {
  return (
    <div className="route-suspense-fallback" data-testid="route-suspense-fallback">
      Loading…
    </div>
  )
}

const DEFAULT_REQUEST: PredictionRunRequest = {
  tour: "pga",
  tournament: "",
  course: "",
  mode: "full",
  enable_ai: true,
}

const RICH_PLAYER_PROFILES_ENABLED = import.meta.env.VITE_RICH_PLAYER_PROFILES !== "0"
/** Lab board + Lab picks routes on unless build sets `VITE_COCKPIT_LAB=0` (legacy env name). */
const COCKPIT_LAB_ENABLED = import.meta.env.VITE_COCKPIT_LAB !== "0"

function passesPositiveEv(ev: number | null | undefined, minEdge: number): boolean {
  return ev != null && ev > 0 && ev >= minEdge
}

function filterValueBet<T extends FlattenedSecondaryBet>(bet: T, minEdge: number, selectedBookSet: Set<string>): boolean {
  const betBook = normalizeSportsbook(bet.book)
  if (betBook && NON_BOOK_SOURCES.has(betBook)) return false
  if (!passesPositiveEv(bet.ev, minEdge)) return false
  if (selectedBookSet.size === 0) return true
  return betBook ? selectedBookSet.has(betBook) : false
}

export default function App() {
  const [manualRefreshPending, setManualRefreshPending] = useState(false)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

  return (
    <InteractionProvider>
      <LiveSnapshotProvider manualRefreshPending={manualRefreshPending} uiAlert={uiAlert}>
        <AppContent
          manualRefreshPending={manualRefreshPending}
          setManualRefreshPending={setManualRefreshPending}
          setUiAlert={setUiAlert}
        />
      </LiveSnapshotProvider>
    </InteractionProvider>
  )
}

function AppContent({
  manualRefreshPending,
  setManualRefreshPending,
  setUiAlert,
}: {
  manualRefreshPending: boolean
  setManualRefreshPending: (value: boolean) => void
  setUiAlert: (value: string | null) => void
}) {
  const queryClient = useQueryClient()
  const [predictionRequest] = useLocalStorageState<PredictionRunRequest>(
    "golf-model.prediction-request",
    DEFAULT_REQUEST,
  )
  const [predictionRun] = useLocalStorageState<PredictionRunResponse | null>(
    "golf-model.latest-prediction-run",
    null,
  )
  const [matchupSearch, setMatchupSearch] = useLocalStorageState("golf-model.matchup-search", "")
  const [minEdge, setMinEdge] = useLocalStorageState("golf-model.min-edge", 0.02)
  const [selectedBooks, setSelectedBooks] = useLocalStorageState<string[]>("golf-model.selected-books", [])
  const [selectedPlayerKey, setSelectedPlayerKey] = useLocalStorageState("golf-model.selected-player", "")
  const [refreshStartedAt, setRefreshStartedAt] = useState<number | null>(null)
  const [refreshElapsedSec, setRefreshElapsedSec] = useState<number | null>(null)
  const [pastReplayHeadline, setPastReplayHeadline] = useState<{ eventName: string; courseName?: string } | null>(
    null,
  )
  const [commandMenuOpen, setCommandMenuOpen] = useState(false)

  const location = useLocation()
  const {
    envelope: liveSnapshotEnvelope,
    snapshot: liveSnapshot,
    warmSnapshot,
    labSnapshotMerged,
    isLiveActive,
    ageSeconds: snapshotAgeSeconds,
    runtimeStatus,
    snapshotNoticeBase,
    liveRuntimeRunning,
    liveRefreshStatus,
  } = useLiveSnapshot()

  const isLegacyLabBoardPath =
    location.pathname === "/cockpit-lab" || location.pathname.startsWith("/cockpit-lab/")
  const isLabBoardRoute = location.pathname === "/lab" || isLegacyLabBoardPath
  const isLabPicksRoute = location.pathname.startsWith("/lab/picks")
  const labRouteActive = isLabBoardRoute || isLabPicksRoute

  const tabPollingSuspended = useSyncExternalStore(
    (onStoreChange) => {
      if (typeof document === "undefined") return () => {}
      const onVis = () => onStoreChange()
      document.addEventListener("visibilitychange", onVis)
      return () => document.removeEventListener("visibilitychange", onVis)
    },
    () => (typeof document !== "undefined" ? document.visibilityState === "hidden" : false),
    () => false,
  )

  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    refetchInterval: tabPollingSuspended ? false : POLLING.dashboard,
  })
  const gradingHistoryPickSource = labRouteActive ? "lab" : "cockpit"
  const gradingHistoryQuery = useQuery({
    queryKey: ["grading-history", gradingHistoryPickSource],
    queryFn: () => api.getGradingHistory({ pickSource: gradingHistoryPickSource }),
  })
  /** When the parallel lab lane is off, lab routes still hydrate from production snapshot so the UI is usable. */
  const labDisplaySnapshot = useMemo(() => {
    if (!labRouteActive) return null
    return labSnapshotMerged ?? liveSnapshot ?? null
  }, [labRouteActive, labSnapshotMerged, liveSnapshot])
  const labUsingProdSnapshotFallback = Boolean(labRouteActive && !labSnapshotMerged && liveSnapshot)
  /** Only one of lab_live / lab_upcoming populated — merged board mixes lab + production for the missing side. */
  const labLanePartialSections = Boolean(
    liveSnapshot &&
      ((liveSnapshot.lab_upcoming_tournament != null && liveSnapshot.lab_live_tournament == null) ||
        (liveSnapshot.lab_upcoming_tournament == null && liveSnapshot.lab_live_tournament != null)),
  )
  const snapshotNotice = snapshotNoticeBase
  const shellFreshnessLabel = snapshotAgeSecondsLabel(snapshotAgeSeconds)
  const { predictionTab, setPredictionTab } = usePredictionTab(isLiveActive)

  const hydratedRun = useMemo(() => {
    if (predictionTab === "past") return null
    return buildHydratedPredictionRun(liveSnapshot, predictionTab)
  }, [liveSnapshot, predictionTab])

  const effectivePredictionRun = useMemo(
    () => hydratedRun ?? predictionRun,
    [hydratedRun, predictionRun],
  )
  const visiblePredictionRun = predictionTab === "past" ? null : effectivePredictionRun

  const normalizedSelectedBooks = useMemo(
    () => selectedBooks.map((book) => normalizeSportsbook(book)).filter(Boolean),
    [selectedBooks],
  )
  const selectedBookSet = useMemo(() => new Set(normalizedSelectedBooks), [normalizedSelectedBooks])
  const prodProfileSection =
    predictionTab === "upcoming"
      ? liveSnapshot?.upcoming_tournament
      : predictionTab === "live"
          ? liveSnapshot?.live_tournament
          : null
  const availableBooks = useMemo(
    () => collectBooksForFilter(visiblePredictionRun, prodProfileSection?.diagnostics?.books_seen),
    [visiblePredictionRun, prodProfileSection?.diagnostics?.books_seen],
  )
  const profileSection =
    labRouteActive && labDisplaySnapshot
      ? predictionTab === "upcoming"
        ? labDisplaySnapshot.upcoming_tournament
        : predictionTab === "live"
            ? labDisplaySnapshot.live_tournament
            : null
      : prodProfileSection
  const profileTournamentId = profileSection?.tournament_id ?? visiblePredictionRun?.tournament_id
  const profileCourseNum = profileSection?.course_num ?? visiblePredictionRun?.course_num
  const hasProfileTournamentContext = profileTournamentId !== null && profileTournamentId !== undefined

  const playerProfileQuery = useQuery({
    queryKey: [
      "player-profile",
      labRouteActive ? "lab" : "dashboard",
      selectedPlayerKey,
      profileTournamentId,
      profileCourseNum,
    ],
    queryFn: () => {
      if (profileTournamentId === null || profileTournamentId === undefined) {
        throw new Error("Missing tournament context for player profile")
      }
      return api.getPlayerProfile(
        selectedPlayerKey,
        profileTournamentId,
        profileCourseNum,
      )
    },
    enabled:
      RICH_PLAYER_PROFILES_ENABLED &&
      Boolean(selectedPlayerKey && hasProfileTournamentContext),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  })

  const playerProfileState: "loading" | "ready" | "error" | "unavailable" = useMemo(() => {
    if (!RICH_PLAYER_PROFILES_ENABLED) {
      return "unavailable"
    }
    if (!selectedPlayerKey || !hasProfileTournamentContext) {
      return "unavailable"
    }
    if (playerProfileQuery.isError) {
      return "error"
    }
    const profileData = playerProfileQuery.data
    const dataMatchesPlayer = profileData?.player_key === selectedPlayerKey
    if (
      playerProfileQuery.isPending ||
      (!dataMatchesPlayer && (playerProfileQuery.isFetching || playerProfileQuery.isLoading))
    ) {
      return "loading"
    }
    if (dataMatchesPlayer && profileData) {
      return "ready"
    }
    return "unavailable"
  }, [
    hasProfileTournamentContext,
    playerProfileQuery.data,
    playerProfileQuery.isError,
    playerProfileQuery.isFetching,
    playerProfileQuery.isLoading,
    playerProfileQuery.isPending,
    selectedPlayerKey,
  ])
  const playerProfileErrorMessage =
    playerProfileQuery.error instanceof Error ? playerProfileQuery.error.message : undefined
  const selectedPlayerProfile = playerProfileQuery.data
  const handlePlayerProfileRetry = useCallback(() => {
    void playerProfileQuery.refetch()
  }, [playerProfileQuery])

  const gradeMutation = useMutation({
    mutationFn: () =>
      api.gradeLatestTournament(dashboardQuery.data?.latest_completed_event ?? undefined),
    onSuccess: () => {
      setUiAlert(null)
      toast.success("Event graded successfully")
      void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
      void queryClient.invalidateQueries({ queryKey: ["grading-history"] })
      void queryClient.invalidateQueries({ queryKey: ["grading-season"] })
      void queryClient.invalidateQueries({ queryKey: ["track-record"] })
    },
    onError: () => {
      const msg = "Grading failed. Check backend logs and retry."
      setUiAlert(msg)
      toast.error(msg)
    },
  })

  const refreshSnapshotMutation = useMutation({
    mutationFn: () => api.refreshLiveSnapshot(),
    onMutate: () => {
      setManualRefreshPending(true)
      setRefreshStartedAt(Date.now())
    },
    onSettled: () => {
      setManualRefreshPending(false)
      setRefreshStartedAt(null)
      setRefreshElapsedSec(null)
    },
    onSuccess: (payload) => {
      if (payload.accepted) {
        const msg =
          payload.operator_message ??
          payload.stale_reason ??
          "Refresh queued. Data will update when the worker finishes."
        setUiAlert(msg)
        toast.message(msg)
      } else if (payload.ok) {
        const generated = payload.generated_at ? formatDateTime(payload.generated_at) : "just now"
        const msg = `Snapshot refreshed (${generated}).`
        setUiAlert(msg)
        toast.success(msg)
      } else if (payload.busy) {
        const msg =
          payload.operator_message ??
          payload.stale_reason ??
          "A snapshot refresh is already running."
        setUiAlert(msg)
        toast.message(msg)
      } else {
        const msg =
          payload.operator_message ??
          payload.stale_reason ??
          "Manual refresh did not return a snapshot."
        setUiAlert(msg)
        toast.warning(msg)
      }
      void queryClient.invalidateQueries({ queryKey: ["live-refresh-status"] })
      void queryClient.invalidateQueries({ queryKey: ["live-refresh-snapshot"] })
    },
    onError: () => {
      const msg = "Manual refresh failed. Check runtime logs and try again."
      setUiAlert(msg)
      toast.error(msg)
    },
  })

  const liveProgress = liveRefreshStatus?.status?.progress
  const lrRefreshState = liveProgress?.refresh_state ?? liveRefreshStatus?.status?.refresh_state
  const refreshButtonDisabled =
    refreshSnapshotMutation.isPending || lrRefreshState === "running" || lrRefreshState === "busy"
  useEffect(() => {
    if (!refreshButtonDisabled || !refreshStartedAt) return
    const updateElapsed = () => {
      setRefreshElapsedSec(Math.max(0, Math.floor((Date.now() - refreshStartedAt) / 1000)))
    }
    updateElapsed()
    const id = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(id)
  }, [refreshButtonDisabled, refreshStartedAt])
  const refreshElapsedSecDisplay = refreshButtonDisabled && refreshStartedAt ? refreshElapsedSec : null

  const players = predictionTab === "past" ? [] : (effectivePredictionRun?.composite_results ?? [])

  const filteredMatchups = useMemo(() => {
    const sourceMatchups =
      visiblePredictionRun?.matchup_bets_all_books ??
      visiblePredictionRun?.matchup_bets ??
      []
    return sourceMatchups.filter((matchup) => {
      const matchupBook = normalizeSportsbook(matchup.book)
      if (NON_BOOK_SOURCES.has(matchupBook)) return false
      const passesBook = selectedBookSet.size === 0 || selectedBookSet.has(matchupBook)
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesBook && passesSearch && passesPositiveEv(matchup.ev, minEdge)
    })
  }, [
    visiblePredictionRun?.matchup_bets_all_books,
    visiblePredictionRun?.matchup_bets,
    matchupSearch,
    minEdge,
    selectedBookSet,
  ])

  const matchupsPageEmptyMessage = useMemo(() => {
    if (predictionTab === "past")
      return "Use the dashboard home to review past-event matchup replay."
    if (predictionTab === "live" && !isLiveActive)
      return "No event is live right now. Switch to Upcoming for pre-tournament matchup context."
    const diagnostics =
      predictionTab === "upcoming"
        ? liveSnapshot?.upcoming_tournament?.diagnostics
        : liveSnapshot?.live_tournament?.diagnostics
    return getMatchupStateMessage({
      state: diagnostics?.state,
      reasonCodes: diagnostics?.reason_codes,
      hasFilters: normalizedSelectedBooks.length > 0,
    })
  }, [isLiveActive, liveSnapshot, normalizedSelectedBooks, predictionTab])

  const secondaryBets = useMemo(() => {
    if (predictionTab === "past") return []
    return flattenSecondaryBets(visiblePredictionRun).filter((bet) =>
      filterValueBet(bet, minEdge, selectedBookSet),
    )
  }, [predictionTab, selectedBookSet, visiblePredictionRun, minEdge])

  const labWorkspaceHydrated = useMemo(() => {
    if (predictionTab === "past" || !labDisplaySnapshot) return null
    return buildHydratedPredictionRun(labDisplaySnapshot, predictionTab)
  }, [labDisplaySnapshot, predictionTab])

  const labVisiblePredictionRun = predictionTab === "past" ? null : labWorkspaceHydrated

  const labFilteredMatchups = useMemo(() => {
    const sourceMatchups =
      labVisiblePredictionRun?.matchup_bets_all_books ??
      labVisiblePredictionRun?.matchup_bets ??
      []
    return sourceMatchups.filter((matchup) => {
      const matchupBook = normalizeSportsbook(matchup.book)
      if (NON_BOOK_SOURCES.has(matchupBook)) return false
      const passesBook = selectedBookSet.size === 0 || selectedBookSet.has(matchupBook)
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesBook && passesSearch && passesPositiveEv(matchup.ev, minEdge)
    })
  }, [
    labVisiblePredictionRun?.matchup_bets_all_books,
    labVisiblePredictionRun?.matchup_bets,
    matchupSearch,
    minEdge,
    selectedBookSet,
  ])

  const labMatchupsEmptyMessage = useMemo(() => {
    if (predictionTab === "past")
      return "Use the dashboard home to review past-event matchup replay."
    if (predictionTab === "live" && !isLiveActive)
      return "No event is live right now. Switch to Upcoming for pre-tournament matchup context."
    if (!labSnapshotMerged) {
      if (liveSnapshot) {
        return "Lab parallel lane is off — showing production snapshot boards. Set LIVE_REFRESH_LAB_PROFILE_ENABLED=1 in .env (or enable live_refresh.lab_profile_enabled in settings), restart the live-refresh worker, and wait for the next recompute."
      }
      return "No live snapshot yet. Start the live-refresh worker or use Refresh, then try again."
    }
    const diagnostics =
      predictionTab === "upcoming"
        ? labSnapshotMerged.upcoming_tournament?.diagnostics
        : labSnapshotMerged.live_tournament?.diagnostics
    return getMatchupStateMessage({
      state: diagnostics?.state,
      reasonCodes: diagnostics?.reason_codes,
      hasFilters: normalizedSelectedBooks.length > 0,
    })
  }, [isLiveActive, labSnapshotMerged, liveSnapshot, normalizedSelectedBooks, predictionTab])

  const labSecondaryBets = useMemo(() => {
    if (predictionTab === "past") return []
    return flattenSecondaryBets(labVisiblePredictionRun).filter((bet) =>
      filterValueBet(bet, minEdge, selectedBookSet),
    )
  }, [predictionTab, selectedBookSet, labVisiblePredictionRun, minEdge])

  const labPlayers = predictionTab === "past" ? [] : (labWorkspaceHydrated?.composite_results ?? [])

  const labPicksMarketSection = useMemo<
    "lab_live" | "lab_upcoming" | "live" | "upcoming" | null
  >(() => {
    if ((!isLabBoardRoute && !isLabPicksRoute) || predictionTab === "past") return null
    if (predictionTab === "upcoming") {
      if (String(liveSnapshot?.lab_upcoming_tournament?.source_event_id ?? "").trim()) {
        return "lab_upcoming"
      }
      return String(liveSnapshot?.upcoming_tournament?.source_event_id ?? "").trim() ? "upcoming" : null
    }
    if (predictionTab === "live") {
      if (String(liveSnapshot?.lab_live_tournament?.source_event_id ?? "").trim()) {
        return "lab_live"
      }
      return String(liveSnapshot?.live_tournament?.source_event_id ?? "").trim() ? "live" : null
    }
    return null
  }, [isLabBoardRoute, isLabPicksRoute, predictionTab, liveSnapshot])

  const labPicksMarketEventId = useMemo(() => {
    if (!labPicksMarketSection) return ""
    if (labPicksMarketSection === "lab_upcoming") {
      return (
        String(liveSnapshot?.lab_upcoming_tournament?.source_event_id ?? "").trim() ||
        String(liveSnapshot?.upcoming_tournament?.source_event_id ?? "").trim()
      )
    }
    if (labPicksMarketSection === "upcoming") {
      return String(liveSnapshot?.upcoming_tournament?.source_event_id ?? "").trim()
    }
    if (labPicksMarketSection === "lab_live") {
      return (
        String(liveSnapshot?.lab_live_tournament?.source_event_id ?? "").trim() ||
        String(liveSnapshot?.live_tournament?.source_event_id ?? "").trim()
      )
    }
    return String(liveSnapshot?.live_tournament?.source_event_id ?? "").trim()
  }, [labPicksMarketSection, liveSnapshot])

  const labPicksMarketRowsQuery = useQuery({
    queryKey: ["live-refresh-past-market-rows", labPicksMarketEventId, labPicksMarketSection, "lab-route"],
    queryFn: () =>
      api.getLiveRefreshPastMarketRows(labPicksMarketEventId, {
        section: (labPicksMarketSection ?? "live") as "live" | "upcoming" | "lab_live" | "lab_upcoming",
      }),
    enabled: Boolean((isLabBoardRoute || isLabPicksRoute) && labPicksMarketSection && labPicksMarketEventId),
    staleTime: 30_000,
  })
  const labPicksMarketRows = labPicksMarketRowsQuery.data?.ok ? (labPicksMarketRowsQuery.data.rows ?? []) : []
  const labPicksMarketRowsError =
    labPicksMarketRowsQuery.error instanceof Error ? labPicksMarketRowsQuery.error.message : undefined

  const labTournamentIdForPicks =
    predictionTab === "upcoming"
      ? (liveSnapshot?.lab_upcoming_tournament?.tournament_id ??
          liveSnapshot?.upcoming_tournament?.tournament_id)
      : predictionTab === "live"
        ? (liveSnapshot?.lab_live_tournament?.tournament_id ??
            liveSnapshot?.live_tournament?.tournament_id)
        : undefined

  const picksSection: "live" | "upcoming" | null =
    predictionTab === "upcoming" ? "upcoming" : predictionTab === "live" ? "live" : null
  const picksEventId =
    picksSection === "upcoming"
      ? String(liveSnapshot?.upcoming_tournament?.source_event_id ?? "").trim()
      : picksSection === "live"
        ? String(liveSnapshot?.live_tournament?.source_event_id ?? "").trim()
        : ""
  const picksMarketRowsQuery = useQuery({
    queryKey: ["live-refresh-past-market-rows", picksEventId, picksSection],
    queryFn: () =>
      api.getLiveRefreshPastMarketRows(picksEventId, {
        section: picksSection ?? "live",
      }),
    enabled: Boolean(picksSection && picksEventId),
    staleTime: 30_000,
  })
  const picksMarketRows = picksMarketRowsQuery.data?.ok
    ? (picksMarketRowsQuery.data.rows ?? [])
    : []
  const picksMarketRowsError =
    picksMarketRowsQuery.error instanceof Error
      ? picksMarketRowsQuery.error.message
      : undefined

  const gradingHistory = gradingHistoryQuery.data?.tournaments ?? []
  const gradingRecordSummary = gradingHistoryQuery.data?.summary
  const dashboard = dashboardQuery.data

  useLiveRefreshRuntime({
    requestedTour: predictionRequest.tour,
    onError: setUiAlert,
  })

  const dashboardPowerRankingsSubtitle = useMemo(() => {
    if (predictionTab === "past") return null
    const sec =
      predictionTab === "upcoming"
        ? liveSnapshot?.upcoming_tournament
        : liveSnapshot?.live_tournament
    const mv = sec?.model_variant
    if (!mv) return null
    return `Dashboard — snapshot model "${String(mv)}" (default baseline operator path). Compare with Lab (research v5).`
  }, [liveSnapshot, predictionTab])

  const handlePastEventContextChange = useCallback(
    (context: { eventName: string; courseName?: string } | null) => {
      setPastReplayHeadline(context)
    },
    [],
  )

  const cockpitWorkspaceProps = useMemo<PredictionWorkspacePageProps>(
    () => ({
      liveSnapshot,
      runtimeStatus,
      snapshotNotice,
      snapshotAgeSeconds,
      predictionTab,
      onPredictionTabChange: setPredictionTab,
      availableBooks,
      selectedBooks: normalizedSelectedBooks,
      onSelectedBooksChange: setSelectedBooks,
      matchupSearch,
      onMatchupSearchChange: setMatchupSearch,
      minEdge,
      onMinEdgeChange: setMinEdge,
      filteredMatchups,
      gradingHistory,
      gradingRecordSummary,
      players,
      predictionRun: effectivePredictionRun,
      selectedPlayerKey,
      onPlayerSelect: setSelectedPlayerKey,
      selectedPlayerProfile,
      playerProfileState,
      playerProfileErrorMessage,
      onPlayerProfileRetry: handlePlayerProfileRetry,
      richProfilesEnabled: RICH_PLAYER_PROFILES_ENABLED,
      secondaryBets,
      powerRankingsSubtitle: dashboardPowerRankingsSubtitle,
      pastReplaySource: "dashboard",
      onPastEventContextChange: handlePastEventContextChange,
      fullPicks: {
        mode: "production" as const,
        matchups: filteredMatchups,
        matchupsEmptyMessage: matchupsPageEmptyMessage,
        matchupDiagnostics:
          predictionTab === "upcoming"
            ? liveSnapshot?.upcoming_tournament?.diagnostics
            : liveSnapshot?.live_tournament?.diagnostics,
        minEdgePct: Math.round(minEdge * 100),
        secondaryBets,
        onPlayerSelect: setSelectedPlayerKey,
        marketRows: picksMarketRows,
        marketRowsLoading: picksMarketRowsQuery.isLoading || picksMarketRowsQuery.isFetching,
        marketRowsError: picksMarketRowsError,
      },
    }),
    [
      liveSnapshot,
      runtimeStatus,
      snapshotNotice,
      snapshotAgeSeconds,
      predictionTab,
      setPredictionTab,
      availableBooks,
      normalizedSelectedBooks,
      setSelectedBooks,
      matchupSearch,
      setMatchupSearch,
      minEdge,
      setMinEdge,
      filteredMatchups,
      gradingHistory,
      gradingRecordSummary,
      players,
      effectivePredictionRun,
      selectedPlayerKey,
      setSelectedPlayerKey,
      selectedPlayerProfile,
      playerProfileState,
      playerProfileErrorMessage,
      handlePlayerProfileRetry,
      secondaryBets,
      dashboardPowerRankingsSubtitle,
      handlePastEventContextChange,
      liveSnapshot,
      matchupsPageEmptyMessage,
      picksMarketRows,
      picksMarketRowsQuery.isFetching,
      picksMarketRowsQuery.isLoading,
      picksMarketRowsError,
    ],
  )

  const labPowerRankingsSubtitle = useMemo(() => {
    if (!isLabBoardRoute) return null
    if (!labSnapshotMerged) {
      return "Lab track unavailable — showing production snapshot boards until lab_live_tournament / lab_upcoming_tournament populate (enable live_refresh.lab_profile_enabled, restart live-refresh worker, wait for next tick). For an independent Lab vs Dashboard comparison, lab_* sections must be non-null."
    }
    const meta = labWorkspaceHydrated?.strategy_meta
    const champion = meta?.lab_champion_id ?? meta?.strategy_name ?? "lab_champion"
    const mv = labWorkspaceHydrated?.model_variant ?? "v5"
    return `Lab — promoted matchup model ${champion} (${mv}). Dashboard / Picks stay on the production snapshot for A/B.`
  }, [isLabBoardRoute, labSnapshotMerged, labWorkspaceHydrated?.model_variant, labWorkspaceHydrated?.strategy_meta])

  const labBoardWorkspaceProps = useMemo<PredictionWorkspacePageProps>(
    () => ({
      liveSnapshot: labDisplaySnapshot,
      runtimeStatus,
      snapshotNotice,
      snapshotAgeSeconds,
      predictionTab,
      onPredictionTabChange: setPredictionTab,
      availableBooks: collectBooksForFilter(
        labVisiblePredictionRun,
        (predictionTab === "upcoming"
          ? labDisplaySnapshot?.upcoming_tournament
          : predictionTab === "live"
              ? labDisplaySnapshot?.live_tournament
              : null)?.diagnostics?.books_seen,
      ),
      selectedBooks: normalizedSelectedBooks,
      onSelectedBooksChange: setSelectedBooks,
      matchupSearch,
      onMatchupSearchChange: setMatchupSearch,
      minEdge,
      onMinEdgeChange: setMinEdge,
      filteredMatchups: labFilteredMatchups,
      gradingHistory,
      gradingRecordSummary,
      players: labPlayers,
      predictionRun: labWorkspaceHydrated,
      selectedPlayerKey,
      onPlayerSelect: setSelectedPlayerKey,
      selectedPlayerProfile,
      playerProfileState,
      playerProfileErrorMessage,
      onPlayerProfileRetry: handlePlayerProfileRetry,
      richProfilesEnabled: RICH_PLAYER_PROFILES_ENABLED,
      secondaryBets: labSecondaryBets,
      powerRankingsSubtitle: labPowerRankingsSubtitle,
      pastReplaySource: "lab",
      fullPicks: {
        mode: "lab" as const,
        matchups: labFilteredMatchups,
        matchupsEmptyMessage: labMatchupsEmptyMessage,
        matchupDiagnostics:
          predictionTab === "upcoming"
            ? liveSnapshot?.lab_upcoming_tournament?.diagnostics
            : liveSnapshot?.lab_live_tournament?.diagnostics,
        minEdgePct: Math.round(minEdge * 100),
        secondaryBets: labSecondaryBets,
        onPlayerSelect: setSelectedPlayerKey,
        marketRows: labPicksMarketRows,
        marketRowsLoading: labPicksMarketRowsQuery.isLoading || labPicksMarketRowsQuery.isFetching,
        marketRowsError: labPicksMarketRowsError,
        tournamentId: labTournamentIdForPicks,
        predictionRun: labWorkspaceHydrated,
      },
    }),
    [
      labDisplaySnapshot,
      runtimeStatus,
      snapshotNotice,
      snapshotAgeSeconds,
      predictionTab,
      setPredictionTab,
      labVisiblePredictionRun,
      normalizedSelectedBooks,
      setSelectedBooks,
      matchupSearch,
      setMatchupSearch,
      minEdge,
      setMinEdge,
      labFilteredMatchups,
      gradingHistory,
      gradingRecordSummary,
      labPlayers,
      labWorkspaceHydrated,
      selectedPlayerKey,
      setSelectedPlayerKey,
      selectedPlayerProfile,
      playerProfileState,
      playerProfileErrorMessage,
      handlePlayerProfileRetry,
      labSecondaryBets,
      labPowerRankingsSubtitle,
      liveSnapshot,
      labMatchupsEmptyMessage,
      labPicksMarketRows,
      labPicksMarketRowsQuery.isFetching,
      labPicksMarketRowsQuery.isLoading,
      labPicksMarketRowsError,
      labTournamentIdForPicks,
    ],
  )

  const shellEventName =
    predictionTab === "past" && pastReplayHeadline?.eventName
      ? pastReplayHeadline.eventName
      : labRouteActive && labWorkspaceHydrated?.event_name
        ? labWorkspaceHydrated.event_name
        : effectivePredictionRun?.event_name ?? "No event loaded"

  const shellEventMeta = (() => {
    if (predictionTab === "past" && pastReplayHeadline?.courseName) {
      return pastReplayHeadline.courseName
    }
    const run =
      labRouteActive && labWorkspaceHydrated ? labWorkspaceHydrated : effectivePredictionRun
    const course = run?.course_name?.trim()
    if (!course) return undefined
    const field = run?.field_size
    return field != null ? `${course} · ${field} players` : course
  })()

  useEffect(() => {
    const suffix = "Golf Model"
    const path = location.pathname
    const routePrimary: Record<string, string> = {
      "/": shellEventName,
      "/lab": "Lab",
      "/lab/picks": "Lab picks",
      "/players": "Players",
      "/compare": "Track comparison",
      "/eval": "Eval",
      "/matchups": "Picks",
      "/results": "Results",
      "/system": "System",
      "/grading": "Grading",
      "/track-record": "Track record",
      "/research/legacy-model": "Legacy model",
      "/research/champion-challenger": "Champion / Challenger",
      "/research/diagnostics": "Diagnostics",
    }
    const primary =
      routePrimary[path] ??
      (path.startsWith("/players/")
        ? "Player profile"
        : path.startsWith("/cockpit-lab")
            ? "Lab"
            : suffix)
    document.title = primary === suffix ? suffix : `${primary} · ${suffix}`
  }, [location.pathname, shellEventName])

  return (
    <>
    <MonitoringShell
      headline={shellEventName}
      subheadline={shellEventMeta}
      laneSwitcher={
        <CockpitModeSwitch
          value={predictionTab}
          onChange={setPredictionTab}
          liveActive={isLiveActive}
        />
      }
      frameStatus={
        <SidebarStatus
          runtimeStatus={runtimeStatus}
          freshnessLabel={shellFreshnessLabel}
        />
      }
      actions={
        <>
          <CommandMenuTrigger onClick={() => setCommandMenuOpen(true)} />
          <SnapshotChip
            generatedAt={liveSnapshot?.generated_at ?? liveSnapshotEnvelope?.generated_at ?? null}
            dataSource={liveSnapshot?.data_source ?? null}
          />
          <button
            className="btn btn-ghost"
            onClick={() => gradeMutation.mutate()}
            disabled={gradeMutation.isPending}
            data-testid="btn-grade"
          >
            <Star size={13} />
            {gradeMutation.isPending ? "Grading…" : "Grade event"}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => refreshSnapshotMutation.mutate()}
            disabled={refreshButtonDisabled}
            data-testid="btn-refresh"
            aria-busy={refreshButtonDisabled}
            title={
              liveProgress?.last_error
                ? `Last error: ${liveProgress.last_error}`
                : liveProgress?.phase_detail
                  ? `${liveProgress.phase ?? ""}: ${liveProgress.phase_detail}`
                  : undefined
            }
          >
            <RefreshCw
              size={13}
              style={
                refreshButtonDisabled ? { animation: "spin 1s linear infinite" } : undefined
              }
            />
            {refreshSnapshotMutation.isPending
              ? `Refreshing${refreshElapsedSecDisplay != null ? ` (${refreshElapsedSecDisplay}s)` : ""}…`
              : lrRefreshState === "busy" || lrRefreshState === "running"
              ? "Updating…"
              : liveRuntimeRunning
              ? "Refresh"
              : "Start + refresh"}
          </button>
        </>
      }
    >
      <RouteErrorBoundaryGate>
        <Routes>
        <Route
          path="/"
          element={<PredictionWorkspacePage {...cockpitWorkspaceProps} />}
        />
        <Route path="/lab/picks" element={<Navigate to="/lab?tab=full-picks" replace />} />
        <Route
          path="/lab"
          element={
            COCKPIT_LAB_ENABLED ? (
              <CockpitLabPage
                cockpitWorkspaceProps={labBoardWorkspaceProps}
                usingProdSnapshotFallback={labUsingProdSnapshotFallback}
                labLanePartialSections={labLanePartialSections}
              />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/cockpit-lab"
          element={<Navigate to={COCKPIT_LAB_ENABLED ? "/lab" : "/"} replace />}
        />
        <Route
          path="/players"
          element={
            <div className="route-page-shell">
              <Suspense fallback={<RouteFallback />}>
                <PlayersPage players={players} />
              </Suspense>
            </div>
          }
        />
        <Route
          path="/players/:playerKey"
          element={
            <div className="route-page-shell">
              <Suspense fallback={<RouteFallback />}>
                <PlayersDeepLink players={players} />
              </Suspense>
            </div>
          }
        />
        <Route path="/matchups" element={<Navigate to="/?tab=full-picks" replace />} />
        <Route
          path="/compare"
          element={
            <div className="route-page-shell">
              <Suspense fallback={<RouteFallback />}>
                <ComparePage />
              </Suspense>
            </div>
          }
        />
        <Route
          path="/eval"
          element={
            <div className="route-page-shell">
              <Suspense fallback={<RouteFallback />}>
                <EvalPage />
              </Suspense>
            </div>
          }
        />
        <Route
          path="/results"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ResultsPage />
            </Suspense>
          }
        />
        <Route path="/grading" element={<Navigate to="/results" replace />} />
        <Route path="/track-record" element={<Navigate to="/results?tab=track-record" replace />} />
        <Route
          path="/system"
          element={
            <Suspense fallback={<RouteFallback />}>
              <SystemPage
                dashboard={dashboard}
                liveSnapshot={liveSnapshot}
                predictionTab={predictionTab}
                isLiveActive={isLiveActive}
                gradingHistory={gradingHistory}
                predictionRun={effectivePredictionRun}
                secondaryBets={secondaryBets}
              />
            </Suspense>
          }
        />
        <Route
          path="/research/legacy-model"
          element={
            <Suspense fallback={<RouteFallback />}>
              <LegacyModelPage liveSnapshot={liveSnapshot} />
            </Suspense>
          }
        />
        <Route
          path="/research/champion-challenger"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ChampionChallengerPage />
            </Suspense>
          }
        />
        <Route path="/research/diagnostics" element={<Navigate to="/system" replace />} />
        <Route
          path="/research/diagnostics-legacy"
          element={
            <Suspense fallback={<RouteFallback />}>
              <DiagnosticsPage
                dashboard={dashboard}
                liveSnapshot={liveSnapshot}
                predictionTab={predictionTab}
                isLiveActive={isLiveActive}
                gradingHistory={gradingHistory}
                predictionRun={effectivePredictionRun}
                secondaryBets={secondaryBets}
              />
            </Suspense>
          }
        />
      </Routes>
      </RouteErrorBoundaryGate>
    </MonitoringShell>
    <CommandMenu
      open={commandMenuOpen}
      onOpenChange={setCommandMenuOpen}
      onGrade={() => gradeMutation.mutate()}
      onRefresh={() => refreshSnapshotMutation.mutate()}
    />
    </>
  )
}

function snapshotAgeSecondsLabel(ageSeconds: number | null) {
  if (ageSeconds === null || ageSeconds === undefined) return "Waiting for snapshot"
  if (ageSeconds < 60) return `${ageSeconds}s ago`
  return `${Math.round(ageSeconds / 60)}m ago`
}

/* Spin animation for refresh button */
const style = document.createElement("style")
style.textContent = `
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
`
if (typeof document !== "undefined") document.head.appendChild(style)
