import { lazy, Suspense, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Route, Routes, Navigate, useLocation } from "react-router-dom"
import { RefreshCw, Star } from "lucide-react"

import { CockpitModeSwitch } from "@/components/cockpit/workspace"
import { SuiteShell, SidebarStatus } from "@/components/shell"
import { SnapshotChip } from "@/components/snapshot-chip"
import { useLiveRefreshRuntime } from "@/hooks/use-live-refresh-runtime"
import { usePredictionTab } from "@/hooks/use-prediction-tab"
import { api } from "@/lib/api"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import { formatDateTime } from "@/lib/format"
import {
  buildHydratedPredictionRun,
  collectAvailableBooks,
  flattenSecondaryBets,
  NON_BOOK_SOURCES,
  normalizeSportsbook,
} from "@/lib/prediction-board"
import { mergeLabSnapshotSections } from "@/lib/lab-snapshot"
import { useLocalStorageState } from "@/lib/storage"
import type { LiveRefreshSnapshot, PredictionRunRequest, PredictionRunResponse } from "@/lib/types"
import { CockpitLabPage } from "@/pages/cockpit-lab-page"
import { LabPicksPage } from "@/pages/lab-picks-page"
import { LegacyRouteGate } from "@/pages/legacy-route-gate"
import { PicksPage } from "@/pages/picks-page"
import { PredictionWorkspacePage, type PredictionWorkspacePageProps } from "@/pages/prediction-workspace-page"

// Code-split heavy / rarely-visited routes. The default "/" route
// (PredictionWorkspacePage) and the primary Picks route stay eager so the
// cockpit boots without a Suspense flicker. Players, Grading,
// Track Record, and Champion-Challenger are all secondary nav targets — the
// operator clicks into them, so a single network round-trip on first visit
// is acceptable and trims ~400-600 kB off the initial bundle.
const PlayersPage = lazy(() =>
  import("@/pages/players-page").then((mod) => ({ default: mod.PlayersPage })),
)
const GradingPage = lazy(() =>
  import("@/pages/legacy-routes").then((mod) => ({ default: mod.GradingPage })),
)
const TrackRecordPage = lazy(() =>
  import("@/pages/legacy-routes").then((mod) => ({ default: mod.TrackRecordPage })),
)
const ChampionChallengerPage = lazy(() =>
  import("@/pages/champion-challenger-page").then((mod) => ({
    default: mod.ChampionChallengerPage,
  })),
)
const LegacyModelPage = lazy(() =>
  import("@/pages/legacy-model-page").then((mod) => ({ default: mod.LegacyModelPage })),
)
const DiagnosticsPage = lazy(() =>
  import("@/pages/diagnostics-page").then((mod) => ({ default: mod.DiagnosticsPage })),
)

function RouteFallback() {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--text-faint)",
        fontSize: 12,
        fontFamily: "var(--font-mono)",
      }}
      data-testid="route-suspense-fallback"
    >
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
/** Lab route/nav on unless production build explicitly sets `VITE_COCKPIT_LAB=0`. */
const COCKPIT_LAB_ENABLED = import.meta.env.VITE_COCKPIT_LAB !== "0"

function App() {
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

  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    refetchInterval: 30_000,
  })
  const gradingHistoryQuery = useQuery({
    queryKey: ["grading-history", "cockpit"],
    queryFn: () => api.getGradingHistory({ pickSource: "cockpit" }),
  })
  const liveRefreshStatusQuery = useQuery({
    queryKey: ["live-refresh-status"],
    queryFn: api.getLiveRefreshStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.status?.running ? 5_000 : 15_000
    },
  })
  const liveSnapshotQuery = useQuery({
    queryKey: ["live-refresh-snapshot"],
    queryFn: api.getLiveRefreshSnapshot,
    refetchInterval: 10_000,
  })

  const liveSnapshotEnvelope = liveSnapshotQuery.data
  const liveSnapshot: LiveRefreshSnapshot | null = liveSnapshotEnvelope?.snapshot ?? null
  const location = useLocation()
  const labSnapshotMerged = useMemo(() => mergeLabSnapshotSections(liveSnapshot), [liveSnapshot])
  const isCockpitLabRoute = location.pathname.startsWith("/cockpit-lab")
  const isLabPicksRoute = location.pathname.startsWith("/lab/picks")
  const labRouteActive = isCockpitLabRoute || isLabPicksRoute
  /** When the parallel lab lane is off, lab routes still hydrate from production snapshot so the UI is usable. */
  const labDisplaySnapshot = useMemo(() => {
    if (!labRouteActive) return null
    return labSnapshotMerged ?? liveSnapshot ?? null
  }, [labRouteActive, labSnapshotMerged, liveSnapshot])
  const labUsingProdSnapshotFallback = Boolean(labRouteActive && !labSnapshotMerged && liveSnapshot)
  const liveRuntimeRunning = Boolean(liveRefreshStatusQuery.data?.status?.running)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

  // A single failed poll happens routinely (network blip, deploy restart) and
  // should not flip the runtime indicator to "error" or surface the alarming
  // "check API health" banner. We only flag it after the query has retried
  // multiple times without success — React Query exposes this via
  // `failureCount`, which resets to 0 on the next successful poll.
  const SUSTAINED_FAILURE_THRESHOLD = 2
  const snapshotSustainedFailure =
    liveSnapshotQuery.isError && liveSnapshotQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD
  const statusSustainedFailure =
    liveRefreshStatusQuery.isError &&
    liveRefreshStatusQuery.failureCount >= SUSTAINED_FAILURE_THRESHOLD

  const runtimeStatus = useMemo(() => {
    if (statusSustainedFailure || snapshotSustainedFailure)
      return { label: "Runtime error", tone: "bad" as const }
    if (!liveRuntimeRunning)
      return { label: "Offline", tone: "warn" as const }
    if (liveSnapshotEnvelope?.stale_reason)
      return { label: "Degraded", tone: "warn" as const }
    return { label: "Live", tone: "good" as const }
  }, [
    statusSustainedFailure,
    snapshotSustainedFailure,
    liveRuntimeRunning,
    liveSnapshotEnvelope?.stale_reason,
  ])

  const snapshotNotice =
    snapshotSustainedFailure
      ? "Live snapshot request failed. Retry after checking API health."
      : liveSnapshotEnvelope?.stale_reason ?? liveSnapshotEnvelope?.fallback_reason ?? uiAlert

  const shellFreshnessLabel = snapshotAgeSecondsLabel(liveSnapshotEnvelope?.age_seconds ?? null)
  const isLiveActive = Boolean(liveSnapshot?.live_tournament?.active)
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
  const availableBooks = useMemo(() => collectAvailableBooks(visiblePredictionRun), [visiblePredictionRun])
  const prodProfileSection =
    predictionTab === "upcoming"
      ? liveSnapshot?.upcoming_tournament
      : predictionTab === "live"
          ? liveSnapshot?.live_tournament
          : null
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
    if (playerProfileQuery.isPending || playerProfileQuery.isFetching) {
      return "loading"
    }
    if (playerProfileQuery.isError) {
      return "error"
    }
    if (
      playerProfileQuery.data &&
      playerProfileQuery.data.player_key === selectedPlayerKey
    ) {
      return "ready"
    }
    return "unavailable"
  }, [
    hasProfileTournamentContext,
    playerProfileQuery.data,
    playerProfileQuery.isError,
    playerProfileQuery.isFetching,
    playerProfileQuery.isPending,
    selectedPlayerKey,
  ])
  const playerProfileErrorMessage =
    playerProfileQuery.error instanceof Error ? playerProfileQuery.error.message : undefined

  const gradeMutation = useMutation({
    mutationFn: () =>
      api.gradeLatestTournament(dashboardQuery.data?.latest_completed_event ?? undefined),
    onSuccess: () => {
      setUiAlert(null)
      void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
      void queryClient.invalidateQueries({ queryKey: ["grading-history"] })
      void queryClient.invalidateQueries({ queryKey: ["track-record"] })
    },
    onError: () => {
      setUiAlert("Grading failed. Check backend logs and retry.")
    },
  })

  const refreshSnapshotMutation = useMutation({
    mutationFn: () => api.refreshLiveSnapshot(),
    onSuccess: (payload) => {
      if (payload.ok) {
        const generated = payload.generated_at ? formatDateTime(payload.generated_at) : "just now"
        setUiAlert(`Snapshot refreshed (${generated}).`)
      } else {
        setUiAlert(payload.stale_reason ?? "Manual refresh did not return a snapshot.")
      }
      void queryClient.invalidateQueries({ queryKey: ["live-refresh-status"] })
      void queryClient.invalidateQueries({ queryKey: ["live-refresh-snapshot"] })
    },
    onError: () => {
      setUiAlert("Manual refresh failed. Check runtime logs and try again.")
    },
  })

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
      return passesBook && passesSearch && matchup.ev >= minEdge
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
      return "Use the cockpit home to review past-event matchup replay."
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
    return flattenSecondaryBets(visiblePredictionRun).filter((bet) => {
      const betBook = normalizeSportsbook(bet.book)
      if (betBook && NON_BOOK_SOURCES.has(betBook)) return false
      if (selectedBookSet.size === 0) return true
      return betBook ? selectedBookSet.has(betBook) : false
    })
  }, [predictionTab, selectedBookSet, visiblePredictionRun])

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
      return passesBook && passesSearch && matchup.ev >= minEdge
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
      return "Use the cockpit home to review past-event matchup replay."
    if (predictionTab === "live" && !isLiveActive)
      return "No event is live right now. Switch to Upcoming for pre-tournament matchup context."
    if (!labSnapshotMerged) {
      if (liveSnapshot) {
        return "Lab parallel lane is off — showing production snapshot boards. Enable live_refresh.lab_profile_enabled (and wait for the next recompute) for true lab model rows."
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
    return flattenSecondaryBets(labVisiblePredictionRun).filter((bet) => {
      const betBook = normalizeSportsbook(bet.book)
      if (betBook && NON_BOOK_SOURCES.has(betBook)) return false
      if (selectedBookSet.size === 0) return true
      return betBook ? selectedBookSet.has(betBook) : false
    })
  }, [predictionTab, selectedBookSet, labVisiblePredictionRun])

  const labPlayers = predictionTab === "past" ? [] : (labWorkspaceHydrated?.composite_results ?? [])

  const labPicksMarketSection = useMemo<
    "lab_live" | "lab_upcoming" | "live" | "upcoming" | null
  >(() => {
    if (!isLabPicksRoute || predictionTab === "past") return null
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
  }, [isLabPicksRoute, predictionTab, liveSnapshot])

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
        limit: 5000,
      }),
    enabled: Boolean(isLabPicksRoute && labPicksMarketSection && labPicksMarketEventId),
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
        limit: 5000,
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
  const dashboard = dashboardQuery.data

  useLiveRefreshRuntime({
    requestedTour: predictionRequest.tour,
    onError: setUiAlert,
  })

  const cockpitWorkspaceProps = useMemo<PredictionWorkspacePageProps>(
    () => ({
      liveSnapshot,
      runtimeStatus,
      snapshotNotice,
      snapshotAgeSeconds: liveSnapshotEnvelope?.age_seconds ?? null,
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
      players,
      predictionRun: effectivePredictionRun,
      selectedPlayerKey,
      onPlayerSelect: setSelectedPlayerKey,
      selectedPlayerProfile: playerProfileQuery.data,
      playerProfileState,
      playerProfileErrorMessage,
      onPlayerProfileRetry: () => {
        void playerProfileQuery.refetch()
      },
      richProfilesEnabled: RICH_PLAYER_PROFILES_ENABLED,
      secondaryBets,
    }),
    [
      liveSnapshot,
      runtimeStatus,
      snapshotNotice,
      liveSnapshotEnvelope?.age_seconds,
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
      players,
      effectivePredictionRun,
      selectedPlayerKey,
      setSelectedPlayerKey,
      playerProfileQuery.data,
      playerProfileState,
      playerProfileErrorMessage,
      playerProfileQuery.refetch,
      secondaryBets,
    ],
  )

  const labCockpitWorkspaceProps = useMemo<PredictionWorkspacePageProps>(
    () => ({
      liveSnapshot: labDisplaySnapshot,
      runtimeStatus,
      snapshotNotice,
      snapshotAgeSeconds: liveSnapshotEnvelope?.age_seconds ?? null,
      predictionTab,
      onPredictionTabChange: setPredictionTab,
      availableBooks: collectAvailableBooks(labVisiblePredictionRun),
      selectedBooks: normalizedSelectedBooks,
      onSelectedBooksChange: setSelectedBooks,
      matchupSearch,
      onMatchupSearchChange: setMatchupSearch,
      minEdge,
      onMinEdgeChange: setMinEdge,
      filteredMatchups: labFilteredMatchups,
      gradingHistory,
      players: labPlayers,
      predictionRun: labWorkspaceHydrated,
      selectedPlayerKey,
      onPlayerSelect: setSelectedPlayerKey,
      selectedPlayerProfile: playerProfileQuery.data,
      playerProfileState,
      playerProfileErrorMessage,
      onPlayerProfileRetry: () => {
        void playerProfileQuery.refetch()
      },
      richProfilesEnabled: RICH_PLAYER_PROFILES_ENABLED,
      secondaryBets: labSecondaryBets,
    }),
    [
      labDisplaySnapshot,
      runtimeStatus,
      snapshotNotice,
      liveSnapshotEnvelope?.age_seconds,
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
      labPlayers,
      labWorkspaceHydrated,
      selectedPlayerKey,
      setSelectedPlayerKey,
      playerProfileQuery.data,
      playerProfileState,
      playerProfileErrorMessage,
      playerProfileQuery.refetch,
      labSecondaryBets,
    ],
  )

  const shellEventName =
    labRouteActive && labWorkspaceHydrated?.event_name
      ? labWorkspaceHydrated.event_name
      : effectivePredictionRun?.event_name ?? "No event loaded"

  return (
    <SuiteShell
      headline={shellEventName}
      modeSwitcher={
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
            disabled={refreshSnapshotMutation.isPending}
            data-testid="btn-refresh"
          >
            <RefreshCw
              size={13}
              style={
                refreshSnapshotMutation.isPending
                  ? { animation: "spin 1s linear infinite" }
                  : undefined
              }
            />
            {refreshSnapshotMutation.isPending
              ? "Refreshing…"
              : liveRuntimeRunning
              ? "Refresh"
              : "Start + refresh"}
          </button>
        </>
      }
    >
      <Routes>
        <Route
          path="/"
          element={<PredictionWorkspacePage {...cockpitWorkspaceProps} />}
        />
        <Route
          path="/cockpit-lab"
          element={
            COCKPIT_LAB_ENABLED ? (
              <CockpitLabPage
                cockpitWorkspaceProps={labCockpitWorkspaceProps}
                usingProdSnapshotFallback={labUsingProdSnapshotFallback}
              />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/lab/picks"
          element={
            COCKPIT_LAB_ENABLED ? (
              <LabPicksPage
                matchups={labFilteredMatchups}
                matchupsEmptyMessage={labMatchupsEmptyMessage}
                matchupDiagnostics={
                  predictionTab === "upcoming"
                    ? liveSnapshot?.lab_upcoming_tournament?.diagnostics
                    : liveSnapshot?.lab_live_tournament?.diagnostics
                }
                minEdgePct={Math.round(minEdge * 100)}
                secondaryBets={labSecondaryBets}
                onPlayerSelect={setSelectedPlayerKey}
                marketRows={labPicksMarketRows}
                marketRowsLoading={labPicksMarketRowsQuery.isLoading || labPicksMarketRowsQuery.isFetching}
                marketRowsError={labPicksMarketRowsError}
                tournamentId={labTournamentIdForPicks}
                predictionRun={labWorkspaceHydrated}
              />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/players"
          element={
            <div style={{flex:1,minHeight:0,overflow:"hidden",display:"flex",flexDirection:"column"}}>
              <Suspense fallback={<RouteFallback />}>
                <PlayersPage players={players} />
              </Suspense>
            </div>
          }
        />
        <Route
          path="/matchups"
          element={
            <LegacyRouteGate route="matchups" mode={predictionTab}>
              <PicksPage
                matchups={filteredMatchups}
                matchupsEmptyMessage={matchupsPageEmptyMessage}
                matchupDiagnostics={
                  predictionTab === "upcoming"
                    ? liveSnapshot?.upcoming_tournament?.diagnostics
                    : liveSnapshot?.live_tournament?.diagnostics
                }
                minEdgePct={Math.round(minEdge * 100)}
                secondaryBets={secondaryBets}
                onPlayerSelect={setSelectedPlayerKey}
                marketRows={picksMarketRows}
                marketRowsLoading={picksMarketRowsQuery.isLoading || picksMarketRowsQuery.isFetching}
                marketRowsError={picksMarketRowsError}
              />
            </LegacyRouteGate>
          }
        />
        <Route
          path="/grading"
          element={
            <div style={{flex:1,overflowY:"auto",padding:"10px 12px"}}>
              <Suspense fallback={<RouteFallback />}>
                <GradingPage />
              </Suspense>
            </div>
          }
        />
        <Route
          path="/track-record"
          element={
            <div style={{flex:1,overflowY:"auto",padding:"10px 12px"}}>
              <Suspense fallback={<RouteFallback />}>
                <TrackRecordPage />
              </Suspense>
            </div>
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
        <Route
          path="/research/diagnostics"
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
    </SuiteShell>
  )
}

function snapshotAgeSecondsLabel(ageSeconds: number | null) {
  if (ageSeconds === null || ageSeconds === undefined) return "Waiting for snapshot"
  if (ageSeconds < 60) return `${ageSeconds}s ago`
  return `${Math.round(ageSeconds / 60)}m ago`
}

export default App

/* Spin animation for refresh button */
const style = document.createElement("style")
style.textContent = `
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
`
if (typeof document !== "undefined") document.head.appendChild(style)
