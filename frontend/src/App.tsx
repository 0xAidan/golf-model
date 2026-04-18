import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Route, Routes } from "react-router-dom"

import { CockpitModeSwitch } from "@/components/cockpit/workspace"
import { SuiteShell } from "@/components/shell"
import { Button } from "@/components/ui/button"
import { useLiveRefreshRuntime } from "@/hooks/use-live-refresh-runtime"
import { usePredictionTab } from "@/hooks/use-prediction-tab"
import { api } from "@/lib/api"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import { formatDateTime } from "@/lib/format"
import { buildHydratedPredictionRun, collectAvailableBooks, flattenSecondaryBets, NON_BOOK_SOURCES, normalizeSportsbook } from "@/lib/prediction-board"
import { useLocalStorageState } from "@/lib/storage"
import type { LiveRefreshSnapshot, PredictionRunRequest, PredictionRunResponse } from "@/lib/types"
import { LegacyRouteGate } from "@/pages/legacy-route-gate"
import { CoursePage, GradingPage, MatchupsPage, PlayersPage, TrackRecordPage } from "@/pages/legacy-routes"
import { PredictionWorkspacePage } from "@/pages/prediction-workspace-page"

const DEFAULT_REQUEST: PredictionRunRequest = {
  tour: "pga",
  tournament: "",
  course: "",
  mode: "full",
  enable_ai: true,
}

const RICH_PLAYER_PROFILES_ENABLED = import.meta.env.VITE_RICH_PLAYER_PROFILES !== "0"

function App() {
  const queryClient = useQueryClient()
  const [predictionRequest] = useLocalStorageState<PredictionRunRequest>("golf-model.prediction-request", DEFAULT_REQUEST)
  const [predictionRun] = useLocalStorageState<PredictionRunResponse | null>("golf-model.latest-prediction-run", null)
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
    queryKey: ["grading-history"],
    queryFn: api.getGradingHistory,
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
  const liveRuntimeRunning = Boolean(liveRefreshStatusQuery.data?.status?.running)
  const [uiAlert, setUiAlert] = useState<string | null>(null)

  const runtimeStatus = useMemo(() => {
    if (liveRefreshStatusQuery.isError || liveSnapshotQuery.isError) {
      return { label: "Runtime error", tone: "bad" as const }
    }
    if (!liveRuntimeRunning) {
      return { label: "Runtime offline", tone: "warn" as const }
    }
    if (liveSnapshotEnvelope?.stale_reason) {
      return { label: "Snapshot degraded", tone: "warn" as const }
    }
    return { label: "Runtime active", tone: "good" as const }
  }, [
    liveRefreshStatusQuery.isError,
    liveSnapshotQuery.isError,
    liveRuntimeRunning,
    liveSnapshotEnvelope?.stale_reason,
  ])

  const snapshotNotice =
    liveSnapshotQuery.isError
      ? "Live snapshot request failed. Retry after checking API health."
      : liveSnapshotEnvelope?.stale_reason ?? liveSnapshotEnvelope?.fallback_reason ?? uiAlert
  const shellFreshnessLabel = snapshotAgeSecondsLabel(liveSnapshotEnvelope?.age_seconds ?? null)
  const isLiveActive = Boolean(liveSnapshot?.live_tournament?.active)
  const { predictionTab, setPredictionTab } = usePredictionTab(isLiveActive)

  const hydratedRun = useMemo(() => {
    if (predictionTab === "past") {
      return null
    }
    return buildHydratedPredictionRun(liveSnapshot, predictionTab)
  }, [liveSnapshot, predictionTab])
  const effectivePredictionRun = useMemo(() => hydratedRun ?? predictionRun, [hydratedRun, predictionRun])
  const visiblePredictionRun = predictionTab === "past" ? null : effectivePredictionRun

  const normalizedSelectedBooks = useMemo(
    () => selectedBooks.map((book) => normalizeSportsbook(book)).filter(Boolean),
    [selectedBooks],
  )
  const selectedBookSet = useMemo(() => new Set(normalizedSelectedBooks), [normalizedSelectedBooks])
  const availableBooks = useMemo(
    () => collectAvailableBooks(visiblePredictionRun),
    [visiblePredictionRun],
  )

  const playerProfileQuery = useQuery({
    queryKey: ["player-profile", selectedPlayerKey, visiblePredictionRun?.tournament_id, visiblePredictionRun?.course_num],
    queryFn: () => api.getPlayerProfile(selectedPlayerKey, visiblePredictionRun?.tournament_id ?? 0, visiblePredictionRun?.course_num),
    enabled: RICH_PLAYER_PROFILES_ENABLED && Boolean(selectedPlayerKey && visiblePredictionRun?.tournament_id),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  })

  const gradeMutation = useMutation({
    mutationFn: () => api.gradeLatestTournament(dashboardQuery.data?.latest_completed_event ?? undefined),
    onSuccess: () => {
      setUiAlert(null)
      void queryClient.invalidateQueries({ queryKey: ["dashboard-state"] })
      void queryClient.invalidateQueries({ queryKey: ["grading-history"] })
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
      visiblePredictionRun?.matchup_bets_all_books
      ?? visiblePredictionRun?.matchup_bets
      ?? []

    return sourceMatchups.filter((matchup) => {
      const matchupBook = normalizeSportsbook(matchup.book)
      if (NON_BOOK_SOURCES.has(matchupBook)) return false
      const passesBook = selectedBookSet.size === 0 || selectedBookSet.has(matchupBook)
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesBook && passesSearch && matchup.ev >= minEdge
    })
  }, [visiblePredictionRun?.matchup_bets_all_books, visiblePredictionRun?.matchup_bets, matchupSearch, minEdge, selectedBookSet])

  const matchupsPageEmptyMessage = useMemo(() => {
    if (predictionTab === "past") {
      return "Use the cockpit home route to review past-event matchup replay and generated-pick context."
    }

    if (predictionTab === "live" && !isLiveActive) {
      return "No event is live right now. Switch to Upcoming for pre-tournament matchup context."
    }

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
    if (predictionTab === "past") {
      return []
    }

    return flattenSecondaryBets(visiblePredictionRun).filter((bet) => {
      const betBook = normalizeSportsbook(bet.book)
      if (betBook && NON_BOOK_SOURCES.has(betBook)) return false
      if (selectedBookSet.size === 0) return true
      return betBook ? selectedBookSet.has(betBook) : false
    })
  }, [predictionTab, selectedBookSet, visiblePredictionRun])

  const gradingHistory = gradingHistoryQuery.data?.tournaments ?? []
  const dashboard = dashboardQuery.data

  useLiveRefreshRuntime({
    requestedTour: predictionRequest.tour,
    onError: setUiAlert,
  })

  return (
    <SuiteShell
      headline={effectivePredictionRun?.event_name ?? "Event cockpit"}
      subheadline="One tournament workspace for live monitoring, pre-event planning, replay review, and player drill-downs while legacy routes stay reachable during migration."
      modeSwitcher={
        <CockpitModeSwitch
          value={predictionTab}
          onChange={setPredictionTab}
          liveActive={isLiveActive}
        />
      }
      frameStatus={
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-[0.16em] text-slate-500">Runtime</span>
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${
                runtimeStatus.tone === "good"
                  ? "bg-emerald-500/15 text-emerald-200"
                  : runtimeStatus.tone === "bad"
                    ? "bg-rose-500/15 text-rose-200"
                    : "bg-amber-500/15 text-amber-200"
              }`}
            >
              {runtimeStatus.label}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-[0.16em] text-slate-500">Freshness</span>
            <span className="text-sm text-white">{shellFreshnessLabel}</span>
          </div>
        </div>
      }
      actions={
        <>
          <Button
            size="lg"
            variant="outline"
            onClick={() => gradeMutation.mutate()}
            disabled={gradeMutation.isPending}
          >
            {gradeMutation.isPending ? "Grading..." : "Grade latest event"}
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => refreshSnapshotMutation.mutate()}
            disabled={refreshSnapshotMutation.isPending}
          >
            {refreshSnapshotMutation.isPending
              ? "Refreshing..."
              : liveRuntimeRunning
                ? "Refresh now"
                : "Start + refresh"}
          </Button>
        </>
      }
    >
      <Routes>
        <Route
          path="/"
          element={
            <PredictionWorkspacePage
              dashboard={dashboard}
              liveSnapshot={liveSnapshot}
              runtimeStatus={runtimeStatus}
              snapshotNotice={snapshotNotice}
              snapshotAgeSeconds={liveSnapshotEnvelope?.age_seconds ?? null}
              predictionTab={predictionTab}
              onPredictionTabChange={setPredictionTab}
              availableBooks={availableBooks}
              selectedBooks={normalizedSelectedBooks}
              onSelectedBooksChange={setSelectedBooks}
              matchupSearch={matchupSearch}
              onMatchupSearchChange={setMatchupSearch}
              minEdge={minEdge}
              onMinEdgeChange={setMinEdge}
              filteredMatchups={filteredMatchups}
              gradingHistory={gradingHistory}
              players={players}
              predictionRun={effectivePredictionRun}
              selectedPlayerKey={selectedPlayerKey}
              onPlayerSelect={setSelectedPlayerKey}
              selectedPlayerProfile={playerProfileQuery.data}
              richProfilesEnabled={RICH_PLAYER_PROFILES_ENABLED}
              secondaryBets={secondaryBets}
            />
          }
        />
        <Route
          path="/players"
          element={
            <LegacyRouteGate route="players" mode={predictionTab}>
              <PlayersPage
                players={players}
                selectedPlayerProfile={playerProfileQuery.data}
                onPlayerSelect={setSelectedPlayerKey}
                richProfilesEnabled={RICH_PLAYER_PROFILES_ENABLED}
              />
            </LegacyRouteGate>
          }
        />
        <Route
          path="/matchups"
          element={
            <LegacyRouteGate route="matchups" mode={predictionTab}>
              <MatchupsPage
                matchups={filteredMatchups}
                emptyMessage={matchupsPageEmptyMessage}
              />
            </LegacyRouteGate>
          }
        />
        <Route
          path="/course"
          element={
            <LegacyRouteGate route="course" mode={predictionTab}>
              <CoursePage
                dashboard={dashboard}
                players={players}
                predictionRun={effectivePredictionRun}
              />
            </LegacyRouteGate>
          }
        />
        <Route path="/grading" element={<GradingPage gradingHistory={gradingHistory} />} />
        <Route path="/track-record" element={<TrackRecordPage />} />
      </Routes>
    </SuiteShell>
  )
}

function snapshotAgeSecondsLabel(ageSeconds: number | null) {
  if (ageSeconds === null || ageSeconds === undefined) {
    return "Waiting for snapshot"
  }

  return `${ageSeconds}s old`
}

export default App
