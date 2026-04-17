import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Brain, ChevronDown, CircleAlert, Clock3, Download, ExternalLink, Flag, NotebookPen, Radar, ShieldAlert, Sparkles } from "lucide-react"
import { Link, Route, Routes } from "react-router-dom"

import { BarTrendChart, SparklineChart } from "@/components/charts"
import { PlayerProfileSections } from "@/components/player-profile-sections"
import { CommandShell, MetricTile, SectionTitle, SurfaceCard } from "@/components/shell"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { formatDateTime, formatNumber, formatUnits } from "@/lib/format"
import { buildHydratedPredictionRun, buildPredictionRunFromSection, collectAvailableBooks, flattenSecondaryBets, NON_BOOK_SOURCES, normalizeSportsbook } from "@/lib/prediction-board"
import { useLocalStorageState } from "@/lib/storage"
import trackRecordData from "@/data/trackRecord.json"
import type {
  CompositePlayer,
  DashboardState,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  LiveRefreshStatusResponse,
  MatchupBet,
  PastSnapshotEvent,
  PlayerProfile,
  PredictionRunRequest,
  PredictionRunResponse,
} from "@/lib/types"

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
  const [matchupSearch] = useLocalStorageState("golf-model.matchup-search", "")
  const [minEdge] = useLocalStorageState("golf-model.min-edge", 0.02)
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
      const data = query.state.data as LiveRefreshStatusResponse | undefined
      return data?.status?.running ? 5_000 : 15_000
    },
  })
  const liveSnapshotQuery = useQuery({
    queryKey: ["live-refresh-snapshot"],
    queryFn: api.getLiveRefreshSnapshot,
    refetchInterval: 10_000,
  })
  const liveSnapshotEnvelope = liveSnapshotQuery.data
  const liveSnapshot = (liveSnapshotEnvelope?.snapshot ?? null) as LiveRefreshSnapshot | null
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
  const isLiveActive = Boolean(liveSnapshot?.live_tournament?.active)
  const [predictionTab, setPredictionTab] = useState<"live" | "upcoming" | "past">(
    isLiveActive ? "live" : "upcoming",
  )
  const hydratedRun = useMemo(() => {
    if (predictionTab === "past") {
      return null
    }
    return buildHydratedPredictionRun(liveSnapshot, predictionTab)
  }, [liveSnapshot, predictionTab])
  const effectivePredictionRun = useMemo(() => {
    return hydratedRun ?? predictionRun
  }, [predictionRun, hydratedRun])
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
  }, [predictionTab, visiblePredictionRun, selectedBookSet])
  const gradingHistory = gradingHistoryQuery.data?.tournaments ?? []
  const dashboard = dashboardQuery.data as DashboardState | undefined

  useEffect(() => {
    const ensureAlwaysOnRuntime = async () => {
      try {
        const runtime = await api.getLiveRefreshStatus()
        const settings = runtime.settings ?? {}
        if (settings.enabled === false) {
          return
        }
        const tour = settings.tour || predictionRequest.tour || "pga"
        if (settings.autostart !== true) {
          await api.patchAutoresearchSettings({
            live_refresh: { ...settings, enabled: true, autostart: true, tour },
          })
        }
        if (!runtime.status?.running) {
          await api.startLiveRefresh({
            tour,
            live_refresh: { ...settings, enabled: true, autostart: true, tour },
          })
        }
      } catch {
        setUiAlert("Could not verify live runtime automatically. Use 'Check runtime' and inspect status.")
      }
    }
    void ensureAlwaysOnRuntime()
  }, [predictionRequest.tour])

  return (
    <CommandShell
      headline={effectivePredictionRun?.event_name ?? "Operator command station"}
      subheadline="Desktop-first betting intelligence across predictions, player drill-downs, course context, grading continuity, and research control."
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
              filteredMatchups={filteredMatchups}
              gradingHistory={gradingHistory}
              players={players}
              predictionRun={effectivePredictionRun}
              secondaryBets={secondaryBets}
            />
          }
        />
        <Route
          path="/players"
          element={
            <PlayersPage
              players={players}
              selectedPlayerProfile={playerProfileQuery.data}
              onPlayerSelect={setSelectedPlayerKey}
              richProfilesEnabled={RICH_PLAYER_PROFILES_ENABLED}
            />
          }
        />
        <Route
          path="/matchups"
          element={
            <MatchupsPage
              matchups={filteredMatchups}
            />
          }
        />
        <Route
          path="/course"
          element={
            <CoursePage
              dashboard={dashboard}
              players={players}
              predictionRun={effectivePredictionRun}
            />
          }
        />
        <Route
          path="/grading"
          element={<GradingPage gradingHistory={gradingHistory} />}
        />
        <Route
          path="/track-record"
          element={<TrackRecordPage />}
        />
      </Routes>
    </CommandShell>
  )
}

function PredictionWorkspacePage({
  dashboard,
  liveSnapshot,
  runtimeStatus,
  snapshotNotice,
  snapshotAgeSeconds,
  predictionTab,
  onPredictionTabChange,
  availableBooks,
  selectedBooks,
  onSelectedBooksChange,
  filteredMatchups,
  gradingHistory,
  players,
  predictionRun,
  secondaryBets,
}: {
  dashboard?: DashboardState
  liveSnapshot: LiveRefreshSnapshot | null
  runtimeStatus: { label: string; tone: "good" | "warn" | "bad" }
  snapshotNotice: string | null
  snapshotAgeSeconds: number | null
  predictionTab: "live" | "upcoming" | "past"
  onPredictionTabChange: (value: "live" | "upcoming" | "past") => void
  availableBooks: string[]
  selectedBooks: string[]
  onSelectedBooksChange: (value: string[]) => void
  filteredMatchups: MatchupBet[]
  gradingHistory: GradedTournamentSummary[]
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
  secondaryBets: Array<{ market: string; player: string; odds: string; ev: number; confidence?: string; book?: string }>
}) {
  const [expandedMatchupKey, setExpandedMatchupKey] = useState<string | null>(null)
  const [healthExpanded, setHealthExpanded] = useState(false)
  const [selectedPastEventKey, setSelectedPastEventKey] = useState("")
  const pastEventsQuery = useQuery({
    queryKey: ["live-refresh-past-events"],
    queryFn: api.getLiveRefreshPastEvents,
    staleTime: 60_000,
  })

  const totalProfit = gradingHistory.reduce((sum, t) => sum + Number(t.total_profit ?? 0), 0)
  const liveTournament = liveSnapshot?.live_tournament
  const upcomingTournament = liveSnapshot?.upcoming_tournament
  const isLiveActive = Boolean(liveTournament?.active)

  const fallbackPastEvents = useMemo<PastSnapshotEvent[]>(
    () =>
      gradingHistory
        .filter((event) => Boolean(event.event_id))
        .map((event) => ({
          event_id: String(event.event_id),
          event_name: event.name,
        })),
    [gradingHistory],
  )
  const pastEventOptions = useMemo(() => {
    const persisted = pastEventsQuery.data?.events ?? []
    return persisted.length > 0 ? persisted : fallbackPastEvents
  }, [fallbackPastEvents, pastEventsQuery.data?.events])
  const selectedPastEvent = useMemo(() => {
    if (pastEventOptions.length === 0) return null
    if (!selectedPastEventKey) return pastEventOptions[0]
    return pastEventOptions.find((event) => event.event_id === selectedPastEventKey) ?? pastEventOptions[0]
  }, [pastEventOptions, selectedPastEventKey])
  useEffect(() => {
    if (predictionTab !== "past") return
    if (selectedPastEventKey) return
    const firstEventId = pastEventOptions[0]?.event_id
    if (firstEventId) {
      setSelectedPastEventKey(firstEventId)
    }
  }, [pastEventOptions, predictionTab, selectedPastEventKey])
  const pastSnapshotQuery = useQuery({
    queryKey: ["live-refresh-past-snapshot", selectedPastEvent?.event_id],
    queryFn: () => api.getLiveRefreshPastSnapshot(selectedPastEvent?.event_id ?? ""),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })
  const pastSnapshotSection = pastSnapshotQuery.data?.ok ? (pastSnapshotQuery.data.snapshot ?? null) : null
  const pastPredictionRun = useMemo(
    () => buildPredictionRunFromSection(pastSnapshotSection),
    [pastSnapshotSection],
  )
  const selectedBookSet = useMemo(() => new Set(selectedBooks), [selectedBooks])
  const pastMatchups = useMemo(() => {
    const sourceRows = pastPredictionRun?.matchup_bets_all_books ?? pastPredictionRun?.matchup_bets ?? []
    return sourceRows.filter((matchup) => {
      const matchupBook = normalizeSportsbook(matchup.book)
      if (NON_BOOK_SOURCES.has(matchupBook)) return false
      if (selectedBookSet.size === 0) return true
      return matchupBook ? selectedBookSet.has(matchupBook) : false
    })
  }, [pastPredictionRun, selectedBookSet])
  const pastSecondaryBets = useMemo(() => {
    return flattenSecondaryBets(pastPredictionRun).filter((bet) => {
      const betBook = normalizeSportsbook(bet.book)
      if (betBook && NON_BOOK_SOURCES.has(betBook)) return false
      if (selectedBookSet.size === 0) return true
      return betBook ? selectedBookSet.has(betBook) : false
    })
  }, [pastPredictionRun, selectedBookSet])
  const displayPredictionRun = predictionTab === "past" ? pastPredictionRun : predictionRun
  const displayPlayers = predictionTab === "past" ? (pastPredictionRun?.composite_results ?? []) : players
  const displaySecondaryBets = predictionTab === "past" ? pastSecondaryBets : secondaryBets
  const displayAvailableBooks = predictionTab === "past" ? collectAvailableBooks(pastPredictionRun) : availableBooks
  const activeSection =
    predictionTab === "upcoming"
      ? upcomingTournament
      : predictionTab === "live"
        ? liveTournament
        : null
  const eventName =
    predictionTab === "past"
      ? selectedPastEvent?.event_name ?? "Past event snapshot unavailable"
      : activeSection?.event_name ?? displayPredictionRun?.event_name ?? "No event loaded"
  const courseName =
    predictionTab === "past"
      ? (pastPredictionRun?.course_name ?? "")
      : activeSection?.course_name ?? displayPredictionRun?.course_name ?? ""
  const fieldSize =
    predictionTab === "past"
      ? (pastPredictionRun?.field_size ?? 0)
      : activeSection?.field_size ?? displayPredictionRun?.field_size ?? 0
  const diagnostics = predictionTab === "past" ? pastSnapshotSection?.diagnostics : activeSection?.diagnostics
  const leaderboardRows = predictionTab === "past"
    ? (pastSnapshotSection?.leaderboard ?? [])
    : (activeSection?.leaderboard ?? [])
  const matchupSource = useMemo(
    () => (predictionTab === "past" ? pastMatchups : filteredMatchups),
    [filteredMatchups, pastMatchups, predictionTab],
  )

  const topPlays = useMemo(() => {
    const TIER_RANK: Record<string, number> = { STRONG: 0, GOOD: 1, LEAN: 2 }
    return matchupSource.slice().sort((a, b) => {
      const tierDiff = (TIER_RANK[a.tier ?? "LEAN"] ?? 2) - (TIER_RANK[b.tier ?? "LEAN"] ?? 2)
      if (tierDiff !== 0) return tierDiff
      return b.ev - a.ev
    })
  }, [matchupSource])

  const bestEdge = topPlays.length > 0
    ? topPlays[0].ev
    : 0

  const diagnosticsMessage =
    predictionTab === "past"
      ? pastSnapshotQuery.isFetching
        ? "Loading stored past-event snapshot..."
        : pastSnapshotQuery.isError
          ? "No stored past-event snapshot found for this selection yet."
          : "Stored snapshot replay for completed event."
      : getMatchupStateMessage({
        state: diagnostics?.state,
        reasonCodes: diagnostics?.reason_codes,
        hasFilters: selectedBooks.length > 0,
      })

  const handleExportMarkdown = () => {
    if (!displayPredictionRun?.card_content) return
    const blob = new Blob([displayPredictionRun.card_content], { type: "text/markdown;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `${displayPredictionRun.event_name ?? "prediction"}.md`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* ── Zone 1: Tournament context header ── */}
      <SurfaceCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
              {predictionTab === "live" ? "Live Event" : predictionTab === "upcoming" ? "Upcoming Event" : "Past Event"}
            </p>
            <h3 className="mt-1 text-2xl font-semibold tracking-tight text-white">{eventName}</h3>
            {courseName ? <p className="mt-1 text-sm text-slate-400">{courseName}</p> : null}
          </div>
          <span
            className={`mt-1 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${
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

        {snapshotNotice ? (
          <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            {snapshotNotice}
            {snapshotAgeSeconds !== null ? ` (snapshot age: ${snapshotAgeSeconds}s)` : ""}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={predictionTab === "upcoming" ? "default" : "outline"}
            onClick={() => onPredictionTabChange("upcoming")}
          >
            Upcoming
          </Button>
          <Button
            size="sm"
            variant={predictionTab === "live" ? "default" : "outline"}
            onClick={() => onPredictionTabChange("live")}
          >
            <span className="flex items-center gap-1.5">
              {isLiveActive ? <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" /> : null}
              Live
            </span>
          </Button>
          <Button
            size="sm"
            variant={predictionTab === "past" ? "default" : "outline"}
            onClick={() => onPredictionTabChange("past")}
          >
            Past Event
          </Button>
        </div>

        {predictionTab === "past" ? (
          <div className="mt-3">
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-500">Browse past events</span>
              <select
                className="rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/30"
                value={selectedPastEventKey}
                onChange={(event) => setSelectedPastEventKey(event.target.value)}
                aria-label="Select past event"
                disabled={pastEventOptions.length === 0}
              >
                <option value="">Most recent completed event</option>
                {pastEventOptions.map((event) => (
                  <option key={event.event_id} value={event.event_id}>
                    {event.event_name}
                  </option>
                ))}
              </select>
            </label>
            <p className="mt-2 text-xs text-slate-400">
              {pastSnapshotQuery.isFetching
                ? "Loading immutable snapshot replay for the selected event..."
                : pastSnapshotQuery.isError
                  ? "No immutable snapshot found for this event yet. Run live refresh during event windows to capture replay history."
                  : selectedPastEvent
                    ? `Replay loaded from snapshot history${pastSnapshotQuery.data?.generated_at ? ` (${formatDateTime(pastSnapshotQuery.data.generated_at)}).` : "."}`
                    : "Select an event to load snapshot replay."}
            </p>
          </div>
        ) : null}

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-white/8 bg-black/20 px-4 py-3">
            <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Field</p>
            <p className="mt-1 text-xl font-semibold text-white">{fieldSize}</p>
          </div>
          <div className="rounded-xl border border-white/8 bg-black/20 px-4 py-3">
            <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Edges found</p>
            <p className="mt-1 text-xl font-semibold text-white">{topPlays.length}</p>
          </div>
          <div className="rounded-xl border border-white/8 bg-black/20 px-4 py-3">
            <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Best edge</p>
            <p className="mt-1 text-xl font-semibold text-cyan-200">{bestEdge > 0 ? `${(bestEdge * 100).toFixed(1)}%` : "--"}</p>
          </div>
          <div className="rounded-xl border border-white/8 bg-black/20 px-4 py-3">
            <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Season P/L</p>
            <p className={`mt-1 text-xl font-semibold ${totalProfit >= 0 ? "text-emerald-300" : "text-amber-200"}`}>{formatUnits(totalProfit)}</p>
          </div>
        </div>
      </SurfaceCard>

      {/* ── Zone 2: Featured plays ── */}
      <SurfaceCard>
        <SectionTitle
          title="Top Plays"
          description={
            predictionTab === "live"
              ? "Best edges from the live event."
              : predictionTab === "upcoming"
                ? "Highest-conviction matchup edges for the upcoming event."
                : "Replayed matchup edges captured during prior refresh cycles."
          }
          action={
            <Link to="/matchups" className="flex items-center gap-1.5 text-sm text-cyan-300 transition hover:text-cyan-200">
              View all matchups <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          }
        />

        {displayAvailableBooks.length > 0 ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Books</span>
            {displayAvailableBooks.map((book) => {
              const active = selectedBooks.includes(book)
              return (
                <button
                  key={book}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    if (active) {
                      onSelectedBooksChange(selectedBooks.filter((b) => b !== book))
                    } else {
                      onSelectedBooksChange([...selectedBooks, book])
                    }
                  }}
                  className={`rounded-full border px-2.5 py-0.5 text-[10px] uppercase tracking-[0.14em] transition ${
                    active
                      ? "border-cyan-300/40 bg-cyan-400/15 text-cyan-100"
                      : "border-white/10 bg-white/5 text-slate-400 hover:border-white/25 hover:text-slate-200"
                  }`}
                >
                  {book}
                </button>
              )
            })}
            {selectedBooks.length > 0 ? (
              <button
                type="button"
                onClick={() => onSelectedBooksChange([])}
                className="text-[10px] uppercase tracking-[0.14em] text-slate-500 transition hover:text-slate-300"
              >
                Clear
              </button>
            ) : null}
          </div>
        ) : null}

        {predictionTab === "live" && !isLiveActive ? (
          <div className="rounded-2xl border border-white/10 bg-black/20 p-6">
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <Radar className="mb-3 h-8 w-8 text-slate-600" />
              <p className="text-base font-medium text-white">No event is live right now</p>
              <p className="mt-2 max-w-md text-sm text-slate-400">
                Live edges will populate automatically after Thursday tee-off.
                Check{" "}
                <button type="button" className="text-cyan-300 underline underline-offset-2 hover:text-cyan-200" onClick={() => onPredictionTabChange("upcoming")}>
                  Upcoming
                </button>{" "}
                for pre-tournament projections.
              </p>
            </div>
          </div>
        ) : topPlays.length > 0 ? (
          <div className="space-y-3">
            {topPlays.slice(0, 5).map((matchup) => {
              const key = buildMatchupKey(matchup)
              const isExpanded = expandedMatchupKey === key
              return (
                <div key={key} className="rounded-2xl border border-white/8 bg-black/20 transition">
                  <button
                    type="button"
                    aria-expanded={isExpanded}
                    aria-label={`${matchup.pick} over ${matchup.opponent}, edge ${matchup.ev_pct}`}
                    tabIndex={0}
                    className={`flex w-full cursor-pointer items-center justify-between gap-4 p-4 text-left transition hover:bg-white/5 ${isExpanded ? "bg-white/3" : ""}`}
                    onClick={() => setExpandedMatchupKey(isExpanded ? null : key)}
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-white">{matchup.pick} <span className="text-slate-500">over</span> {matchup.opponent}</p>
                      <p className="mt-0.5 text-xs text-slate-500">{matchup.book ?? "book"} · {matchup.odds}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="hidden text-right sm:block">
                        <p className="text-[10px] uppercase tracking-[0.14em] text-slate-500">Edge</p>
                        <p className="text-sm font-semibold text-cyan-200">{matchup.ev_pct}</p>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${getTierStyle(matchup.tier)}`}>
                        {matchup.tier ?? "lean"}
                      </span>
                      <ChevronDown className={`h-4 w-4 text-slate-500 transition ${isExpanded ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  {isExpanded ? (
                    <div className="border-t border-white/8 bg-white/3 px-4 py-5">
                      <div className="space-y-4">
                        <p className="text-sm leading-6 text-slate-300">{matchup.reason}</p>
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                          <MetricTile label="Model probability" value={`${(matchup.model_win_prob * 100).toFixed(1)}%`} />
                          <MetricTile label="Implied probability" value={`${(matchup.implied_prob * 100).toFixed(1)}%`} />
                          <MetricTile label="Composite gap" value={formatNumber(matchup.composite_gap, 1)} />
                          <MetricTile label="Conviction" value={formatNumber(matchup.conviction, 0)} />
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                          <MetricTile label="Form gap" value={formatNumber(matchup.form_gap, 1)} />
                          <MetricTile label="Course-fit gap" value={formatNumber(matchup.course_fit_gap, 1)} />
                          <MetricTile label="Momentum" value={matchup.momentum_aligned ? "Aligned" : "Mixed"} />
                          <MetricTile label="Stake multiplier" value={formatNumber(matchup.stake_multiplier, 2)} />
                        </div>
                        <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                          <div className="mb-2 flex items-center gap-2 text-slate-300">
                            <ChartColumnIcon />
                            <span className="text-sm font-medium">Confidence drivers</span>
                          </div>
                          <BarTrendChart
                            labels={["Composite", "Form", "Course", "Momentum", "Conviction"]}
                            values={[
                              matchup.composite_gap,
                              matchup.form_gap,
                              matchup.course_fit_gap,
                              Number(matchup.pick_momentum ?? 0) - Number(matchup.opp_momentum ?? 0),
                              Number(matchup.conviction ?? 0),
                            ]}
                            color="#22d3ee"
                          />
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              )
            })}
            {topPlays.length > 5 ? (
              <p className="text-center text-sm text-slate-500">
                Showing top 5 of {topPlays.length} qualifying lines.{" "}
                <Link to="/matchups" className="text-cyan-300 underline underline-offset-2 hover:text-cyan-200">View all</Link>
              </p>
            ) : null}
          </div>
        ) : (
          <EmptyState message={diagnosticsMessage} />
        )}
      </SurfaceCard>

      {/* ── Zone 3: Rankings + secondary intel ── */}
      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SurfaceCard>
          <SectionTitle
            title="Power Rankings"
            description="Top 10 model projections for this event context."
            action={
              <Link to="/players" className="flex items-center gap-1.5 text-sm text-cyan-300 transition hover:text-cyan-200">
                Full rankings <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            }
          />
          {displayPlayers.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-sm" role="grid">
                <thead>
                  <tr className="border-b border-white/10 text-left text-[10px] uppercase tracking-[0.16em] text-slate-500">
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">Player</th>
                    <th className="px-3 py-2 text-right font-medium">Composite</th>
                    <th className="px-3 py-2 text-right font-medium">Form</th>
                    <th className="px-3 py-2 text-right font-medium">Course</th>
                    <th className="px-3 py-2 text-center font-medium">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {displayPlayers.slice(0, 10).map((player) => {
                    const dir = player.momentum_direction ?? ""
                    const arrow = TREND_ARROW[dir] ?? "—"
                    const trendColor = TREND_COLOR[dir] ?? "text-slate-500"
                    return (
                      <tr key={player.player_key} className="border-t border-white/6 transition hover:bg-white/5">
                        <td className="px-3 py-2.5 text-slate-500">{player.rank}</td>
                        <td className="px-3 py-2.5">
                          <Link to="/players" className="font-medium text-white transition hover:text-cyan-200">
                            {player.player_display}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5 text-right font-semibold text-cyan-200">{formatNumber(player.composite, 1)}</td>
                        <td className="px-3 py-2.5 text-right text-slate-300">{formatNumber(player.form, 1)}</td>
                        <td className="px-3 py-2.5 text-right text-slate-300">{formatNumber(player.course_fit, 1)}</td>
                        <td className={`px-3 py-2.5 text-center text-base ${trendColor}`}>{arrow}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message="No rankings available yet for this event context." />
          )}
        </SurfaceCard>
        <div className="space-y-6">
          <SurfaceCard>
            <SectionTitle
              title="Leaderboard"
              description={
                predictionTab === "upcoming"
                  ? "Live leaderboard appears once round scoring data is available."
                  : "Round-by-round leaderboard feed, independent of model projections."
              }
            />
            {leaderboardRows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[420px] text-sm" role="grid">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-[10px] uppercase tracking-[0.16em] text-slate-500">
                      <th className="px-3 py-2 font-medium">Pos</th>
                      <th className="px-3 py-2 font-medium">Player</th>
                      <th className="px-3 py-2 text-right font-medium">To Par</th>
                      <th className="px-3 py-2 text-right font-medium">R</th>
                      <th className="px-3 py-2 text-right font-medium">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboardRows.slice(0, 10).map((row) => (
                      <tr key={`${row.player_key ?? row.player}-${row.rank}`} className="border-t border-white/6 transition hover:bg-white/5">
                        <td className="px-3 py-2.5 text-slate-400">{row.position ?? row.rank}</td>
                        <td className="px-3 py-2.5 text-white">{row.player}</td>
                        <td className="px-3 py-2.5 text-right text-cyan-200">{formatToParValue(row.total_to_par)}</td>
                        <td className="px-3 py-2.5 text-right text-slate-300">{row.latest_round_num ?? "--"}</td>
                        <td className="px-3 py-2.5 text-right text-slate-300">{row.latest_round_score ?? "--"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message="No leaderboard rows available yet for this event context." />
            )}
          </SurfaceCard>

          <SurfaceCard>
            <SectionTitle
              title="Market Intel"
              description="Secondary edges across placement and adjacent markets."
            />
            {displaySecondaryBets.length > 0 ? (
              <div className="space-y-2">
                {displaySecondaryBets.slice(0, 6).map((bet) => (
                  <div key={`${bet.market}-${bet.player}-${bet.odds}`} className="flex items-center justify-between gap-4 rounded-xl border border-white/8 bg-black/20 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">{bet.player}</p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        <span className="rounded-full bg-white/8 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300">
                          {bet.market}
                        </span>
                        <span className="rounded-full bg-cyan-400/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-cyan-200">
                          {secondaryBadgeLabel(bet.market)}
                        </span>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-cyan-200">{formatNumber(bet.ev * 100, 1)}%</p>
                      <p className="text-xs text-slate-500">
                        {bet.book ? `${bet.book} · ${bet.odds}` : bet.odds}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState message="No secondary market edges surfaced yet." />
            )}
          </SurfaceCard>
        </div>
      </div>

      {/* ── Zone 4: Season performance + model health ── */}
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SurfaceCard>
          <SectionTitle title="Season Performance" description="Recent graded tournaments and running P/L." />
          {gradingHistory.length > 0 ? (
            <>
              <div className="mb-4">
                <SparklineChart
                  values={gradingHistory.slice(0, 8).reverse().map((t) => Number(t.total_profit ?? 0))}
                  color="#34d399"
                />
              </div>
              <div className="space-y-2">
                {gradingHistory.slice(0, 5).map((event) => {
                  const profit = Number(event.total_profit ?? 0)
                  return (
                    <div key={`${event.event_id}-${event.year}`} className="flex items-center justify-between gap-4 rounded-xl border border-white/6 bg-black/15 px-4 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-white">{event.name}</p>
                        <p className="text-xs text-slate-500">{event.hits ?? 0}/{event.graded_pick_count ?? 0} hits</p>
                      </div>
                      <p className={`text-sm font-semibold ${profit >= 0 ? "text-emerald-300" : "text-red-400"}`}>
                        {formatUnits(profit)}
                      </p>
                    </div>
                  )
                })}
              </div>
              <Link to="/track-record" className="mt-3 flex items-center gap-1.5 text-sm text-cyan-300 transition hover:text-cyan-200">
                Full track record <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </>
          ) : (
            <EmptyState message="Grade a tournament to see season performance." />
          )}
        </SurfaceCard>

        <SurfaceCard>
          <SectionTitle
            title="Model Health"
            description="Runtime status, data diagnostics, and export."
            action={
              <button
                type="button"
                aria-expanded={healthExpanded}
                onClick={() => setHealthExpanded(!healthExpanded)}
                className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-200"
              >
                {healthExpanded ? "Collapse" : "Details"}
                <ChevronDown className={`h-3.5 w-3.5 transition ${healthExpanded ? "rotate-180" : ""}`} />
              </button>
            }
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoRow icon={ShieldAlert} label="Field validation" value={displayPredictionRun?.field_validation?.has_cross_tour_field_risk ? "Review warnings" : "Healthy"} />
            <InfoRow icon={Brain} label="AI availability" value={dashboard?.ai_status?.available ? "Enabled" : "Unavailable"} />
            <InfoRow icon={Flag} label="Latest completed" value={dashboard?.latest_completed_event?.event_name ?? "--"} />
            <InfoRow icon={Clock3} label="Last graded" value={dashboard?.latest_graded_tournament?.name ?? "--"} />
          </div>

          {healthExpanded ? (
            <div className="mt-4 space-y-3">
              <div className="rounded-xl border border-white/8 bg-black/20 p-3">
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Data diagnostics</p>
                <div className="mt-2 grid gap-1.5 text-sm text-slate-300">
                  <p>Snapshot state: {diagnostics?.state ?? "unknown"}</p>
                  <p>Matchup rows posted: {String(diagnostics?.market_counts?.tournament_matchups?.raw_rows ?? 0)}</p>
                  <p>Selection rows: {String(diagnostics?.selection_counts?.selected_rows ?? 0)}</p>
                  <p>Rows filtered (EV cap): {String(diagnostics?.value_filters?.ev_cap_filtered ?? 0)}</p>
                  <p>Rows filtered (missing odds): {String(diagnostics?.value_filters?.missing_display_odds ?? 0)}</p>
                  <p>Rows filtered (probability mismatch): {String(diagnostics?.value_filters?.probability_inconsistency_filtered ?? 0)}</p>
                </div>
              </div>
              {displayPredictionRun?.warnings?.length ? (
                <div className="rounded-xl border border-amber-400/25 bg-amber-500/10 p-3 text-sm text-amber-100">
                  {displayPredictionRun.warnings.join(" ")}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="mt-4">
            <Button size="sm" variant="outline" onClick={handleExportMarkdown} disabled={!displayPredictionRun?.card_content}>
              <Download className="mr-1.5 h-3.5 w-3.5" />
              Export markdown
            </Button>
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

const formatToParValue = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "--"
  if (value === 0) return "E"
  return value > 0 ? `+${value}` : `${value}`
}

const TREND_ARROW: Record<string, string> = { hot: "↑↑", warming: "↑", cooling: "↓", cold: "↓↓" }
const TREND_COLOR: Record<string, string> = {
  hot: "text-emerald-400",
  warming: "text-emerald-300",
  cooling: "text-amber-300",
  cold: "text-red-400",
}

const TIER_STYLE: Record<string, string> = {
  STRONG: "bg-emerald-400/12 text-emerald-300",
  GOOD: "bg-cyan-400/12 text-cyan-200",
  LEAN: "bg-slate-400/10 text-slate-400",
}
const getTierStyle = (tier?: string) => TIER_STYLE[tier ?? ""] ?? TIER_STYLE.LEAN

function PlayersPage({
  players,
  selectedPlayerProfile,
  onPlayerSelect,
  richProfilesEnabled,
}: {
  players: CompositePlayer[]
  selectedPlayerProfile?: PlayerProfile
  onPlayerSelect: (playerKey: string) => void
  richProfilesEnabled: boolean
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const handleToggle = (playerKey: string) => {
    if (expandedKey === playerKey) {
      setExpandedKey(null)
      onPlayerSelect("")
    } else {
      setExpandedKey(playerKey)
      onPlayerSelect(playerKey)
    }
  }

  return (
    <SurfaceCard>
      <SectionTitle title="Model Rankings" description="Click any player row to expand their full projection profile." />
      {players.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm" role="grid">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                <th className="px-3 py-3 font-medium">Rank</th>
                <th className="px-3 py-3 font-medium">Player</th>
                <th className="px-3 py-3 font-medium text-right">Composite</th>
                <th className="px-3 py-3 font-medium text-right">Course Fit</th>
                <th className="px-3 py-3 font-medium text-right">Form</th>
                <th className="px-3 py-3 font-medium text-right">Momentum</th>
                <th className="px-3 py-3 font-medium text-center">Trend</th>
              </tr>
            </thead>
            <tbody>
              {players.map((player) => {
                const isExpanded = player.player_key === expandedKey
                const dir = player.momentum_direction ?? ""
                const arrow = TREND_ARROW[dir] ?? "—"
                const trendColor = TREND_COLOR[dir] ?? "text-slate-500"
                const profileReady =
                  isExpanded &&
                  Boolean(selectedPlayerProfile) &&
                  selectedPlayerProfile?.player_key === player.player_key

                return (
                  <tr key={player.player_key} className="group">
                    <td colSpan={7} className="p-0">
                      <button
                        type="button"
                        aria-expanded={isExpanded}
                        aria-label={`${player.player_display} ranked ${player.rank}`}
                        tabIndex={0}
                        className={`flex w-full cursor-pointer items-center transition hover:bg-white/5 ${isExpanded ? "bg-white/3" : ""}`}
                        onClick={() => handleToggle(player.player_key)}
                      >
                        <span className="w-[calc(100%/7)] px-3 py-3 text-left text-slate-400">{player.rank}</span>
                        <span className="flex w-[calc(100%/7)] items-center gap-2 px-3 py-3 text-left font-medium text-white">
                          {player.player_display}
                          <ChevronDown className={`h-3.5 w-3.5 text-slate-500 transition ${isExpanded ? "rotate-180" : ""}`} />
                        </span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right font-semibold text-cyan-200">{formatNumber(player.composite, 1)}</span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right text-slate-300">{formatNumber(player.course_fit, 1)}</span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right text-slate-300">{formatNumber(player.form, 1)}</span>
                        <span className="w-[calc(100%/7)] px-3 py-3 text-right text-slate-300">{formatNumber(player.momentum, 1)}</span>
                        <span className={`w-[calc(100%/7)] px-3 py-3 text-center text-lg ${trendColor}`}>{arrow}</span>
                      </button>
                      {isExpanded ? (
                        <div className="border-t border-white/8 bg-white/3 px-4 py-5">
                          {richProfilesEnabled ? (
                            <PlayerProfileSections
                              player={player}
                              profile={selectedPlayerProfile}
                              profileReady={profileReady}
                            />
                          ) : (
                            <div className="space-y-4">
                              <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                                Rich profile sections are currently disabled by configuration.
                              </div>
                              <div className="grid gap-4 md:grid-cols-4">
                                <MetricTile label="Composite" value={formatNumber(player.composite, 1)} />
                                <MetricTile label="Course fit" value={formatNumber(player.course_fit, 1)} />
                                <MetricTile label="Form" value={formatNumber(player.form, 1)} />
                                <MetricTile label="Momentum" value={formatNumber(player.momentum, 1)} />
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState message="No players available yet for this event context." />
      )}
    </SurfaceCard>
  )
}

function MatchupsPage({
  matchups,
}: {
  matchups: MatchupBet[]
}) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const handleToggle = (key: string) => {
    setExpandedKey(expandedKey === key ? null : key)
  }

  return (
    <SurfaceCard>
      <SectionTitle title="Matchup conviction map" description="Scan tier, edge, pricing, and momentum at a glance. Click any row to expand." />
      {matchups.length ? (
        <div className="space-y-3">
          {matchups.map((matchup) => {
            const key = buildMatchupKey(matchup)
            const isExpanded = expandedKey === key
            return (
              <div key={key} className="rounded-2xl border border-white/8 bg-black/20 transition">
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  aria-label={`${matchup.pick} vs ${matchup.opponent}`}
                  tabIndex={0}
                  className={`flex w-full cursor-pointer items-center justify-between gap-4 p-4 text-left transition hover:bg-white/5 ${isExpanded ? "bg-white/3" : ""}`}
                  onClick={() => handleToggle(key)}
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="min-w-0">
                      <p className="font-medium text-white">{matchup.pick}</p>
                      <p className="text-xs text-slate-500">vs {matchup.opponent}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="hidden text-right sm:block">
                      <p className="text-xs text-slate-500">Edge</p>
                      <p className="text-sm font-semibold text-cyan-200">{matchup.ev_pct}</p>
                    </div>
                    <div className="hidden text-right sm:block">
                      <p className="text-xs text-slate-500">Price</p>
                      <p className="text-sm font-semibold text-white">{matchup.odds}</p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${getTierStyle(matchup.tier)}`}>
                      {matchup.tier ?? "lean"}
                    </span>
                    <ChevronDown className={`h-4 w-4 text-slate-500 transition ${isExpanded ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {isExpanded ? (
                  <div className="border-t border-white/8 bg-white/3 px-4 py-5">
                    <div className="space-y-5">
                      <div className="grid gap-4 md:grid-cols-4">
                        <MetricTile label="Edge" value={matchup.ev_pct} />
                        <MetricTile label="Model prob" value={`${(matchup.model_win_prob * 100).toFixed(1)}%`} />
                        <MetricTile label="Implied prob" value={`${(matchup.implied_prob * 100).toFixed(1)}%`} />
                        <MetricTile label="Conviction" value={formatNumber(matchup.conviction, 0)} />
                      </div>
                      <div className="grid gap-4 md:grid-cols-4">
                        <MetricTile label="Composite gap" value={formatNumber(matchup.composite_gap, 1)} />
                        <MetricTile label="Form gap" value={formatNumber(matchup.form_gap, 1)} />
                        <MetricTile label="Course fit gap" value={formatNumber(matchup.course_fit_gap, 1)} />
                        <MetricTile label="Momentum" value={matchup.momentum_aligned ? "Aligned" : "Mixed"} />
                      </div>
                      <BarTrendChart
                        labels={["Composite", "Form", "Course", "Momentum", "Conviction"]}
                        values={[
                          matchup.composite_gap,
                          matchup.form_gap,
                          matchup.course_fit_gap,
                          Number(matchup.pick_momentum ?? 0) - Number(matchup.opp_momentum ?? 0),
                          Number(matchup.conviction ?? 0),
                        ]}
                        color="#38bdf8"
                      />
                      <div className="grid gap-4 md:grid-cols-2">
                        <MetricTile label="Book" value={matchup.book ?? "--"} />
                        <MetricTile label="Price" value={matchup.odds} />
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState message="No matchups available under the current filters." />
      )}
    </SurfaceCard>
  )
}

function CoursePage({
  dashboard,
  players,
  predictionRun,
}: {
  dashboard?: DashboardState
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
}) {
  const topPlayers = players.slice(0, 8)

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-4">
        <MetricTile label="Event" value={predictionRun?.event_name ?? "--"} />
        <MetricTile label="Course" value={predictionRun?.course_name ?? "--"} />
        <MetricTile label="Cross-tour backfill" value={predictionRun?.field_validation?.cross_tour_backfill_used ? "Enabled" : "Standard"} />
        <MetricTile label="Latest graded" value={dashboard?.latest_graded_tournament?.name ?? "--"} />
      </div>
      <div className="grid gap-6 2xl:grid-cols-[1.05fr_0.95fr]">
        <SurfaceCard>
          <SectionTitle title="Field-fit distribution" description="Top of the board by composite score, framed as a course-fit command surface." />
          {topPlayers.length ? (
            <BarTrendChart labels={topPlayers.map((player) => player.player_display.split(" ")[0])} values={topPlayers.map((player) => player.composite)} color="#38bdf8" />
          ) : (
            <EmptyState message="Run a prediction to populate field-fit distributions." />
          )}
        </SurfaceCard>
        <SurfaceCard>
          <SectionTitle title="Course risk notes" description="Macro course context and field quality warnings that matter before a wager goes live." />
          <div className="space-y-3">
            <InfoRow icon={Radar} label="Major event handling" value={predictionRun?.field_validation?.major_event ? "Major-week cross-tour coverage active" : "Standard PGA event"} />
            <InfoRow icon={ShieldAlert} label="Thin-round players" value={String(predictionRun?.field_validation?.players_with_thin_rounds?.length ?? 0)} />
            <InfoRow icon={CircleAlert} label="Missing DG skill" value={String(predictionRun?.field_validation?.players_missing_dg_skill?.length ?? 0)} />
            <InfoRow icon={NotebookPen} label="Prediction artifact" value={dashboard?.latest_prediction_artifact?.path ?? "--"} />
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

function GradingPage({ gradingHistory }: { gradingHistory: GradedTournamentSummary[] }) {
  const labels = gradingHistory.slice(0, 8).reverse().map((item) => item.name.replace("Open", ""))
  const profits = gradingHistory.slice(0, 8).reverse().map((item) => Number(item.total_profit ?? 0))

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-4">
        <MetricTile label="Tournaments graded" value={String(gradingHistory.length)} />
        <MetricTile label="Latest P/L" value={formatUnits(Number(gradingHistory[0]?.total_profit ?? 0))} />
        <MetricTile label="Latest hits" value={String(gradingHistory[0]?.hits ?? 0)} />
        <MetricTile label="Last graded at" value={formatDateTime(gradingHistory[0]?.last_graded_at)} />
      </div>
      <div className="grid gap-6 2xl:grid-cols-[1fr_0.95fr]">
        <SurfaceCard>
          <SectionTitle title="Season trend" description="Durable grading history survives refreshes, restarts, and week-to-week review." />
          {profits.length ? <BarTrendChart labels={labels} values={profits} color="#34d399" /> : <EmptyState message="Grade a tournament to start the season trend view." />}
        </SurfaceCard>
        <SurfaceCard>
          <SectionTitle title="Graded events" description="Tournament-by-tournament status, hit count, and profit." />
          <div className="space-y-3">
            {gradingHistory.map((item) => (
              <div key={`${item.event_id}-${item.year}`} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-white">{item.name}</p>
                    <p className="text-xs text-slate-500">{formatDateTime(item.last_graded_at)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-emerald-300">{formatUnits(Number(item.total_profit ?? 0))}</p>
                    <p className="text-xs text-slate-500">
                      {item.hits ?? 0}/{item.graded_pick_count ?? 0} hits
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SurfaceCard>
      </div>
    </div>
  )
}

type MergedEvent = {
  name: string
  course: string
  wins: number
  losses: number
  pushes: number
  profit: number
  picks: Array<{ pick: string; opponent: string; odds: string; result: string; pl: number }>
}

function useTrackRecordData(): { events: MergedEvent[]; totals: { wins: number; losses: number; pushes: number; profit: number } } {
  const trackRecordQuery = useQuery({
    queryKey: ["track-record"],
    queryFn: api.getTrackRecord,
    staleTime: 5 * 60 * 1000,
  })

  return useMemo(() => {
    const staticEvents = (trackRecordData as { events: Array<{ name: string; course: string; record: { wins: number; losses: number; pushes: number }; profit_units: number; picks: Array<{ pick: string; opponent: string; odds: string; result: string; pl: number }> }> }).events
    const apiEvents = trackRecordQuery.data?.events ?? []

    const seen = new Set<string>()

    const merged: MergedEvent[] = []

    for (const apiEvent of apiEvents) {
      const key = apiEvent.name.toLowerCase().trim()
      seen.add(key)
      const apiPicks = (apiEvent.picks ?? []).map((p) => ({
        pick: p.player_display,
        opponent: p.opponent_display,
        odds: String(p.market_odds ?? "--"),
        result: p.hit === 1 ? "win" : p.profit === 0 ? "push" : "loss",
        pl: p.profit,
      }))
      const staticMatch = staticEvents.find((s) => s.name.toLowerCase().trim() === key)
      const picks = apiPicks.length > 0 ? apiPicks : (staticMatch?.picks ?? [])
      merged.push({
        name: apiEvent.name,
        course: apiEvent.course ?? staticMatch?.course ?? "",
        wins: apiEvent.wins,
        losses: apiEvent.losses,
        pushes: apiEvent.pushes,
        profit: apiEvent.total_profit,
        picks,
      })
    }

    for (const staticEvent of staticEvents) {
      const key = staticEvent.name.toLowerCase().trim()
      if (seen.has(key)) continue
      merged.push({
        name: staticEvent.name,
        course: staticEvent.course,
        wins: staticEvent.record.wins,
        losses: staticEvent.record.losses,
        pushes: staticEvent.record.pushes,
        profit: staticEvent.profit_units,
        picks: staticEvent.picks,
      })
    }

    const totals = merged.reduce(
      (acc, e) => ({ wins: acc.wins + e.wins, losses: acc.losses + e.losses, pushes: acc.pushes + e.pushes, profit: acc.profit + e.profit }),
      { wins: 0, losses: 0, pushes: 0, profit: 0 },
    )
    return { events: merged, totals }
  }, [trackRecordQuery.data])
}

function TrackRecordPage() {
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null)
  const { events, totals } = useTrackRecordData()
  const totalBets = totals.wins + totals.losses + totals.pushes
  const winRate = totalBets - totals.pushes > 0 ? ((totals.wins / (totalBets - totals.pushes)) * 100).toFixed(1) : "0"
  const roiPct = totalBets > 0 ? ((totals.profit / totalBets) * 100).toFixed(1) : "0"

  return (
    <div className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-5">
        <MetricTile label="Record" value={`${totals.wins}-${totals.losses}-${totals.pushes}`} />
        <MetricTile label="Win rate" value={`${winRate}%`} tone={Number(winRate) >= 50 ? "positive" : undefined} />
        <MetricTile label="Profit" value={`${totals.profit >= 0 ? "+" : ""}${totals.profit.toFixed(2)}u`} tone={totals.profit >= 0 ? "positive" : "warning"} />
        <MetricTile label="ROI" value={`${Number(roiPct) >= 0 ? "+" : ""}${roiPct}%`} tone={Number(roiPct) >= 0 ? "positive" : "warning"} />
        <MetricTile label="Events" value={String(events.length)} />
      </div>
      <SurfaceCard>
        <SectionTitle title="Event-by-event results" description="2026 PGA Tour season. Matchup-focused betting record." />
        <div className="space-y-2">
          {events.map((event) => {
            const isOpen = expandedEvent === event.name
            const record = `${event.wins}-${event.losses}-${event.pushes}`
            const profitSign = event.profit >= 0 ? "+" : ""
            const profitTone = event.profit >= 0 ? "text-emerald-300" : "text-red-400"

            return (
              <div key={event.name} className="rounded-2xl border border-white/8 bg-black/20">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-label={`${event.name} record ${record}`}
                  tabIndex={0}
                  className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition hover:bg-white/5"
                  onClick={() => setExpandedEvent(isOpen ? null : event.name)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-white">{event.name}</p>
                    <p className="text-xs text-slate-500">{event.course}</p>
                  </div>
                  <div className="flex items-center gap-5">
                    <div className="text-right">
                      <p className="text-sm font-semibold text-white">{record}</p>
                      <p className={`text-xs font-medium ${profitTone}`}>{profitSign}{event.profit.toFixed(2)}u</p>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-slate-500 transition ${isOpen ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {isOpen ? (
                  <div className="border-t border-white/8 px-5 py-4">
                    {event.picks.length ? (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[480px] text-sm">
                          <thead>
                            <tr className="border-b border-white/10 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
                              <th className="px-2 py-2 font-medium">Pick</th>
                              <th className="px-2 py-2 font-medium">vs</th>
                              <th className="px-2 py-2 font-medium text-right">Odds</th>
                              <th className="px-2 py-2 font-medium text-center">Result</th>
                              <th className="px-2 py-2 font-medium text-right">P/L</th>
                            </tr>
                          </thead>
                          <tbody>
                            {event.picks.map((p, i) => {
                              const resultColor =
                                p.result === "win" ? "text-emerald-400" : p.result === "loss" ? "text-red-400" : "text-slate-400"
                              const plColor = p.pl > 0 ? "text-emerald-300" : p.pl < 0 ? "text-red-400" : "text-slate-400"
                              return (
                                <tr key={`${p.pick}-${p.opponent}-${i}`} className="border-b border-white/5">
                                  <td className="px-2 py-2.5 text-white">{p.pick}</td>
                                  <td className="px-2 py-2.5 text-slate-400">{p.opponent}</td>
                                  <td className="px-2 py-2.5 text-right text-slate-300">{p.odds}</td>
                                  <td className={`px-2 py-2.5 text-center font-medium uppercase ${resultColor}`}>{p.result}</td>
                                  <td className={`px-2 py-2.5 text-right font-medium ${plColor}`}>
                                    {p.pl > 0 ? "+" : ""}{p.pl.toFixed(2)}u
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-sm text-slate-400">No individual pick data available for this event.</p>
                    )}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </SurfaceCard>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-slate-400">{message}</div>
}

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Sparkles
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="rounded-xl bg-white/6 p-2 text-cyan-200">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
        <p className="truncate text-sm text-slate-100">{value}</p>
      </div>
    </div>
  )
}

function ChartColumnIcon() {
  return <div className="h-4 w-4 rounded-full bg-cyan-300/80" aria-hidden="true" />
}

function buildMatchupKey(matchup: MatchupBet) {
  return [
    matchup.pick_key,
    matchup.opponent_key,
    matchup.market_type ?? "matchup",
    normalizeSportsbook(matchup.book) || "book",
    String(matchup.odds ?? "--"),
  ].join("-")
}

function secondaryBadgeLabel(market: string) {
  const normalized = market.toLowerCase()
  if (normalized.includes("miss")) {
    return "miss-cut"
  }
  if (normalized.includes("top") || normalized.includes("placement")) {
    return "placement"
  }
  return "mispriced"
}

function getMatchupStateMessage({
  state,
  reasonCodes,
  hasFilters,
}: {
  state?: string
  reasonCodes?: Record<string, number>
  hasFilters: boolean
}) {
  if (hasFilters) {
    return "No matchup rows match current book/search/min-EV filters."
  }
  if (state === "no_market_posted_yet") {
    return "No sportsbook matchup lines are posted yet for this context."
  }
  if (state === "market_available_no_edges") {
    return "Markets are available, but no rows currently pass model and EV thresholds."
  }
  if (state === "pipeline_error") {
    return "Matchup pipeline reported an error. Check runtime diagnostics."
  }
  if ((reasonCodes?.missing_composite_player ?? 0) > 0) {
    return "Matchup rows were received, but player mapping to model scores failed."
  }
  return "No matchup rows are available yet."
}

export default App
