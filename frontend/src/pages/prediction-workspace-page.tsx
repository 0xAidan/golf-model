import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Download, ExternalLink, Radar } from "lucide-react"
import { Link } from "react-router-dom"

import { MatchupExpandDetail } from "@/components/cockpit/matchup-expand-detail"
import {
  CourseWeatherFeedPanel,
  LeaderboardPanel,
} from "@/components/cockpit/event-modules"
import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import { TeamEventNotice } from "@/components/cockpit/team-event-notice"
import { EdgeBadge, TierBadge } from "@/components/ui/edge-badge"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { isTeamEvent } from "@/lib/event-format"
import { CockpitResizableStack } from "@/components/cockpit/cockpit-resizable-stack"
import { CockpitVerticalSections } from "@/components/cockpit/responsive-panels"
import { CockpitModule, CockpitWorkspace } from "@/components/cockpit/workspace"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { FilterSheet } from "@/components/ui/filter-sheet"
import { useCockpitSpotlight } from "@/hooks/use-cockpit-spotlight"
import { useIsNarrowViewport } from "@/hooks/use-media-query"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import { api } from "@/lib/api"
import {
  buildCourseFeedModel,
  buildLeaderboardModel,
} from "@/lib/cockpit-event-models"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import {
  buildReplayGeneratedMatchups,
  buildReplayGeneratedSecondaryBets,
  getRawGeneratedMatchups,
  getRawGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import { resolvePastMatchupGrade } from "@/lib/matchup-pick-grade"
import { gradeSecondaryBetFromLeaderboard } from "@/lib/outright-replay-grade"
import { formatUnits } from "@/lib/format"
import { buildGradingRecordSummary, buildPastReplayRecordSummary } from "@/lib/record-summary"
import {
  GRADING_TABLE_TOOLTIPS,
  MATCHUP_TABLE_TOOLTIPS,
  POWER_RANKINGS_HELP,
  SG_TRAJECTORY_HELP,
} from "@/lib/metric-tooltips"
import {
  buildPredictionRunFromSection,
  collectAvailableBooks,
  flattenSecondaryBets,
  NON_BOOK_SOURCES,
  normalizeSportsbook,
} from "@/lib/prediction-board"
import type {
  CompositePlayer,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveLeaderboardRow,
  LiveRefreshSnapshot,
  LiveTournamentSnapshot,
  MatchupBet,
  PastSnapshotEvent,
  PlayerProfile,
  PredictionRunResponse,
  RecordSummary,
} from "@/lib/types"
import { computeSgTrajectoryBounds } from "@/lib/metric-heat"
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import {
  buildMatchupKey,
  buildPickColumns,
  buildRankingsColumns,
  buildRecentResultsColumns,
  buildSecondaryColumns,
} from "@/lib/cockpit-columns"

/* ── Small helpers ────────────────────────────── */
function PastPickGradeCell({
  matchup,
  leaderboard,
}: {
  matchup: MatchupBet
  leaderboard: LiveLeaderboardRow[] | undefined
}) {
  const g = resolvePastMatchupGrade(matchup, leaderboard)
  if (g.kind === "letter") {
    const cls = g.letter === "W" ? "win" : g.letter === "L" ? "loss" : "push"
    return (
      <span className={`pick-result-badge ${cls}`} title={g.title} aria-label={g.title}>
        {g.letter}
      </span>
    )
  }
  if (g.kind === "pending") {
    return (
      <span className="text-pending" title={g.title}>
        Pending
      </span>
    )
  }
  return (
    <span className="num num-faint" title={g.title} aria-label={g.title}>
      —
    </span>
  )
}

function PastSecondaryGradeCell({
  bet,
  leaderboard,
}: {
  bet: FlattenedSecondaryBet
  leaderboard: LiveLeaderboardRow[] | undefined
}) {
  if (!leaderboard || leaderboard.length === 0) {
    return (
      <span style={{ fontSize: 11, color: "var(--text-muted)" }} title="Waiting for final leaderboard">
        Pending
      </span>
    )
  }
  const graded = gradeSecondaryBetFromLeaderboard(bet, leaderboard)
  if (graded) {
    const letter = graded.outcome === "win" ? "W" : "L"
    const cls = graded.outcome === "win" ? "win" : "loss"
    let title = graded.outcome === "win" ? "Win" : "Loss"
    if (graded.outcome === "win" && graded.fraction > 0 && graded.fraction < 1) {
      title = `Dead heat: ${(graded.fraction * 100).toFixed(1)}% of stake wins`
    }
    return (
      <span className={`pick-result-badge ${cls}`} title={title} aria-label={title}>
        {letter}
      </span>
    )
  }
  return (
    <span
      className="num"
      style={{ color: "var(--text-faint)" }}
      title="Not graded — unsupported market (e.g. FRL) or player missing from leaderboard"
      aria-label="Not graded"
    >
      —
    </span>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-title">{message}</div>
    </div>
  )
}

const DEFAULT_COCKPIT_MIN_EDGE = 0.02

type PastReplaySource = "dashboard" | "lab"
type PastReplayLane = "completed" | "live" | "upcoming"
type PastHistoryLane = "live" | "upcoming" | "lab_live" | "lab_upcoming"

function resolvePastHistoryLane(lane: PastReplayLane, source: PastReplaySource): PastHistoryLane | null {
  if (lane === "completed") return null
  if (source === "lab") return lane === "live" ? "lab_live" : "lab_upcoming"
  return lane
}

function TopPicksPipelineHint({
  diagnostics,
  predictionTab,
  minEdge,
  selectedBooksLength,
  matchupSearchTrimmed,
}: {
  diagnostics?: LiveTournamentSnapshot["diagnostics"]
  predictionTab: PredictionTab
  minEdge: number
  selectedBooksLength: number
  matchupSearchTrimmed: string
}) {
  if (predictionTab === "past") return null
  const filterActive =
    selectedBooksLength > 0 ||
    matchupSearchTrimmed.length > 0 ||
    minEdge > DEFAULT_COCKPIT_MIN_EDGE
  const st = diagnostics?.state
  const sel = diagnostics?.selection_counts
  const reasons = diagnostics?.reason_codes
  const topReasons = Object.entries(reasons ?? {})
    .filter(([, n]) => Number(n) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 4)
  return (
    <div className="workspace-pipeline-hint">
      <div className="workspace-pipeline-title">Matchup pipeline</div>
      <div>
        State: <code>{st ?? "—"}</code>
        {sel?.input_rows != null ? (
          <>
            {" "}
            · Raw rows: <strong>{sel.input_rows}</strong>
          </>
        ) : null}
        {sel?.all_qualifying_rows != null ? (
          <>
            {" "}
            · Qualifying: <strong>{sel.all_qualifying_rows}</strong>
          </>
        ) : null}
        {sel?.selected_rows != null ? (
          <>
            {" "}
            · Card-selected: <strong>{sel.selected_rows}</strong>
          </>
        ) : null}
      </div>
      {topReasons.length > 0 ? (
        <div className="workspace-pipeline-exclusions">
          Top exclusions:{" "}
          {topReasons.map(([k, v], i) => (
            <span key={k}>
              {i > 0 ? " · " : null}
              <span title={k}>{k.replaceAll("_", " ")}</span> ({v})
            </span>
          ))}
        </div>
      ) : null}
      <div className="text-faint-11" style={{ marginTop: 6 }}>
        Top picks uses the same filters as the matchup board (books, search, min edge {(minEdge * 100).toFixed(0)}%; default{" "}
        {(DEFAULT_COCKPIT_MIN_EDGE * 100).toFixed(0)}%). Secondary markets can still show edges when matchups do not.
        {filterActive ? " Filters are active — relax them to see more qualifying rows." : null}
      </div>
    </div>
  )
}

/* ── Props ────────────────────────────────────── */
export type PredictionWorkspacePageProps = {
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
  gradingRecordSummary?: RecordSummary
  players: CompositePlayer[]
  predictionRun: PredictionRunResponse | null
  selectedPlayerKey: string
  onPlayerSelect: (playerKey: string) => void
  selectedPlayerProfile?: PlayerProfile
  playerProfileState: "loading" | "ready" | "error" | "unavailable"
  playerProfileErrorMessage?: string
  onPlayerProfileRetry: () => void
  richProfilesEnabled: boolean
  secondaryBets: FlattenedSecondaryBet[]
  /** When set, shown under power rankings count (e.g. lab model lane). */
  powerRankingsSubtitle?: string | null
  /** Keeps Dashboard Past and Lab Past market-row history separated. */
  pastReplaySource?: PastReplaySource
  /** Updates shell headline / document title while Past replay is active. */
  onPastEventContextChange?: (context: { eventName: string; courseName?: string } | null) => void
}

export function PredictionWorkspacePage({
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
  gradingRecordSummary,
  players,
  predictionRun,
  selectedPlayerKey,
  onPlayerSelect,
  selectedPlayerProfile,
  playerProfileState,
  playerProfileErrorMessage,
  onPlayerProfileRetry,
  richProfilesEnabled,
  secondaryBets,
  powerRankingsSubtitle,
  pastReplaySource = "dashboard",
  onPastEventContextChange,
}: PredictionWorkspacePageProps) {
  const isNarrow = useIsNarrowViewport()
  const [expandedMatchupKey, setExpandedMatchupKey] = useState<string | null>(null)
  const [selectedPastEventKey, setSelectedPastEventKey] = useState("")
  const [pastReplaySection, setPastReplaySection] = useState<PastReplayLane>("completed")

  const pastEventsQuery = useQuery({
    queryKey: ["live-refresh-past-events"],
    queryFn: api.getLiveRefreshPastEvents,
    staleTime: 60_000,
  })

  const durableRecordSummary = useMemo(
    () => buildGradingRecordSummary(gradingHistory, gradingRecordSummary),
    [gradingHistory, gradingRecordSummary],
  )
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
    queryKey: ["live-refresh-past-snapshot", selectedPastEvent?.event_id, pastReplaySection, pastReplaySource],
    queryFn: () =>
      api.getLiveRefreshPastSnapshot(
        selectedPastEvent?.event_id ?? "",
        resolvePastHistoryLane(pastReplaySection, pastReplaySource) ?? "completed",
        { source: pastReplaySource },
      ),
    enabled: predictionTab === "past" && Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })

  const pastReplayHistoryLane = resolvePastHistoryLane(pastReplaySection, pastReplaySource)
  const pastReplayHasHistoryLanes = pastReplayHistoryLane !== null

  const pastTimelineQuery = useQuery({
    queryKey: ["live-refresh-past-timeline", selectedPastEvent?.event_id, pastReplayHistoryLane],
    queryFn: () => {
      const lane = pastReplayHistoryLane
      if (!lane) {
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
    queryKey: ["live-refresh-past-market-rows", selectedPastEvent?.event_id, pastReplaySection, pastReplaySource],
    queryFn: () => {
      return api.getLiveRefreshPastMarketRows(selectedPastEvent?.event_id ?? "", {
        section: pastReplayHistoryLane ?? "completed",
        source: pastReplaySource,
      })
    },
    enabled:
      predictionTab === "past" &&
      Boolean(selectedPastEvent?.event_id),
    staleTime: 30_000,
  })
  const pastReplayHasError =
    pastEventsQuery.isError ||
    pastSnapshotQuery.isError ||
    pastTimelineQuery.isError ||
    pastMarketRowsQuery.isError
  const pastReplayErrorMessage = (
    pastEventsQuery.error ??
    pastSnapshotQuery.error ??
    pastTimelineQuery.error ??
    pastMarketRowsQuery.error
  ) instanceof Error
    ? (
        pastEventsQuery.error ??
        pastSnapshotQuery.error ??
        pastTimelineQuery.error ??
        pastMarketRowsQuery.error
      )?.message
    : "Replay API request failed."

  const pastSnapshotSection = pastSnapshotQuery.data?.ok
    ? (pastSnapshotQuery.data.snapshot ?? null)
    : null
  const pastLeaderboardForGrades = useMemo(
    () => (predictionTab === "past" ? (pastSnapshotSection?.leaderboard ?? []) : []),
    [pastSnapshotSection?.leaderboard, predictionTab],
  )
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
    const filtered = pastMarketRows.filter((row) => row.snapshot_id === activePastReplaySnapshotId)
    return filtered.length > 0 ? filtered : pastMarketRows
  }, [activePastReplaySnapshotId, pastMarketRows])

  const pastReplayLoading =
    predictionTab === "past" &&
    Boolean(selectedPastEvent?.event_id) &&
    (pastSnapshotQuery.isLoading ||
      pastMarketRowsQuery.isLoading ||
      pastSnapshotQuery.isFetching ||
      pastMarketRowsQuery.isFetching)

  const pastRecentResults = useMemo(() => {
    if (predictionTab !== "past") {
      return gradingHistory.slice(0, 5).map((event) => ({ kind: "graded" as const, event }))
    }
    const gradedByEventId = new Map(
      gradingHistory
        .filter((event) => Boolean(event.event_id))
        .map((event) => [String(event.event_id), event]),
    )
    return pastEventOptions.slice(0, 8).map((event) => {
      const graded = gradedByEventId.get(event.event_id)
      if (graded) return { kind: "graded" as const, event: graded }
      return {
        kind: "replay" as const,
        event: {
          event_id: event.event_id,
          name: event.event_name,
          total_profit: null,
          hits: null,
          graded_pick_count: null,
        },
      }
    })
  }, [gradingHistory, pastEventOptions, predictionTab])

  const pastMatchups = useMemo(() => {
    const sourceRows =
      pastReplayRows.length > 0
        ? buildReplayGeneratedMatchups(pastReplayRows)
        : (pastPredictionRun?.matchup_bets_all_books ?? pastPredictionRun?.matchup_bets ?? [])
    return sourceRows.filter((matchup) => {
      const passesSearch = matchupSearch
        ? `${matchup.pick} ${matchup.opponent}`.toLowerCase().includes(matchupSearch.toLowerCase())
        : true
      return passesSearch
    })
  }, [matchupSearch, pastPredictionRun, pastReplayRows])

  const pastSecondaryBets = useMemo(() => {
    const sourceRows =
      pastReplayRows.length > 0
        ? buildReplayGeneratedSecondaryBets(pastReplayRows)
        : flattenSecondaryBets(pastPredictionRun)
    return sourceRows
  }, [pastPredictionRun, pastReplayRows])

  const displayPredictionRun = predictionTab === "past" ? pastPredictionRun : predictionRun
  const displayPlayers = useMemo(
    () => (predictionTab === "past" ? (pastPredictionRun?.composite_results ?? []) : players),
    [pastPredictionRun?.composite_results, players, predictionTab],
  )
  const boardTrajectoryBounds = useMemo(
    () => computeSgTrajectoryBounds(displayPlayers),
    [displayPlayers],
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

  const recordSummary = useMemo(
    () =>
      predictionTab === "past" &&
      (rawGeneratedMatchups.length > 0 || rawGeneratedSecondaryBets.length > 0)
        ? buildPastReplayRecordSummary(
            rawGeneratedMatchups,
            rawGeneratedSecondaryBets,
            pastLeaderboardForGrades,
          )
        : durableRecordSummary,
    [
      durableRecordSummary,
      pastLeaderboardForGrades,
      predictionTab,
      rawGeneratedMatchups,
      rawGeneratedSecondaryBets,
    ],
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

  const pastReplayHasData =
    predictionTab === "past" &&
    (displayPlayers.length > 0 ||
      pastReplayRows.length > 0 ||
      (pastSnapshotSection?.leaderboard?.length ?? 0) > 0)

  useEffect(() => {
    if (!onPastEventContextChange) return
    if (predictionTab !== "past") {
      onPastEventContextChange(null)
      return
    }
    onPastEventContextChange({
      eventName: selectedPastEvent?.event_name ?? "Past event",
      courseName: courseName || undefined,
    })
  }, [
    courseName,
    onPastEventContextChange,
    predictionTab,
    selectedPastEvent?.event_name,
  ])

  const diagnosticsMessage =
    predictionTab === "past"
      ? "Select a past event from the replay selector to load market data."
      : getMatchupStateMessage({
          state: activeSection?.diagnostics?.state,
          reasonCodes: activeSection?.diagnostics?.reason_codes,
          hasFilters: selectedBooks.length > 0,
        })

  const topPlays = predictionTab === "past" ? pastMatchups : filteredMatchups

  const topPicksEmptyMessage = useMemo(() => {
    if (predictionTab === "past") {
      if (rawGeneratedMatchups.length > 0 && topPlays.length === 0 && matchupSearch.trim()) {
        return `${rawGeneratedMatchups.length} recovered matchup line(s) are available; none match your search.`
      }
      return diagnosticsMessage
    }
    const rawLen = rawGeneratedMatchups.length
    if (rawLen > 0 && topPlays.length === 0) {
      return `${diagnosticsMessage} ${rawLen} matchup line(s) from the model did not pass your filters or min edge — try more books or a lower edge threshold.`
    }
    return diagnosticsMessage
  }, [diagnosticsMessage, matchupSearch, predictionTab, rawGeneratedMatchups.length, topPlays.length])

  const isPastTab = predictionTab === "past"

  const rankingsColumns = useMemo(
    () => buildRankingsColumns({ onPlayerSelect, trajectoryBounds: boardTrajectoryBounds }),
    [onPlayerSelect, boardTrajectoryBounds],
  )

  const pickColumns = useMemo(
    () =>
      buildPickColumns({
        isPast: isPastTab,
        renderResult: isPastTab
          ? (matchup) => (
              <span data-testid={`matchup-grade-${buildMatchupKey(matchup)}`}>
                <PastPickGradeCell matchup={matchup} leaderboard={pastLeaderboardForGrades} />
              </span>
            )
          : undefined,
      }),
    [isPastTab, pastLeaderboardForGrades],
  )

  const secondaryColumns = useMemo(
    () =>
      buildSecondaryColumns({
        isPast: isPastTab,
        onPlayerSelect,
        renderResult: isPastTab
          ? (bet) => (
              <span data-testid={`secondary-grade-${bet.market}-${bet.player}`}>
                <PastSecondaryGradeCell bet={bet} leaderboard={pastLeaderboardForGrades} />
              </span>
            )
          : undefined,
      }),
    [isPastTab, onPlayerSelect, pastLeaderboardForGrades],
  )

  const recentResultsColumns = useMemo(() => buildRecentResultsColumns(), [])

  // Team-format events (Zurich Classic) intentionally short-circuit the
  // pipeline in the backend (see src/event_format.py). Mirror the skip on
  // the frontend by replacing the bettable-card modules with an explanatory
  // notice — never show an empty placement / matchup board that implies the
  // model ran but found nothing.
  const showTeamEventNotice =
    (predictionTab === "live" || predictionTab === "upcoming") && isTeamEvent(activeSection)

  // Dashboard workspace modules (using exact API signatures from cockpit-event-models.ts)
  const mode = predictionTab as "live" | "upcoming" | "past"

  const leaderboardModel = buildLeaderboardModel({
    mode,
    leaderboardRows: activeSection?.leaderboard ?? pastSnapshotSection?.leaderboard ?? [],
    players: displayPlayers,
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

  const leftRailMobile = (
          <CockpitVerticalSections
            autoSaveId="golf-model-cockpit-left-rail"
            defaultActiveId="context"
            stackClassName={isNarrow ? "cockpit-left-rail-panels--stacked" : undefined}
            sections={[
              {
                id: "context",
                label: "Context",
                content: (
                  <>
            {/* Past event selector */}
            {predictionTab === "past" && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Replay selector</div>
                </div>
                <div className="card-body card-body-stack-8">
                  {pastEventOptions.length === 0 && (
                    <div
                      role="status"
                      data-testid="past-events-empty"
                      className="workspace-status-banner"
                    >
                      No past events to replay: snapshot history is empty and no graded tournaments with a
                      DataGolf <code>event_id</code> were found (legacy rows may
                      still resolve from round data after deploy). Ensure the live-refresh worker has run
                      for completed events and grading has stored picks linked to the tournament.
                    </div>
                  )}
                  <div>
                    <div className="field-label field-label--tight">Event</div>
                    <select
                      value={selectedPastEventKey || selectedPastEvent?.event_id || ""}
                      onChange={(e) => setSelectedPastEventKey(e.target.value)}
                      aria-label="Select past event for replay"
                      disabled={pastEventOptions.length === 0}
                      className="workspace-select"
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
                    <div className="field-label field-label--tight">Lane</div>
                    <div className="workspace-lane-row">
                      {(["completed", "live", "upcoming"] as const).map((lane) => (
                        <button
                          key={lane}
                          type="button"
                          onClick={() => setPastReplaySection(lane)}
                          aria-pressed={pastReplaySection === lane}
                          className="workspace-lane-btn"
                        >
                          {lane}
                        </button>
                      ))}
                    </div>
                  </div>
                  {pastReplayHasError && (
                    <div role="alert" className="workspace-alert-error">
                      <div>Replay request failed: {pastReplayErrorMessage}</div>
                      <div className="flex-wrap-gap-6">
                        <button
                          type="button"
                          className="btn btn-ghost btn-compact"
                          onClick={() => {
                            void pastEventsQuery.refetch()
                            void pastSnapshotQuery.refetch()
                            if (pastReplayHasHistoryLanes) {
                              void pastTimelineQuery.refetch()
                            }
                            void pastMarketRowsQuery.refetch()
                          }}
                        >
                          Retry replay fetch
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Course + weather — collapsed by default on desktop to keep filters dominant */}
            <CollapsibleSection
              title="Course & weather"
              description="Secondary context"
              defaultOpen={isNarrow}
              testId="intel-course-weather"
            >
              <CourseWeatherFeedPanel
                metrics={courseFeedModel.metrics}
                feedItems={courseFeedModel.feedItems}
              />
            </CollapsibleSection>
                  </>
                ),
              },
              {
                id: "filters",
                label: "Filters",
                content: (
                  <FilterSheet title="Board filters" description="Books, player search, min edge">
            <div className="card">
              <div className="card-header">
                <div className="card-title">Filters</div>
                {selectedBooks.length > 0 && (
                  <button
                    className="btn btn-ghost btn-compact-md"
                    onClick={() => onSelectedBooksChange([])}
                  >
                    Clear
                  </button>
                )}
              </div>
              <div className="card-body card-body-stack-10">
                {/* Book chips */}
                {displayAvailableBooks.length > 0 && (
                  <div>
                    <div className="field-label">Sportsbook</div>
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
                  <div className="field-label">Search player</div>
                  <div className="search-input">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="search-icon">
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
                  <div className="field-label">
                    Min edge: <span className="text-muted-11">{(minEdge * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="0.2"
                    step="0.01"
                    value={minEdge}
                    onChange={(e) => onMinEdgeChange(Number(e.target.value))}
                    className="workspace-range"
                    aria-label="Minimum edge threshold"
                    data-testid="min-edge-slider"
                  />
                </div>
              </div>
            </div>
                  </FilterSheet>
                ),
              },
              {
                id: "results",
                label: "Results",
                content: (
                  <>
            <CollapsibleSection
              title={predictionTab === "past" ? "Past events" : "Recent results"}
              description={predictionTab === "past" ? "Replay history" : "Graded events"}
              defaultOpen={isNarrow || predictionTab === "past"}
              testId="intel-recent-results"
            >
              <div className="flex-end-row">
                <Link to="/grading" className="link-accent-11">
                  All grading →
                </Link>
              </div>
              <div className="table-scroll">
                {pastRecentResults.length > 0 ? (
                  <ProDataGrid
                    data={pastRecentResults}
                    columns={recentResultsColumns as ColumnDef<(typeof pastRecentResults)[number], unknown>[]}
                    density="compact"
                    virtualizeAfter={999}
                    getRowId={(row) => `${row.event.event_id}-${row.event.name}`}
                  />
                ) : (
                  <div className="card-body-pad">
                    <EmptyState
                      message={
                        predictionTab === "past"
                          ? "No past events available yet. Run live-refresh through a completed tournament week first."
                          : "No graded events yet."
                      }
                    />
                  </div>
                )}
              </div>
            </CollapsibleSection>
                  </>
                ),
              },
            ]}
          />
  )

  const rightRailMobile = (
          <>
            {/* ── Player spotlight ─────────────────── */}
            <CockpitModule
              flex={3}
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
                profileState={playerProfileState}
                profileErrorMessage={playerProfileErrorMessage}
                onRetryProfile={onPlayerProfileRetry}
                richProfilesEnabled={richProfilesEnabled}
              />
            </CockpitModule>
          </>
  )

  const renderCenterBoard = (
    compactView?: "picks" | "rankings" | "secondary" | "leaderboard",
  ) => (
                <CockpitResizableStack
                  layout={compactView != null ? "stack" : isNarrow ? "stack" : "panels"}
                  compactView={compactView}
                  showLeaderboard={predictionTab !== "upcoming"}
                  rankings={
            <div className="card cockpit-stack-card">
              <div className="card-header">
                <div>
                  <div className="card-title">
                    {predictionTab === "past" ? "Pre-tee-off rankings" : "Power rankings"}
                  </div>
                  <div className="card-desc">
                    {predictionTab === "past"
                      ? `${displayPlayers.length} players — last rankings before tee off`
                      : `${displayPlayers.length} players ranked by model`}
                    {powerRankingsSubtitle ? (
                      <span className="card-desc-accent">{powerRankingsSubtitle}</span>
                    ) : null}
                  </div>
                </div>
                <Link to="/players" className="card-header-link">
                  All <ExternalLink size={11} />
                </Link>
              </div>
              <div className="table-scroll">
                {displayPlayers.length > 0 ? (
                  <ProDataGrid
                    data={displayPlayers}
                    columns={rankingsColumns}
                    density="compact"
                    virtualizeAfter={80}
                    getRowId={(player) => player.player_key}
                    getRowTestId={(player) => `player-row-${player.player_key}`}
                    onRowClick={(player) => onPlayerSelect(player.player_key)}
                    testId="cockpit-rankings-grid"
                  />
                ) : (
                  <div className="card-body">
                    <EmptyState message="No rankings available for this event context." />
                  </div>
                )}
              </div>
            </div>
                  }
                  topPicks={
            <div className="card cockpit-stack-card cockpit-stack-card--picks">
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
                {!displayPredictionRun?.card_content ? (
                  <p id="cockpit-export-disabled-help" className="export-help-text">
                    Export stays off until the run includes generated card content for this event.
                  </p>
                ) : null}
                <button
                  className="btn btn-ghost btn-export"
                  onClick={handleExportMarkdown}
                  disabled={!displayPredictionRun?.card_content}
                  data-testid="btn-export"
                  aria-describedby={
                    !displayPredictionRun?.card_content ? "cockpit-export-disabled-help" : undefined
                  }
                >
                  <Download size={12} />
                  Export
                </button>
              </div>

              <TopPicksPipelineHint
                diagnostics={activeSection?.diagnostics}
                predictionTab={predictionTab}
                minEdge={minEdge}
                selectedBooksLength={selectedBooks.length}
                matchupSearchTrimmed={matchupSearch.trim()}
              />

              <div className="table-scroll">
                {predictionTab === "live" && !isLiveActive ? (
                  <div className="card-body">
                    <div className="empty-state">
                      <Radar size={28} className="empty-state-icon" />
                      <div className="empty-state-title">No live event</div>
                      <div className="empty-state-desc">
                        Switch to{" "}
                        <button
                          type="button"
                          className="text-link-btn"
                          onClick={() => onPredictionTabChange("upcoming")}
                        >
                          Upcoming
                        </button>{" "}
                        for pre-tournament picks.
                      </div>
                    </div>
                  </div>
                ) : topPlays.length > 0 ? (
                  <ProDataGrid
                    data={topPlays}
                    columns={pickColumns}
                    density="compact"
                    virtualizeAfter={80}
                    getRowId={(matchup) => buildMatchupKey(matchup)}
                    getRowTestId={(matchup) => `matchup-row-${buildMatchupKey(matchup)}`}
                    expandedRowId={expandedMatchupKey}
                    onRowClick={(matchup) => {
                      const key = buildMatchupKey(matchup)
                      setExpandedMatchupKey(expandedMatchupKey === key ? null : key)
                    }}
                    renderSubRow={(matchup) => <MatchupExpandDetail matchup={matchup} />}
                    testId="cockpit-picks-grid"
                  />
                ) : (
                  <div className="card-body">
                    <EmptyState message={topPicksEmptyMessage} />
                  </div>
                )}
              </div>
            </div>
                  }
                  secondary={
              <div className="card cockpit-stack-card">
                <div className="card-header">
                  <div className="card-title">Secondary markets</div>
                  <div className="card-desc">
                    {displaySecondaryBets.length} picks
                    <Link
                      to="/matchups?tab=secondary"
                      style={{ marginLeft: 8, color: "var(--accent-link)", fontSize: 10, textDecoration: "none" }}
                    >
                      All →
                    </Link>
                  </div>
                </div>
                <div className="table-scroll">
                  {displaySecondaryBets.length > 0 ? (
                    <ProDataGrid
                      data={displaySecondaryBets}
                      columns={secondaryColumns}
                      density="compact"
                      virtualizeAfter={80}
                      getRowId={(bet) => `${bet.market}-${bet.player}-${bet.odds}`}
                      getRowTestId={(bet) => `secondary-row-${bet.player}`}
                      onRowClick={(bet) => bet.player_key && onPlayerSelect(bet.player_key)}
                      testId="cockpit-secondary-grid"
                    />
                  ) : (
                    <div className="card-body">
                      <EmptyState message="No secondary market edges in this context." />
                    </div>
                  )}
                </div>
              </div>
                  }
                  leaderboard={
              predictionTab !== "upcoming" ? (
              <CockpitModule
                className="cockpit-stack-card"
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
              ) : undefined
                  }
                />
  )

  return (
    <div
      className={
        isNarrow
          ? "prediction-workspace prediction-workspace--narrow prediction-workspace-root"
          : "prediction-workspace prediction-workspace-root"
      }
    >
      {/* ── Notice bar ──────────────────────────── */}
      {snapshotNotice && (
        <div className="alert-banner" role="status" aria-live="polite">
          <Radar size={11} style={{ flexShrink: 0 }} />
          {snapshotNotice}
        </div>
      )}

      {predictionTab === "past" && pastReplayLoading && !pastReplayHasData && (
        <div className="alert-banner" role="status" aria-live="polite" data-testid="past-replay-loading">
          Loading past tournament replay for {selectedPastEvent?.event_name ?? "selected event"}…
        </div>
      )}

      {predictionTab === "past" && pastReplayHasError && !pastReplayLoading && !pastReplayHasData && (
        <div className="alert-banner" role="alert" data-testid="past-replay-error">
          Past replay failed: {pastReplayErrorMessage}. Try another event or use the Completed lane.
        </div>
      )}

      {/* ── KPI strip — Bloomberg hero numbers, fixed height ── */}
      <div className={isNarrow ? "kpi-strip kpi-strip--compact" : "kpi-strip"}>
        <div className="kpi-cell kpi-cell--event">
          <div className="kpi-cell-label">Event</div>
          <div className="kpi-cell-value muted">{eventName}</div>
          {courseName && !isNarrow ? <div className="kpi-cell-sub">{courseName}</div> : null}
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Field</div>
          <div className="kpi-cell-value muted">{fieldSize ?? "—"}</div>
          <div className="kpi-cell-sub">players</div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Combined</div>
          <div className={`kpi-cell-value ${recordSummary.combined.profit >= 0 ? "green" : "red"}`}>
            {formatUnits(recordSummary.combined.profit)}
          </div>
          <div className="kpi-cell-sub">
            {recordSummary.combined.recordLabel} · {recordSummary.combined.hitRateLabel}
          </div>
        </div>
        <div className="kpi-cell">
          <div className="kpi-cell-label">Matchups</div>
          <div className={`kpi-cell-value ${recordSummary.matchups.profit >= 0 ? "green" : "red"}`}>
            {formatUnits(recordSummary.matchups.profit)}
          </div>
          <div className="kpi-cell-sub">
            {recordSummary.matchups.recordLabel} · {recordSummary.matchups.hitRateLabel}
          </div>
        </div>
        <div className="kpi-cell kpi-cell--outrights">
          <div className="kpi-cell-label">Outrights</div>
          <div className={`kpi-cell-value ${recordSummary.outrights.profit >= 0 ? "green" : "red"}`}>
            {formatUnits(recordSummary.outrights.profit)}
          </div>
          <div className="kpi-cell-sub">
            {recordSummary.outrights.recordLabel} · {recordSummary.outrights.hitRateLabel}
          </div>
        </div>
      </div>

      {isNarrow ? (
        <div className="workspace-filter-summary-row">
          <span className="filter-summary-chip" data-testid="filter-summary-chip">
            {selectedBooks.length > 0 ? `${selectedBooks.length} book${selectedBooks.length === 1 ? "" : "s"}` : "All books"}
            {" · "}
            {(minEdge * 100).toFixed(0)}% min edge
            {matchupSearch.trim() ? ` · “${matchupSearch.trim()}”` : ""}
          </span>
        </div>
      ) : null}

      <CockpitWorkspace
        className="cockpit-fill"
        layout={isNarrow ? "stack" : "columns"}
        mobilePanels={
          isNarrow
            ? [
                {
                  id: "picks",
                  label: "Picks",
                  badge: topPlays.length,
                  content: (
                    <>
                      <Link to="/matchups" className="cockpit-mobile-cta">
                        Full picks page →
                      </Link>
                      {renderCenterBoard("picks")}
                    </>
                  ),
                },
                {
                  id: "rankings",
                  label: "Rankings",
                  content: renderCenterBoard("rankings"),
                },
                {
                  id: "markets",
                  label: "Markets",
                  badge: displaySecondaryBets.length || undefined,
                  content: renderCenterBoard("secondary"),
                },
                ...(predictionTab !== "upcoming"
                  ? [
                      {
                        id: "board",
                        label: "Board",
                        content: renderCenterBoard("leaderboard"),
                      },
                    ]
                  : []),
                {
                  id: "intel",
                  label: "Intel",
                  content: leftRailMobile,
                },
                {
                  id: "player",
                  label: "Player",
                  content: rightRailMobile,
                },
              ]
            : undefined
        }
        leftRail={isNarrow ? null : leftRailMobile}
        center={
          isNarrow ? (
            showTeamEventNotice ? (
              <div className="workspace-scroll-pane">
                <TeamEventNotice
                  eventName={eventName}
                  courseName={courseName}
                  mode={predictionTab === "live" ? "live" : "upcoming"}
                />
              </div>
            ) : null
          ) : (
            <>
              {showTeamEventNotice && (
                <div className="workspace-scroll-pane">
                  <TeamEventNotice
                    eventName={eventName}
                    courseName={courseName}
                    mode={predictionTab === "live" ? "live" : "upcoming"}
                  />
                </div>
              )}
              {!showTeamEventNotice && (
                <div className="cockpit-center-stack">
                  {renderCenterBoard()}
                </div>
              )}
            </>
          )
        }
        rightRail={isNarrow ? null : rightRailMobile}
      />
    </div>
  )
}
