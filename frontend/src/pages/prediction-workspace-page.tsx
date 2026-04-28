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
import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import { TeamEventNotice } from "@/components/cockpit/team-event-notice"
import { isTeamEvent } from "@/lib/event-format"
import { CockpitModule, CockpitWorkspace } from "@/components/cockpit/workspace"
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
import { formatNumber, formatUnits } from "@/lib/format"
import {
  buildPredictionRunFromSection,
  collectAvailableBooks,
  flattenSecondaryBets,
  NON_BOOK_SOURCES,
  normalizeSportsbook,
} from "@/lib/prediction-board"
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
  buildMatchupKey,
  secondaryBadgeLabel,
  TREND_ARROW,
  TREND_COLOR,
} from "@/pages/page-shared"

/* ── Small helpers ────────────────────────────── */
function EV({ ev, evPct }: { ev: number; evPct?: string }) {
  const cls = ev >= 0.08 ? "high" : ev >= 0.04 ? "medium" : "low"
  return <span className={`ev-badge ${cls}`}>{evPct ?? `${(ev * 100).toFixed(1)}%`}</span>
}

function TierBadge({ tier }: { tier?: string }) {
  const t = tier ?? "LEAN"
  return <span className={`tier-badge ${t}`}>{t}</span>
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-title">{message}</div>
    </div>
  )
}

function ScoreBar({
  value,
  max = 100,
  color = "green",
}: {
  value: number
  max?: number
  color?: "green" | "gold" | "cyan"
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className="score-bar">
      <div className="score-bar-track">
        <div className={`score-bar-fill ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="score-bar-val">{formatNumber(value, 1)}</span>
    </div>
  )
}

/* ── Props ────────────────────────────────────── */
export function PredictionWorkspacePage({
  dashboard,
  liveSnapshot,
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
  const [pastReplaySection, setPastReplaySection] = useState<"completed" | "live" | "upcoming">(
    "completed",
  )

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
    persisted.forEach((event) => merged.set(event.event_id, event))
    fallbackPastEvents.forEach((event) => {
      if (!merged.has(event.event_id)) merged.set(event.event_id, event)
    })
    return Array.from(merged.values())
  }, [fallbackPastEvents, pastEventsQuery.data?.events])

  const selectedPastEvent = useMemo(() => {
    if (pastEventOptions.length === 0) return null
    if (!selectedPastEventKey) return pastEventOptions[0]
    return (
      pastEventOptions.find((event) => event.event_id === selectedPastEventKey) ??
      pastEventOptions[0]
    )
  }, [pastEventOptions, selectedPastEventKey])

  const pastSnapshotQuery = useQuery({
    queryKey: ["live-refresh-past-snapshot", selectedPastEvent?.event_id, pastReplaySection],
    queryFn: () =>
      api.getLiveRefreshPastSnapshot(selectedPastEvent?.event_id ?? "", pastReplaySection),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })

  const pastReplayHasHistoryLanes =
    pastReplaySection === "live" || pastReplaySection === "upcoming"

  const pastTimelineQuery = useQuery({
    queryKey: ["live-refresh-past-timeline", selectedPastEvent?.event_id, pastReplaySection],
    queryFn: () => {
      const lane = pastReplaySection
      if (lane !== "live" && lane !== "upcoming") {
        throw new Error("Past timeline is only available for live or upcoming lanes.")
      }
      return api.getLiveRefreshPastTimeline(selectedPastEvent?.event_id ?? "", {
        section: lane,
        limit: 24,
      })
    },
    enabled:
      predictionTab === "past" &&
      Boolean(selectedPastEvent?.event_id) &&
      pastReplayHasHistoryLanes,
    staleTime: 30_000,
  })

  const pastMarketRowsQuery = useQuery({
    queryKey: ["live-refresh-past-market-rows", selectedPastEvent?.event_id, pastReplaySection],
    queryFn: () => {
      const lane = pastReplaySection
      if (lane !== "live" && lane !== "upcoming") {
        throw new Error("Past market rows are only available for live or upcoming lanes.")
      }
      return api.getLiveRefreshPastMarketRows(selectedPastEvent?.event_id ?? "", {
        section: lane,
        limit: 200,
      })
    },
    enabled:
      predictionTab === "past" &&
      Boolean(selectedPastEvent?.event_id) &&
      pastReplayHasHistoryLanes,
    staleTime: 30_000,
  })

  const pastSnapshotSection = pastSnapshotQuery.data?.ok
    ? (pastSnapshotQuery.data.snapshot ?? null)
    : null
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

  const activePastReplaySnapshotId = pastSnapshotQuery.data?.ok
    ? (pastSnapshotQuery.data.snapshot_id ?? null)
    : null
  const pastReplayRows = useMemo(() => {
    if (!activePastReplaySnapshotId) return pastMarketRows
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
      const passesBook =
        selectedBookSet.size === 0 || (matchupBook ? selectedBookSet.has(matchupBook) : false)
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
    if (predictionTab !== "past") return availableBooks
    const replayBooks = new Set<string>()
    pastReplayRows.forEach((row) => {
      const normalized = normalizeSportsbook(row.book)
      if (normalized && !NON_BOOK_SOURCES.has(normalized)) replayBooks.add(normalized)
    })
    if (replayBooks.size > 0) return Array.from(replayBooks).sort()
    return collectAvailableBooks(pastPredictionRun)
  }, [availableBooks, pastPredictionRun, pastReplayRows, predictionTab])

  const rawGeneratedMatchups = useMemo(
    () =>
      predictionTab === "past"
        ? pastReplayRows.length > 0
          ? buildReplayGeneratedMatchups(pastReplayRows)
          : getRawGeneratedMatchups(displayPredictionRun)
        : getRawGeneratedMatchups(displayPredictionRun),
    [displayPredictionRun, pastReplayRows, predictionTab],
  )
  const rawGeneratedSecondaryBets = useMemo(
    () =>
      predictionTab === "past"
        ? pastReplayRows.length > 0
          ? buildReplayGeneratedSecondaryBets(pastReplayRows)
          : getRawGeneratedSecondaryBets(displayPredictionRun)
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
      ? (selectedPastEvent?.event_name ?? "Past event snapshot unavailable")
      : (activeSection?.event_name ?? displayPredictionRun?.event_name ?? "No event loaded")

  const courseName =
    predictionTab === "past"
      ? (pastPredictionRun?.course_name ?? "")
      : (activeSection?.course_name ?? displayPredictionRun?.course_name ?? "")

  const fieldSize =
    predictionTab === "past"
      ? (pastPredictionRun?.field_size ?? null)
      : (activeSection?.field_size ?? displayPredictionRun?.field_size ?? null)

  const diagnosticsMessage =
    predictionTab === "past"
      ? "Select a past event from the replay selector to load market data."
      : getMatchupStateMessage({
          state: activeSection?.diagnostics?.state,
          reasonCodes: activeSection?.diagnostics?.reason_codes,
          hasFilters: selectedBooks.length > 0,
        })

  const topPlays = predictionTab === "past" ? pastMatchups : filteredMatchups

  // Team-format events (Zurich Classic) intentionally short-circuit the
  // pipeline in the backend (see src/event_format.py). Mirror the skip on
  // the frontend by replacing the bettable-card modules with an explanatory
  // notice — never show an empty placement / matchup board that implies the
  // model ran but found nothing.
  const showTeamEventNotice =
    (predictionTab === "live" || predictionTab === "upcoming") && isTeamEvent(activeSection)

  // Cockpit modules (using exact API signatures from cockpit-event-models.ts)
  const mode = predictionTab as "live" | "upcoming" | "past"

  const leaderboardModel = buildLeaderboardModel({
    mode,
    leaderboardRows: activeSection?.leaderboard ?? pastSnapshotSection?.leaderboard ?? [],
    players: displayPlayers,
  })
  const marketIntelModel = buildMarketIntelModel({
    mode,
    currentSecondaryBets: displaySecondaryBets,
    pastMarketRows: pastReplayRows,
  })
  const courseFeedModel = buildCourseFeedModel({
    mode,
    snapshotAgeSeconds: snapshotAgeSeconds,
    snapshotNotice: snapshotNotice,
    players: displayPlayers,
    timelinePoints: pastTimelinePoints,
    diagnosticsState: activeSection?.diagnostics?.state ?? pastSnapshotSection?.diagnostics?.state,
    fieldValidation: displayPredictionRun?.field_validation,
  })
  const diagnosticsModel = buildDiagnosticsModel({
    mode,
    diagnostics: activeSection?.diagnostics as Parameters<typeof buildDiagnosticsModel>[0]["diagnostics"],
    dashboardAiAvailable: dashboard?.ai_status?.available ?? false,
    strategySource: dashboard?.baseline_provenance?.strategy_source,
    strategyName: dashboard?.baseline_provenance?.live_strategy_name,
    warnings: displayPredictionRun?.warnings,
    gradingHistory,
    selectedEventId: selectedPastEvent?.event_id,
    timelinePoints: pastTimelinePoints,
    currentSecondaryBets: displaySecondaryBets,
  })
  const replayTimelineModel = buildReplayTimelineModel({
    mode,
    timelinePoints: pastTimelinePoints,
    currentGeneratedAt: activeSection?.generated_from ?? null,
    snapshotAgeSeconds: snapshotAgeSeconds,
  })

  // Player spotlight
  const { spotlight, selectedPlayer } = useCockpitSpotlight({
    predictionTab: mode,
    isLiveActive,
    eventName,
    selectedPlayerKey,
    onPlayerSelect,
    players: displayPlayers,
    leaderboardRows: activeSection?.leaderboard ?? pastSnapshotSection?.leaderboard ?? [],
    topPlays,
    rawGeneratedMatchups,
    rawGeneratedSecondaryBets,
  })
  const effectiveSpotlightProfile = selectedPlayerProfile
  const effectiveProfileReady =
    Boolean(selectedPlayerProfile) &&
    selectedPlayerProfile?.player_key === selectedPlayerKey

  function handleExportMarkdown() {
    const content = displayPredictionRun?.card_content
    if (!content) return
    const blob = new Blob([content], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${eventName.replace(/\s+/g, "-").toLowerCase()}-picks.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  /* ── KPI summary strip ──────────────────────── */
  const totalHits = gradingHistory.reduce((s, t) => s + (t.hits ?? 0), 0)
  const totalPicks = gradingHistory.reduce((s, t) => s + (t.graded_pick_count ?? 0), 0)
  const hitRate = totalPicks > 0 ? (totalHits / totalPicks) * 100 : 0

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      {/* ── Notice bar ──────────────────────────── */}
      {snapshotNotice && (
        <div className="alert-banner">
          <Radar size={11} style={{ flexShrink: 0 }} />
          {snapshotNotice}
        </div>
      )}

      {/* ── KPI strip — Bloomberg hero numbers, fixed height ── */}
      <div className="kpi-strip">
        <div className="kpi-cell">
          <div className="kpi-cell-label">Event</div>
          <div className="kpi-cell-value" style={{ fontSize: 13, color: "var(--text)" }}>{eventName}</div>
          {courseName && <div className="kpi-cell-sub">{courseName}</div>}
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Field</div>
          <div className="kpi-cell-value cyan">{fieldSize ?? "—"}</div>
          <div className="kpi-cell-sub">players</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Total P&L</div>
          <div className={`kpi-cell-value ${totalProfit >= 0 ? "green" : "red"}`}>{formatUnits(totalProfit)}</div>
          <div className="kpi-cell-sub">all graded events</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Hit rate</div>
          <div className="kpi-cell-value">{totalPicks > 0 ? `${hitRate.toFixed(0)}%` : "—"}</div>
          <div className="kpi-cell-sub">{totalHits}/{totalPicks} picks</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Snapshot age</div>
          <div className={`kpi-cell-value ${snapshotAgeSeconds !== null && snapshotAgeSeconds > 120 ? "gold" : ""}`}>
            {snapshotAgeSeconds !== null ? `${snapshotAgeSeconds}s` : "—"}
          </div>
          <div className="kpi-cell-sub">data freshness</div>
        </div>
      </div>

      {/* ── Three-column cockpit ─────────────────── */}
      <CockpitWorkspace
        className="cockpit-fill"
        leftRail={
          <>
            {/* Past event selector */}
            {predictionTab === "past" && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Replay selector</div>
                </div>
                <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 4 }}>
                      Event
                    </div>
                    <select
                      value={selectedPastEventKey || selectedPastEvent?.event_id || ""}
                      onChange={(e) => setSelectedPastEventKey(e.target.value)}
                      style={{
                        width: "100%",
                        background: "var(--surface-2)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--r-md)",
                        color: "var(--text)",
                        fontSize: 12,
                        padding: "6px 10px",
                        outline: "none",
                      }}
                      data-testid="past-event-select"
                    >
                      {pastEventOptions.map((e) => (
                        <option key={e.event_id} value={e.event_id}>
                          {e.event_name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 4 }}>
                      Lane
                    </div>
                    <div style={{ display: "flex", gap: 4 }}>
                      {(["completed", "live", "upcoming"] as const).map((lane) => (
                        <button
                          key={lane}
                          onClick={() => setPastReplaySection(lane)}
                          style={{
                            flex: 1,
                            padding: "5px 0",
                            borderRadius: "var(--r-sm)",
                            fontSize: 11,
                            fontWeight: 600,
                            background:
                              pastReplaySection === lane ? "var(--green-dim)" : "var(--surface-2)",
                            border: `1px solid ${pastReplaySection === lane ? "rgba(34,197,94,0.25)" : "var(--border)"}`,
                            color:
                              pastReplaySection === lane ? "var(--green)" : "var(--text-muted)",
                            cursor: "pointer",
                            textTransform: "capitalize",
                          }}
                        >
                          {lane}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Course + weather context */}
            <CockpitModule title="Course & weather" description="Feed for the active event context.">
              <CourseWeatherFeedPanel
                metrics={courseFeedModel.metrics}
                feedItems={courseFeedModel.feedItems}
              />
            </CockpitModule>

            {/* Book filters */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">Filters</div>
                {selectedBooks.length > 0 && (
                  <button
                    className="btn btn-ghost"
                    style={{ padding: "3px 8px", fontSize: 11 }}
                    onClick={() => onSelectedBooksChange([])}
                  >
                    Clear
                  </button>
                )}
              </div>
              <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* Book chips */}
                {displayAvailableBooks.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 6 }}>
                      Sportsbook
                    </div>
                    <div className="filter-chips">
                      {displayAvailableBooks.map((book) => (
                        <button
                          key={book}
                          onClick={() => {
                            const next = selectedBooks.includes(book)
                              ? selectedBooks.filter((b) => b !== book)
                              : [...selectedBooks, book]
                            onSelectedBooksChange(next)
                          }}
                          className={`filter-chip${selectedBooks.includes(book) ? " active" : ""}`}
                          data-testid={`book-chip-${book}`}
                        >
                          {book}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Search */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 6 }}>
                    Search player
                  </div>
                  <div className="search-input">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--text-faint)", flexShrink: 0 }}>
                      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
                    </svg>
                    <input
                      type="text"
                      value={matchupSearch}
                      onChange={(e) => onMatchupSearchChange(e.target.value)}
                      placeholder="Player name…"
                      aria-label="Search matchups by player name"
                      data-testid="search-matchups"
                    />
                  </div>
                </div>

                {/* Min edge */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 6 }}>
                    Min edge: <span style={{ color: "var(--text-muted)" }}>{(minEdge * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="0.2"
                    step="0.01"
                    value={minEdge}
                    onChange={(e) => onMinEdgeChange(Number(e.target.value))}
                    style={{ width: "100%", accentColor: "var(--green)" }}
                    aria-label="Minimum edge threshold"
                    data-testid="min-edge-slider"
                  />
                </div>
              </div>
            </div>

            {/* Recent grading */}
            <div className="card">
              <div className="card-header">
                <div className="card-title">Recent results</div>
                <Link
                  to="/grading"
                  style={{ fontSize: 11, color: "var(--text-muted)", textDecoration: "none" }}
                >
                  All →
                </Link>
              </div>
              <div style={{ overflow: "hidden" }}>
                {gradingHistory.length > 0 ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Event</th>
                        <th className="right">P&L</th>
                        <th className="right">Hit%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {gradingHistory.slice(0, 5).map((event) => {
                        const profit = Number(event.total_profit ?? 0)
                        const picks = event.graded_pick_count ?? 0
                        const hits = event.hits ?? 0
                        const hr = picks > 0 ? ((hits / picks) * 100).toFixed(0) : "—"
                        return (
                          <tr key={`${event.event_id}-${event.year}`}>
                            <td className="player-name" title={event.name}>{event.name}</td>
                            <td
                              className="right num"
                              style={{
                                color:
                                  profit >= 0 ? "var(--positive)" : "var(--danger)",
                                fontWeight: 600,
                              }}
                            >
                              {formatUnits(profit)}
                            </td>
                            <td className="right num" style={{ color: "var(--text-muted)" }}>
                              {typeof hr === "string" ? hr : `${hr}%`}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                ) : (
                  <div className="card-body">
                    <EmptyState message="No graded events yet." />
                  </div>
                )}
              </div>
            </div>
          </>
        }
        center={
          <>
            {showTeamEventNotice && (
              <TeamEventNotice
                eventName={eventName}
                courseName={courseName}
                mode={predictionTab === "live" ? "live" : "upcoming"}
              />
            )}
            {!showTeamEventNotice && (
              <>
            {/* ── Top Plays (Matchups) ──────────────── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">
                    {predictionTab === "past" ? "Generated picks" : "Top picks"}
                  </div>
                  <div className="card-desc">
                    {predictionTab === "past"
                      ? `${topPlays.length} picks generated for this event`
                      : `${topPlays.length} qualifying lines · edge ≥ ${(minEdge * 100).toFixed(0)}%`}
                  </div>
                </div>
                <button
                  className="btn btn-ghost"
                  onClick={handleExportMarkdown}
                  disabled={!displayPredictionRun?.card_content}
                  style={{ padding: "5px 10px" }}
                  data-testid="btn-export"
                >
                  <Download size={12} />
                  Export
                </button>
              </div>

              <div style={{ overflow: "hidden" }}>
                {predictionTab === "live" && !isLiveActive ? (
                  <div className="card-body">
                    <div className="empty-state">
                      <Radar size={28} className="empty-state-icon" />
                      <div className="empty-state-title">No live event</div>
                      <div className="empty-state-desc">
                        Switch to{" "}
                        <button
                          style={{ color: "var(--cyan)", textDecoration: "underline", background: "none", border: "none", cursor: "pointer", fontSize: "inherit" }}
                          onClick={() => onPredictionTabChange("upcoming")}
                        >
                          Upcoming
                        </button>{" "}
                        for pre-tournament picks.
                      </div>
                    </div>
                  </div>
                ) : topPlays.length > 0 ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Pick</th>
                        <th>Book · Odds</th>
                        <th className="center">Tier</th>
                        <th className="right">EV</th>
                        <th className="right">Win%</th>
                        <th style={{ width: 32 }} />
                      </tr>
                    </thead>
                    <tbody>
                      {topPlays.map((matchup) => {
                        const key = buildMatchupKey(matchup)
                        const isExpanded = expandedMatchupKey === key
                        return (
                          <>
                            <tr
                              key={key}
                              onClick={() => setExpandedMatchupKey(isExpanded ? null : key)}
                              style={{ cursor: "pointer" }}
                              data-testid={`matchup-row-${key}`}
                            >
                              <td>
                                <div style={{ fontWeight: 600, color: "var(--text)", fontSize: 13 }}>
                                  {matchup.pick}
                                </div>
                                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                                  vs {matchup.opponent}
                                </div>
                              </td>
                              <td>
                                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                  {matchup.book ?? "—"}
                                </div>
                                <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 600 }}>
                                  {matchup.odds}
                                </div>
                              </td>
                              <td className="center">
                                <TierBadge tier={matchup.tier} />
                              </td>
                              <td className="right">
                                <EV ev={matchup.ev} evPct={matchup.ev_pct} />
                              </td>
                              <td className="right num" style={{ color: "var(--text-muted)", fontSize: 12 }}>
                                {(matchup.model_win_prob * 100).toFixed(1)}%
                              </td>
                              <td style={{ textAlign: "center" }}>
                                <ChevronDown
                                  size={14}
                                  style={{
                                    color: "var(--text-faint)",
                                    transform: isExpanded ? "rotate(180deg)" : "none",
                                    transition: "transform 180ms ease",
                                  }}
                                />
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr key={`${key}-detail`}>
                                <td colSpan={6} style={{ padding: 0 }}>
                                  <div className="matchup-detail">
                                    <div className="matchup-detail-grid">
                                      <div>
                                        <div className="detail-item-label">Composite gap</div>
                                        <div className="detail-item-value num">{formatNumber(matchup.composite_gap, 2)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label">Form gap</div>
                                        <div className="detail-item-value num">{formatNumber(matchup.form_gap, 2)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label">Course gap</div>
                                        <div className="detail-item-value num">{formatNumber(matchup.course_fit_gap, 2)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label">Implied prob</div>
                                        <div className="detail-item-value num">{(matchup.implied_prob * 100).toFixed(1)}%</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label">Conviction</div>
                                        <div className="detail-item-value num">{formatNumber(matchup.conviction, 0)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label">Momentum</div>
                                        <div className="detail-item-value" style={{ color: matchup.momentum_aligned ? "var(--positive)" : "var(--text-muted)" }}>
                                          {matchup.momentum_aligned ? "Aligned ↑" : "Mixed"}
                                        </div>
                                      </div>
                                    </div>
                                    {matchup.reason && (
                                      <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
                                        {matchup.reason}
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </>
                        )
                      })}
                    </tbody>
                  </table>
                ) : (
                  <div className="card-body">
                    <EmptyState message={diagnosticsMessage} />
                  </div>
                )}
              </div>
            </div>

            {/* ── Power Rankings table ──────────────── */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">
                    {predictionTab === "past" ? "Pre-tee-off rankings" : "Power rankings"}
                  </div>
                  <div className="card-desc">
                    {predictionTab === "past"
                      ? `${displayPlayers.length} players — last rankings before tee off`
                      : `${displayPlayers.length} players ranked by model`}
                  </div>
                </div>
                <Link
                  to="/players"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 11,
                    color: "var(--text-muted)",
                    textDecoration: "none",
                  }}
                >
                  All <ExternalLink size={11} />
                </Link>
              </div>
              <div style={{ overflow: "hidden" }}>
                {displayPlayers.length > 0 ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th style={{ width: 36 }}>#</th>
                        <th>Player</th>
                        <th>Composite</th>
                        <th>Form</th>
                        <th>Course</th>
                        <th className="center">Trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayPlayers.slice(0, 15).map((player) => {
                        const dir = player.momentum_direction ?? ""
                        const arrow = TREND_ARROW[dir] ?? "—"
                        const trendColor = TREND_COLOR[dir] ?? "var(--text-faint)"
                        return (
                          <tr
                            key={player.player_key}
                            onClick={() => onPlayerSelect(player.player_key)}
                            data-testid={`player-row-${player.player_key}`}
                          >
                            <td className="rank-cell">{player.rank}</td>
                            <td className="player-name">
                              <button onClick={() => onPlayerSelect(player.player_key)}>
                                {player.player_display}
                              </button>
                            </td>
                            <td>
                              <ScoreBar value={player.composite} max={100} color="cyan" />
                            </td>
                            <td>
                              <ScoreBar value={player.form} max={100} color="green" />
                            </td>
                            <td>
                              <ScoreBar value={player.course_fit} max={100} color="gold" />
                            </td>
                            <td className="center">
                              <span style={{ color: trendColor, fontSize: 14, fontWeight: 700 }}>
                                {arrow}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                ) : (
                  <div className="card-body">
                    <EmptyState message="No rankings available for this event context." />
                  </div>
                )}
              </div>
            </div>

            {/* ── Secondary bets ───────────────────── */}
            {displaySecondaryBets.length > 0 && (
              <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: 0, maxHeight: 320 }}>
                <div className="card-header">
                  <div className="card-title">Secondary markets</div>
                  <div className="card-desc">
                    {displaySecondaryBets.length} picks
                    <Link
                      to="/matchups?tab=secondary"
                      style={{ marginLeft: 8, color: "var(--cyan)", fontSize: 10, textDecoration: "none" }}
                    >
                      All →
                    </Link>
                  </div>
                </div>
                <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Market</th>
                        <th>Book · Odds</th>
                        <th className="right">EV</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displaySecondaryBets.map((bet) => {
                        const tier = (bet.confidence ?? "LEAN").toUpperCase()
                        return (
                          <tr
                            key={`${bet.market}-${bet.player}-${bet.odds}`}
                            onClick={() => bet.player_key && onPlayerSelect(bet.player_key)}
                            data-testid={`secondary-row-${bet.player}`}
                          >
                            <td className="player-name">
                              <button onClick={() => bet.player_key && onPlayerSelect(bet.player_key)}>
                                {bet.player}
                              </button>
                            </td>
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span className={`tier-badge ${tier}`} style={{ fontSize: 9 }}>
                                  {tier}
                                </span>
                                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                  {secondaryBadgeLabel(bet.market)}
                                </span>
                              </div>
                            </td>
                            <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                              {bet.book ? `${bet.book} · ${bet.odds}` : bet.odds}
                            </td>
                            <td className="right">
                              <EV ev={bet.ev} />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Leaderboard — live & past only, not upcoming ─── */}
            {predictionTab !== "upcoming" && (
              <CockpitModule
                title={predictionTab === "past" ? "Final leaderboard" : "Live leaderboard"}
                description={
                  predictionTab === "past"
                    ? "Final standings at event close."
                    : "Live scoring — updates in real time."
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
            )}
              </>
            )}
          </>
        }
        rightRail={
          <>
            {/* ── Player spotlight ─────────────────── */}
            <CockpitModule
              title="Player spotlight"
              tone="accent"
              emptyState={
                selectedPlayerKey ? undefined : "Click any player to open spotlight."
              }
            >
              <PlayerSpotlightPanel
                spotlight={spotlight}
                player={selectedPlayer}
                profile={effectiveSpotlightProfile}
                profileReady={effectiveProfileReady}
                richProfilesEnabled={richProfilesEnabled}
              />
            </CockpitModule>

            {/* ── Market intel ─────────────────────── */}
            <CockpitModule
              title="Market intel"
              description="Secondary edges for this event context."
            >
              <MarketIntelPanel
                metrics={marketIntelModel.metrics}
                rows={marketIntelModel.rows}
                emptyMessage={marketIntelModel.emptyMessage}
                onPlayerSelect={onPlayerSelect}
              />
            </CockpitModule>

            {/* ── Diagnostics ──────────────────────── */}
            <CockpitModule
              title="Diagnostics"
              description="Runtime health and pipeline state."
            >
              <DiagnosticsGradingPanel
                metrics={diagnosticsModel.metrics}
                counters={diagnosticsModel.counters}
                reasonCodes={diagnosticsModel.reasonCodes}
                warnings={diagnosticsModel.warnings}
                selectedEventSummary={diagnosticsModel.selectedEventSummary}
              />
            </CockpitModule>

            {/* ── Replay timeline ──────────────────── */}
            <CockpitModule
              title="Replay timeline"
              description={
                predictionTab === "past"
                  ? "Immutable replay history."
                  : "Timeline captured once event has history."
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
      />
    </div>
  )
}
