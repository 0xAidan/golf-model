import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Download, ExternalLink, Radar } from "lucide-react"
import { Link } from "react-router-dom"

import {
  CourseWeatherFeedPanel,
  DiagnosticsGradingPanel,
  LeaderboardPanel,
  MarketIntelPanel,
  ReplayTimelinePanel,
} from "@/components/cockpit/event-modules"
import { BarTrendChart } from "@/components/charts"
import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import { CockpitModule, CockpitWorkspace } from "@/components/cockpit/workspace"
import { MetricTile } from "@/components/shell"
import { Button } from "@/components/ui/button"
import { useCockpitSpotlight } from "@/hooks/use-cockpit-spotlight"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import { api } from "@/lib/api"
import {
  buildCourseFeedModel,
  buildDiagnosticsModel,
  buildLeaderboardModel,
  buildMarketIntelModel,
  buildReplayTimelineModel,
} from "@/lib/cockpit-event-models"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import {
  buildReplayGeneratedMatchups,
  buildReplayGeneratedSecondaryBets,
  getRawGeneratedMatchups,
  getRawGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import { formatDateTime, formatNumber, formatUnits } from "@/lib/format"
import { buildPredictionRunFromSection, collectAvailableBooks, flattenSecondaryBets, NON_BOOK_SOURCES, normalizeSportsbook } from "@/lib/prediction-board"
import type {
  CompositePlayer,
  DashboardState,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  MatchupBet,
  PastSnapshotEvent,
  PlayerProfile,
  PredictionRunResponse,
} from "@/lib/types"
import {
  ChartColumnIcon,
  EmptyState,
  SelectablePlayerName,
  TREND_ARROW,
  TREND_COLOR,
  buildMatchupKey,
  getTierStyle,
  secondaryBadgeLabel,
} from "@/pages/page-shared"


export function PredictionWorkspacePage({
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
  matchupSearch,
  onMatchupSearchChange,
  minEdge,
  onMinEdgeChange,
  filteredMatchups,
  gradingHistory,
  players,
  predictionRun,
  selectedPlayerKey,
  onPlayerSelect,
  selectedPlayerProfile,
  richProfilesEnabled,
  secondaryBets,
}: {
  dashboard?: DashboardState
  liveSnapshot: LiveRefreshSnapshot | null
  runtimeStatus: { label: string; tone: "good" | "warn" | "bad" }
  snapshotNotice: string | null
  snapshotAgeSeconds: number | null
  predictionTab: PredictionTab
  onPredictionTabChange: (value: PredictionTab) => void
  availableBooks: string[]
  selectedBooks: string[]
  onSelectedBooksChange: (value: string[]) => void
  matchupSearch: string
  onMatchupSearchChange: (value: string) => void
  minEdge: number
  onMinEdgeChange: (value: number) => void
  filteredMatchups: MatchupBet[]
  gradingHistory: GradedTournamentSummary[]
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
  selectedPlayerKey: string
  onPlayerSelect: (playerKey: string) => void
  selectedPlayerProfile?: PlayerProfile
  richProfilesEnabled: boolean
  secondaryBets: FlattenedSecondaryBet[]
}) {
  const [expandedMatchupKey, setExpandedMatchupKey] = useState<string | null>(null)
  const [selectedPastEventKey, setSelectedPastEventKey] = useState("")
  const [pastReplaySection, setPastReplaySection] = useState<"live" | "upcoming">("live")
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
    const merged = new Map<string, PastSnapshotEvent>()

    persisted.forEach((event) => {
      merged.set(event.event_id, event)
    })

    fallbackPastEvents.forEach((event) => {
      if (!merged.has(event.event_id)) {
        merged.set(event.event_id, event)
      }
    })

    return Array.from(merged.values())
  }, [fallbackPastEvents, pastEventsQuery.data?.events])
  const selectedPastEvent = useMemo(() => {
    if (pastEventOptions.length === 0) return null
    if (!selectedPastEventKey) return pastEventOptions[0]
    return pastEventOptions.find((event) => event.event_id === selectedPastEventKey) ?? pastEventOptions[0]
  }, [pastEventOptions, selectedPastEventKey])
  const pastSnapshotQuery = useQuery({
    queryKey: ["live-refresh-past-snapshot", selectedPastEvent?.event_id, pastReplaySection],
    queryFn: () => api.getLiveRefreshPastSnapshot(selectedPastEvent?.event_id ?? "", pastReplaySection),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })
  const pastTimelineQuery = useQuery({
    queryKey: ["live-refresh-past-timeline", selectedPastEvent?.event_id, pastReplaySection],
    queryFn: () =>
      api.getLiveRefreshPastTimeline(selectedPastEvent?.event_id ?? "", {
        section: pastReplaySection,
        limit: 24,
      }),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })
  const pastMarketRowsQuery = useQuery({
    queryKey: ["live-refresh-past-market-rows", selectedPastEvent?.event_id, pastReplaySection],
    queryFn: () =>
      api.getLiveRefreshPastMarketRows(selectedPastEvent?.event_id ?? "", {
        section: pastReplaySection,
        limit: 200,
      }),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })
  const pastSnapshotSection = pastSnapshotQuery.data?.ok ? (pastSnapshotQuery.data.snapshot ?? null) : null
  const pastPredictionRun = useMemo(
    () => buildPredictionRunFromSection(pastSnapshotSection),
    [pastSnapshotSection],
  )
  const pastTimelinePoints = useMemo(
    () => (pastTimelineQuery.data?.ok ? (pastTimelineQuery.data.points ?? []) : []),
    [pastTimelineQuery.data],
  )
  const pastMarketRows = useMemo(
    () => (pastMarketRowsQuery.data?.ok ? (pastMarketRowsQuery.data.rows ?? []) : []),
    [pastMarketRowsQuery.data],
  )
  const activePastReplaySnapshotId = pastSnapshotQuery.data?.ok ? (pastSnapshotQuery.data.snapshot_id ?? null) : null
  const pastReplayRows = useMemo(() => {
    if (!activePastReplaySnapshotId) {
      return pastMarketRows
    }

    return pastMarketRows.filter((row) => row.snapshot_id === activePastReplaySnapshotId)
  }, [activePastReplaySnapshotId, pastMarketRows])
  const selectedBookSet = useMemo(() => new Set(selectedBooks), [selectedBooks])
  const pastMatchups = useMemo(() => {
    const sourceRows =
      pastReplayRows.length > 0
        ? buildReplayGeneratedMatchups(pastReplayRows)
        : (pastPredictionRun?.matchup_bets_all_books ?? pastPredictionRun?.matchup_bets ?? [])
    return sourceRows.filter((matchup) => {
      const matchupBook = normalizeSportsbook(matchup.book)
      if (NON_BOOK_SOURCES.has(matchupBook)) return false
      const passesBook = selectedBookSet.size === 0 || (matchupBook ? selectedBookSet.has(matchupBook) : false)
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesBook && passesSearch && matchup.ev >= minEdge
    })
  }, [matchupSearch, minEdge, pastPredictionRun, pastReplayRows, selectedBookSet])
  const pastSecondaryBets = useMemo(() => {
    const sourceRows =
      pastReplayRows.length > 0
        ? buildReplayGeneratedSecondaryBets(pastReplayRows)
        : flattenSecondaryBets(pastPredictionRun)
    return sourceRows.filter((bet) => {
      const betBook = normalizeSportsbook(bet.book)
      if (betBook && NON_BOOK_SOURCES.has(betBook)) return false
      if (selectedBookSet.size === 0) return true
      return betBook ? selectedBookSet.has(betBook) : false
    })
  }, [pastPredictionRun, pastReplayRows, selectedBookSet])
  const displayPredictionRun = predictionTab === "past" ? pastPredictionRun : predictionRun
  const displayPlayers = useMemo(
    () => (predictionTab === "past" ? (pastPredictionRun?.composite_results ?? []) : players),
    [pastPredictionRun?.composite_results, players, predictionTab],
  )
  const displaySecondaryBets = predictionTab === "past" ? pastSecondaryBets : secondaryBets
  const displayAvailableBooks = useMemo(() => {
    if (predictionTab !== "past") {
      return availableBooks
    }

    const replayBooks = new Set<string>()
    pastReplayRows.forEach((row) => {
      const normalized = normalizeSportsbook(row.book)
      if (normalized && !NON_BOOK_SOURCES.has(normalized)) {
        replayBooks.add(normalized)
      }
    })

    if (replayBooks.size > 0) {
      return Array.from(replayBooks).sort()
    }

    return collectAvailableBooks(pastPredictionRun)
  }, [availableBooks, pastPredictionRun, pastReplayRows, predictionTab])
  const rawGeneratedMatchups = useMemo(
    () =>
      predictionTab === "past"
        ? (pastReplayRows.length > 0
            ? buildReplayGeneratedMatchups(pastReplayRows)
            : getRawGeneratedMatchups(displayPredictionRun))
        : getRawGeneratedMatchups(displayPredictionRun),
    [displayPredictionRun, pastReplayRows, predictionTab],
  )
  const rawGeneratedSecondaryBets = useMemo(
    () =>
      predictionTab === "past"
        ? (pastReplayRows.length > 0
            ? buildReplayGeneratedSecondaryBets(pastReplayRows)
            : getRawGeneratedSecondaryBets(displayPredictionRun))
        : getRawGeneratedSecondaryBets(displayPredictionRun),
    [displayPredictionRun, pastReplayRows, predictionTab],
  )
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
  const leaderboardRows = useMemo(
    () => (predictionTab === "past" ? (pastSnapshotSection?.leaderboard ?? []) : (activeSection?.leaderboard ?? [])),
    [activeSection?.leaderboard, pastSnapshotSection?.leaderboard, predictionTab],
  )
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
  const rawGeneratedPickCount = rawGeneratedMatchups.length + rawGeneratedSecondaryBets.length

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
        hasFilters: selectedBooks.length > 0 || matchupSearch.trim().length > 0 || minEdge > 0.02,
      })
  const { playerKeyByName, selectedPlayer, spotlight } = useCockpitSpotlight({
    predictionTab,
    isLiveActive,
    eventName,
    selectedPlayerKey,
    onPlayerSelect,
    players: displayPlayers,
    leaderboardRows,
    topPlays,
    rawGeneratedMatchups,
    rawGeneratedSecondaryBets,
  })
  const pastReplayNotice =
    predictionTab !== "past"
      ? null
      : pastSnapshotQuery.isFetching
        ? "Loading immutable replay assets for this event..."
        : pastSnapshotQuery.isError
          ? "No stored immutable snapshot was found for this event selection."
          : pastTimelineQuery.isError
            ? "Stored replay timeline is unavailable for this event selection."
            : pastMarketRowsQuery.isError
              ? "Stored market-row history is unavailable for this event selection."
              : selectedPastEvent
                ? `Reviewing ${pastReplaySection} replay captures for ${selectedPastEvent.event_name}.`
                : "Replay mode is ready."
  const courseFeedModel = useMemo(
    () =>
      buildCourseFeedModel({
        mode: predictionTab,
        snapshotAgeSeconds: predictionTab === "past" ? null : snapshotAgeSeconds,
        snapshotNotice: predictionTab === "past" ? pastReplayNotice : snapshotNotice,
        players: displayPlayers,
        timelinePoints: pastTimelinePoints,
        diagnosticsState: diagnostics?.state,
        fieldValidation: displayPredictionRun?.field_validation,
      }),
    [
      diagnostics?.state,
      displayPlayers,
      displayPredictionRun?.field_validation,
      pastReplayNotice,
      pastTimelinePoints,
      predictionTab,
      snapshotAgeSeconds,
      snapshotNotice,
    ],
  )
  const leaderboardModel = useMemo(
    () =>
      buildLeaderboardModel({
        mode: predictionTab,
        leaderboardRows,
        players: displayPlayers,
      }),
    [displayPlayers, leaderboardRows, predictionTab],
  )
  const marketIntelModel = useMemo(
    () =>
      buildMarketIntelModel({
        mode: predictionTab,
        currentSecondaryBets: displaySecondaryBets,
        pastMarketRows: pastReplayRows,
      }),
    [displaySecondaryBets, pastReplayRows, predictionTab],
  )
  const replayTimelineModel = useMemo(
    () =>
      buildReplayTimelineModel({
        mode: predictionTab,
        timelinePoints: pastTimelinePoints,
        currentGeneratedAt:
          predictionTab === "past" ? (pastSnapshotQuery.data?.generated_at ?? null) : (liveSnapshot?.generated_at ?? null),
        snapshotAgeSeconds: predictionTab === "past" ? null : snapshotAgeSeconds,
      }),
    [
      liveSnapshot?.generated_at,
      pastSnapshotQuery.data?.generated_at,
      pastTimelinePoints,
      predictionTab,
      snapshotAgeSeconds,
    ],
  )
  const diagnosticsModel = useMemo(
    () =>
      buildDiagnosticsModel({
        mode: predictionTab,
        diagnostics,
        dashboardAiAvailable: Boolean(dashboard?.ai_status?.available),
        strategySource: displayPredictionRun?.strategy_meta?.strategy_source,
        strategyName: displayPredictionRun?.strategy_meta?.strategy_name,
        warnings: displayPredictionRun?.warnings,
        gradingHistory,
        selectedEventId: predictionTab === "past" ? selectedPastEvent?.event_id : undefined,
        timelinePoints: pastTimelinePoints,
        currentSecondaryBets: displaySecondaryBets,
      }),
    [
      dashboard?.ai_status?.available,
      diagnostics,
      displayPredictionRun?.strategy_meta?.strategy_name,
      displayPredictionRun?.strategy_meta?.strategy_source,
      displayPredictionRun?.warnings,
      displaySecondaryBets,
      gradingHistory,
      pastTimelinePoints,
      predictionTab,
      selectedPastEvent?.event_id,
    ],
  )
  const headlineNotice = predictionTab === "past" ? pastReplayNotice : snapshotNotice
  const spotlightProfileQuery = useQuery({
    queryKey: ["cockpit-player-profile", predictionTab, selectedPlayerKey, displayPredictionRun?.tournament_id, displayPredictionRun?.course_num],
    queryFn: () =>
      api.getPlayerProfile(
        selectedPlayerKey,
        displayPredictionRun?.tournament_id ?? 0,
        displayPredictionRun?.course_num,
      ),
    enabled: richProfilesEnabled && Boolean(selectedPlayerKey && displayPredictionRun?.tournament_id),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  })
  const effectiveSpotlightProfile = spotlightProfileQuery.data ?? selectedPlayerProfile
  const effectiveProfileReady = Boolean(
    selectedPlayer && effectiveSpotlightProfile?.player_key === selectedPlayer.player_key,
  )

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
    <CockpitWorkspace
      leftRail={
        <>
          <CockpitModule
            title="Event switchboard / context"
            description="This locks the suite-level event switchboard into the left area while the shell keeps mode switching persistent above."
            tone="accent"
          >
            <div className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  {predictionTab === "live" ? "Live event" : predictionTab === "upcoming" ? "Upcoming event" : "Past event"}
                </p>
                <h3 className="mt-1 text-2xl font-semibold tracking-tight text-white">{eventName}</h3>
                {courseName ? <p className="mt-1 text-sm text-slate-400">{courseName}</p> : null}
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <MetricTile label="Field" value={String(fieldSize)} />
                <MetricTile label="Edges found" value={String(topPlays.length)} />
                <MetricTile label="Best edge" value={bestEdge > 0 ? `${(bestEdge * 100).toFixed(1)}%` : "--"} />
                <MetricTile
                  label="Runtime"
                  value={runtimeStatus.label}
                  tone={runtimeStatus.tone === "good" ? "positive" : runtimeStatus.tone === "bad" ? "warning" : "default"}
                />
              </div>
              {predictionTab === "past" ? (
                <div className="space-y-3">
                  <label className="block">
                    <span className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-500">Replay event</span>
                    <select
                      className="w-full rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/30"
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
                  <div>
                    <span className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-500">Replay lane</span>
                    <div className="flex flex-wrap gap-2">
                      {(["live", "upcoming"] as const).map((section) => {
                        const active = pastReplaySection === section
                        return (
                          <button
                            key={section}
                            type="button"
                            aria-pressed={active}
                            onClick={() => setPastReplaySection(section)}
                            className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] transition ${
                              active
                                ? "border-cyan-300/40 bg-cyan-400/15 text-cyan-100"
                                : "border-white/10 bg-white/5 text-slate-400 hover:border-white/25 hover:text-slate-200"
                            }`}
                          >
                            {section} capture
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-400">
                    {pastSnapshotQuery.isFetching
                      ? "Loading immutable snapshot replay for the selected event..."
                      : pastSnapshotQuery.isError
                        ? "No immutable snapshot found for this event yet. Run live refresh during event windows to capture replay history."
                        : selectedPastEvent
                          ? `Replay loaded from ${pastReplaySection} snapshot history${pastSnapshotQuery.data?.generated_at ? ` (${formatDateTime(pastSnapshotQuery.data.generated_at)}).` : "."}`
                          : "Select an event to load snapshot replay."}
                  </p>
                </div>
              ) : null}
            </div>
          </CockpitModule>

          <CockpitModule
            title="Course / weather / feed"
            description="Event-aware course context, weather lean, and a time-sensitive feed that stays honest across live, upcoming, and replay modes."
          >
            <CourseWeatherFeedPanel
              metrics={courseFeedModel.metrics}
              feedItems={courseFeedModel.feedItems}
            />
          </CockpitModule>
        </>
      }
      center={
        <>
          <CockpitModule
            title="Event headline"
            description="Primary tournament framing, freshness, and what matters right now."
            tone="accent"
            action={
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
            }
          >
            <div className="space-y-4">
              {headlineNotice ? (
                <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  {headlineNotice}
                  {predictionTab !== "past" && snapshotAgeSeconds !== null ? ` (snapshot age: ${snapshotAgeSeconds}s)` : ""}
                </div>
              ) : null}
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <MetricTile label="Field size" value={String(fieldSize)} />
                <MetricTile label="Featured edges" value={String(topPlays.slice(0, 5).length)} />
                <MetricTile label="All generated picks" value={String(rawGeneratedPickCount)} />
                <MetricTile
                  label="Season P/L"
                  value={formatUnits(totalProfit)}
                  tone={totalProfit >= 0 ? "positive" : "warning"}
                />
              </div>
              <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm leading-6 text-slate-300">
                {predictionTab === "live"
                  ? "The cockpit is focused on live tournament state, active edges, and the players most worth monitoring right now."
                  : predictionTab === "upcoming"
                    ? "The cockpit is focused on pre-tournament conviction, rankings, and event context before the market locks in."
                    : "The cockpit is focused on stored replay context, generated picks, and grading-aware review for completed events."}
              </div>
            </div>
          </CockpitModule>

          <CockpitModule
            title="Featured top plays"
            description={
              predictionTab === "live"
                ? "Highest-conviction live edges."
                : predictionTab === "upcoming"
                  ? "Highest-conviction pre-tournament matchup edges."
                  : "Stored replay of the strongest captured matchup edges."
            }
            action={
              <Link to="/matchups" className="flex items-center gap-1.5 text-sm text-cyan-300 transition hover:text-cyan-200">
                Legacy matchups route <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            }
          >
            <div className="space-y-4">
              <div className="space-y-3">
                {displayAvailableBooks.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-2">
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
                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                  <label className="block">
                    <span className="mb-1 block text-[10px] uppercase tracking-[0.18em] text-slate-500">Search matchups</span>
                    <input
                      type="text"
                      value={matchupSearch}
                      onChange={(event) => onMatchupSearchChange(event.target.value)}
                      placeholder="Search player names"
                      className="w-full rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/30"
                      aria-label="Search featured top plays"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-[10px] uppercase tracking-[0.18em] text-slate-500">Min edge</span>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      value={minEdge}
                      onChange={(event) => onMinEdgeChange(Number(event.target.value || 0))}
                      className="w-full rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/30"
                      aria-label="Minimum edge threshold"
                    />
                  </label>
                </div>
              </div>

              {predictionTab === "live" && !isLiveActive ? (
                <div className="rounded-2xl border border-white/10 bg-black/20 p-6">
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <Radar className="mb-3 h-8 w-8 text-slate-600" />
                    <p className="text-base font-medium text-white">No event is live right now</p>
                    <p className="mt-2 max-w-md text-sm text-slate-400">
                      Live edges will populate automatically after Thursday tee-off. Check{" "}
                      <button
                        type="button"
                        className="text-cyan-300 underline underline-offset-2 hover:text-cyan-200"
                        onClick={() => onPredictionTabChange("upcoming")}
                      >
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
                        <div className={`flex items-start justify-between gap-4 p-4 ${isExpanded ? "bg-white/3" : ""}`}>
                          <div className="min-w-0">
                            <p className="flex flex-wrap items-center gap-2 font-medium text-white">
                              <SelectablePlayerName playerKey={matchup.pick_key} label={matchup.pick} onSelect={onPlayerSelect} />
                              <span className="text-slate-500">over</span>
                              <SelectablePlayerName playerKey={matchup.opponent_key} label={matchup.opponent} onSelect={onPlayerSelect} />
                            </p>
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
                            <button
                              type="button"
                              aria-expanded={isExpanded}
                              aria-label={`${isExpanded ? "Collapse" : "Expand"} top play details`}
                              className="rounded-full border border-white/10 p-2 text-slate-400 transition hover:border-white/20 hover:text-slate-200"
                              onClick={() => setExpandedMatchupKey(isExpanded ? null : key)}
                            >
                              <ChevronDown className={`h-4 w-4 transition ${isExpanded ? "rotate-180" : ""}`} />
                            </button>
                          </div>
                        </div>
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
            </div>
          </CockpitModule>

          <CockpitModule
            title="All generated picks"
            description="Complete raw algorithm-generated output for the selected cockpit context. This inventory does not shrink when featured-play filters are active."
            action={<span className="text-xs uppercase tracking-[0.16em] text-slate-500">{rawGeneratedPickCount} total</span>}
          >
            {rawGeneratedPickCount > 0 ? (
              <div className="space-y-5">
                {selectedBooks.length > 0 ? (
                  <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100">
                    Featured top-play modules respect active book filters. This inventory stays on the full generated set.
                  </div>
                ) : null}
                <div>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Matchups</p>
                    <p className="text-xs text-slate-500">{rawGeneratedMatchups.length} rows</p>
                  </div>
                  {rawGeneratedMatchups.length > 0 ? (
                    <div className="space-y-2">
                      {rawGeneratedMatchups.map((matchup) => (
                        <div key={`all-${buildMatchupKey(matchup)}`} className="flex items-center justify-between gap-4 rounded-xl border border-white/8 bg-black/20 px-4 py-3">
                          <div className="min-w-0">
                            <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-white">
                              <SelectablePlayerName playerKey={matchup.pick_key} label={matchup.pick} onSelect={onPlayerSelect} />
                              <span className="text-slate-500">over</span>
                              <SelectablePlayerName playerKey={matchup.opponent_key} label={matchup.opponent} onSelect={onPlayerSelect} />
                            </p>
                            <p className="mt-1 text-xs text-slate-500">{matchup.book ?? "book"} · {matchup.odds}</p>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${getTierStyle(matchup.tier)}`}>
                              {matchup.tier ?? "lean"}
                            </span>
                            <p className="text-sm font-semibold text-cyan-200">{matchup.ev_pct}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message={diagnosticsMessage} />
                  )}
                </div>

                <div>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Secondary markets</p>
                    <p className="text-xs text-slate-500">{rawGeneratedSecondaryBets.length} rows</p>
                  </div>
                  {rawGeneratedSecondaryBets.length > 0 ? (
                    <div className="space-y-2">
                      {rawGeneratedSecondaryBets.map((bet) => {
                        const playerKey = bet.player_key ?? playerKeyByName.get(bet.player.toLowerCase().trim())
                        return (
                          <div key={`secondary-${bet.market}-${bet.player}-${bet.odds}`} className="flex items-center justify-between gap-4 rounded-xl border border-white/8 bg-black/20 px-4 py-3">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-white">
                                <SelectablePlayerName playerKey={playerKey} label={bet.player} onSelect={onPlayerSelect} />
                              </p>
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
                              <p className="text-xs text-slate-500">{bet.book ? `${bet.book} · ${bet.odds}` : bet.odds}</p>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <EmptyState message="No secondary market rows surfaced for this context." />
                  )}
                </div>
              </div>
            ) : (
              <EmptyState message={predictionTab === "past" ? diagnosticsMessage : "No algorithm-generated picks are available for this event context yet."} />
            )}
          </CockpitModule>

          <CockpitModule
            title="Leaderboard"
            description={
              predictionTab === "upcoming"
                ? "Pre-event seeded board until real scoring arrives."
                : "Live or replay standings with mode-sensitive context."
            }
          >
            <LeaderboardPanel
              metrics={leaderboardModel.metrics}
              rows={leaderboardModel.rows}
              seededFromRankings={leaderboardModel.seededFromRankings}
              emptyMessage={leaderboardModel.emptyMessage}
              onPlayerSelect={onPlayerSelect}
            />
          </CockpitModule>

          <CockpitModule
            title="Power rankings"
            description="Model board with direct spotlight drill-in."
            action={
              <Link to="/players" className="flex items-center gap-1.5 text-sm text-cyan-300 transition hover:text-cyan-200">
                Legacy players route <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            }
          >
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
                            <SelectablePlayerName playerKey={player.player_key} label={player.player_display} onSelect={onPlayerSelect} />
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
          </CockpitModule>

          <CockpitModule
            title="Market intel"
            description="Mode-aware pricing context: current secondary edges for live/upcoming, persisted market history for replay."
          >
            <MarketIntelPanel
              metrics={marketIntelModel.metrics}
              rows={marketIntelModel.rows}
              emptyMessage={marketIntelModel.emptyMessage}
              onPlayerSelect={onPlayerSelect}
            />
          </CockpitModule>

          <CockpitModule
            title="Replay / timeline context"
            description={
              predictionTab === "past"
                ? "Immutable replay history for this completed event, using stored timeline captures."
                : "What replay review will preserve once this event has snapshot history."
            }
          >
            <ReplayTimelinePanel
              metrics={replayTimelineModel.metrics}
              items={replayTimelineModel.items}
              emptyMessage={replayTimelineModel.emptyMessage}
            />
          </CockpitModule>
        </>
      }
      rightRail={
        <>
          <CockpitModule
            title="Player spotlight"
            description="A single spotlight surface that updates from rankings, leaderboard rows, and generated picks."
            tone="accent"
            emptyState="Select a player from the cockpit to load the spotlight."
          >
            <PlayerSpotlightPanel
              spotlight={spotlight}
              player={selectedPlayer}
              profile={effectiveSpotlightProfile}
              profileReady={effectiveProfileReady}
              richProfilesEnabled={richProfilesEnabled}
            />
          </CockpitModule>

          <CockpitModule
            title="Diagnostics / grading context"
            description="Actionable runtime health, exclusion reasons, and grading continuity for the current cockpit mode."
            action={
              <Button size="sm" variant="outline" onClick={handleExportMarkdown} disabled={!displayPredictionRun?.card_content}>
                <Download className="mr-1.5 h-3.5 w-3.5" />
                Export markdown
              </Button>
            }
          >
            <div className="space-y-4">
              <DiagnosticsGradingPanel
                metrics={diagnosticsModel.metrics}
                counters={diagnosticsModel.counters}
                reasonCodes={diagnosticsModel.reasonCodes}
                warnings={diagnosticsModel.warnings}
                selectedEventSummary={diagnosticsModel.selectedEventSummary}
              />
              <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Recent grading context</p>
                  <Link to="/grading" className="text-sm text-cyan-300 transition hover:text-cyan-200">
                    Legacy grading route
                  </Link>
                </div>
                {gradingHistory.length > 0 ? (
                  <div className="space-y-2">
                    {gradingHistory.slice(0, 4).map((event) => {
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
                ) : (
                  <EmptyState message="Grade a tournament to populate review context." />
                )}
              </div>
            </div>
          </CockpitModule>
        </>
      }
    />
  )
}
