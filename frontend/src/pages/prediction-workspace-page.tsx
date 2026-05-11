import { Fragment, useMemo, useState } from "react"
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, Download, ExternalLink, Radar } from "lucide-react"
import { Link } from "react-router-dom"

import {
  CourseWeatherFeedPanel,
  LeaderboardPanel,
} from "@/components/cockpit/event-modules"
import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import { TeamEventNotice } from "@/components/cockpit/team-event-notice"
import { isTeamEvent } from "@/lib/event-format"
import { CockpitResizableStack } from "@/components/cockpit/cockpit-resizable-stack"
import { CockpitModule, CockpitWorkspace } from "@/components/cockpit/workspace"
import { useCockpitSpotlight } from "@/hooks/use-cockpit-spotlight"
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
import { formatNumber, formatUnits } from "@/lib/format"
import { buildGradingRecordSummary, buildPastReplayRecordSummary } from "@/lib/record-summary"
import {
  EV_BADGE_TOOLTIP,
  GRADING_TABLE_TOOLTIPS,
  MATCHUP_DETAIL_TOOLTIPS,
  MATCHUP_TABLE_TOOLTIPS,
  POWER_RANKINGS_HELP,
  SG_TRAJECTORY_HELP,
  TIER_BADGE_TOOLTIP,
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
import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import { computeSgTrajectoryBounds, heatSpectrumGradientAlongUnit } from "@/lib/metric-heat"
import { buildMatchupKey, secondaryBadgeLabel } from "@/pages/page-shared"

/* ── Small helpers ────────────────────────────── */
function EV({ ev, evPct }: { ev: number; evPct?: string }) {
  const cls = ev >= 0.08 ? "high" : ev >= 0.04 ? "medium" : "low"
  return (
    <span className={`ev-badge ${cls}`} title={EV_BADGE_TOOLTIP} style={{ cursor: "help" }}>
      {evPct ?? `${(ev * 100).toFixed(1)}%`}
    </span>
  )
}

function TierBadge({ tier }: { tier?: string }) {
  const t = tier ?? "LEAN"
  return (
    <span className={`tier-badge ${t}`} title={TIER_BADGE_TOOLTIP} style={{ cursor: "help" }}>
      {t}
    </span>
  )
}

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
      <span style={{ fontSize: 11, color: "var(--text-muted)" }} title={g.title}>
        Pending
      </span>
    )
  }
  return (
    <span className="num" style={{ color: "var(--text-faint)" }} title={g.title} aria-label={g.title}>
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
    <div
      style={{
        padding: "8px 12px 10px",
        fontSize: 11,
        color: "var(--text-muted)",
        lineHeight: 1.45,
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div
        style={{
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          fontSize: 9,
          marginBottom: 4,
          color: "var(--text-faint)",
        }}
      >
        Matchup pipeline
      </div>
      <div>
        State: <code style={{ color: "var(--text)" }}>{st ?? "—"}</code>
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
        <div style={{ marginTop: 4 }}>
          Top exclusions:{" "}
          {topReasons.map(([k, v], i) => (
            <span key={k}>
              {i > 0 ? " · " : null}
              <span title={k}>{k.replaceAll("_", " ")}</span> ({v})
            </span>
          ))}
        </div>
      ) : null}
      <div style={{ marginTop: 6, fontSize: 10, color: "var(--text-faint)" }}>
        Top picks uses the same filters as the matchup board (books, search, min edge {(minEdge * 100).toFixed(0)}%; default{" "}
        {(DEFAULT_COCKPIT_MIN_EDGE * 100).toFixed(0)}%). Secondary markets can still show edges when matchups do not.
        {filterActive ? " Filters are active — relax them to see more qualifying rows." : null}
      </div>
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
  const heatFill =
    color === "green" && max > 0 && Number.isFinite(value)
      ? heatSpectrumGradientAlongUnit(Math.min(1, Math.max(0, value / max)), "ltr")
      : undefined
  return (
    <div className="score-bar-wrap">
      <div className="score-bar-track">
        <div
          className={heatFill ? "score-bar-fill" : `score-bar-fill ${color}`}
          style={heatFill ? { width: `${pct}%`, background: heatFill } : { width: `${pct}%` }}
        />
      </div>
      <span className="score-bar-val">{formatNumber(value, 1)}</span>
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
}: PredictionWorkspacePageProps) {
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
        limit: 10000,
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
    return pastMarketRows.filter((row) => row.snapshot_id === activePastReplaySnapshotId)
  }, [activePastReplaySnapshotId, pastMarketRows])

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

  const diagnosticsMessage =
    predictionTab === "past"
      ? "Select a past event from the replay selector to load market data."
      : getMatchupStateMessage({
          state: activeSection?.diagnostics?.state,
          reasonCodes: activeSection?.diagnostics?.reason_codes,
          hasFilters: selectedBooks.length > 0,
        })

  const topPlays = predictionTab === "past" ? pastMatchups : filteredMatchups
  const matchupTableColumnCount = predictionTab === "past" ? 7 : 6

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

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      {/* ── Notice bar ──────────────────────────── */}
      {snapshotNotice && (
        <div className="alert-banner" role="status" aria-live="polite">
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
        <div className="kpi-cell">
          <div className="kpi-cell-label">Outrights</div>
          <div className={`kpi-cell-value ${recordSummary.outrights.profit >= 0 ? "green" : "red"}`}>
            {formatUnits(recordSummary.outrights.profit)}
          </div>
          <div className="kpi-cell-sub">
            {recordSummary.outrights.recordLabel} · {recordSummary.outrights.hitRateLabel}
          </div>
        </div>
      </div>

      {/* ── Three-column dashboard workspace ─────────────────── */}
      <CockpitWorkspace
        className="cockpit-fill"
        leftRail={
          <PanelGroup
            direction="vertical"
            autoSaveId="golf-model-cockpit-left-rail"
            className="cockpit-vertical-panels cockpit-left-rail-panels"
          >
            <Panel defaultSize={42} minSize={14} className="cockpit-panel-shell">
              <div className="cockpit-panel-fill cockpit-left-rail-section" style={{ gap: 4 }}>
            {/* Past event selector */}
            {predictionTab === "past" && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">Replay selector</div>
                </div>
                <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {pastEventOptions.length === 0 && (
                    <div
                      role="status"
                      data-testid="past-events-empty"
                      style={{
                        fontSize: 11,
                        lineHeight: 1.45,
                        color: "var(--text-muted)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--r-sm)",
                        padding: "8px 10px",
                        background: "var(--surface-2)",
                      }}
                    >
                      No past events to replay: snapshot history is empty and no graded tournaments with a
                      DataGolf <code style={{ fontSize: 10 }}>event_id</code> were found (legacy rows may
                      still resolve from round data after deploy). Ensure the live-refresh worker has run
                      for completed events and grading has stored picks linked to the tournament.
                    </div>
                  )}
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--text-faint)", marginBottom: 4 }}>
                      Event
                    </div>
                    <select
                      value={selectedPastEventKey || selectedPastEvent?.event_id || ""}
                      onChange={(e) => setSelectedPastEventKey(e.target.value)}
                      aria-label="Select past event for replay"
                      disabled={pastEventOptions.length === 0}
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
                          type="button"
                          onClick={() => setPastReplaySection(lane)}
                          aria-pressed={pastReplaySection === lane}
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
                  {pastReplayHasError && (
                    <div
                      role="alert"
                      style={{
                        border: "1px solid rgba(239,68,68,0.25)",
                        background: "var(--red-bg)",
                        color: "var(--red)",
                        borderRadius: "var(--r-sm)",
                        padding: "8px 10px",
                        fontSize: 11,
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                      }}
                    >
                      <div>Replay request failed: {pastReplayErrorMessage}</div>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: "3px 8px", fontSize: 10 }}
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

            {/* Course + weather context */}
            <CockpitModule title="Course & weather" description="Feed for the active event context.">
              <CourseWeatherFeedPanel
                metrics={courseFeedModel.metrics}
                feedItems={courseFeedModel.feedItems}
              />
            </CockpitModule>
              </div>
            </Panel>
            <PanelResizeHandle
              className="cockpit-resize-handle cockpit-resize-handle-row"
              aria-label="Resize course area and book filters"
            />
            <Panel defaultSize={38} minSize={16} className="cockpit-panel-shell">
              <div className="cockpit-panel-fill cockpit-left-rail-section" style={{ gap: 4 }}>
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
              </div>
            </Panel>
            <PanelResizeHandle
              className="cockpit-resize-handle cockpit-resize-handle-row"
              aria-label="Resize filters and recent results"
            />
            <Panel defaultSize={20} minSize={12} className="cockpit-panel-shell">
              <div className="cockpit-panel-fill cockpit-left-rail-section" style={{ gap: 4 }}>
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
              <div className="table-scroll">
                {gradingHistory.length > 0 ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th title={GRADING_TABLE_TOOLTIPS.event}>Event</th>
                        <th className="right" title={GRADING_TABLE_TOOLTIPS.pl}>
                          P&L
                        </th>
                        <th className="right" title={GRADING_TABLE_TOOLTIPS.hitPct}>
                          Hit%
                        </th>
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
              </div>
            </Panel>
          </PanelGroup>
        }
        center={
          <>
            {showTeamEventNotice && (
              <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
                <TeamEventNotice
                  eventName={eventName}
                  courseName={courseName}
                  mode={predictionTab === "live" ? "live" : "upcoming"}
                />
              </div>
            )}
            {!showTeamEventNotice && (
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  display: "flex",
                  flexDirection: "column",
                  overflow: "hidden",
                }}
              >
                <CockpitResizableStack
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
                      <span style={{ display: "block", marginTop: 4, color: "var(--accent)" }}>{powerRankingsSubtitle}</span>
                    ) : null}
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
              <div className="table-scroll">
                {displayPlayers.length > 0 ? (
                  <table className="data-table rankings-table">
                    <thead>
                      <tr>
                        <th style={{ width: 36 }} title={POWER_RANKINGS_HELP.rank}>
                          #
                        </th>
                        <th title={POWER_RANKINGS_HELP.player}>Player</th>
                        <th title={POWER_RANKINGS_HELP.composite}>Composite</th>
                        <th title={POWER_RANKINGS_HELP.form}>Form</th>
                        <th title={POWER_RANKINGS_HELP.course}>Course</th>
                        <th className="center" title={SG_TRAJECTORY_HELP}>
                          SG traj
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayPlayers.map((player) => {
                        return (
                          <tr
                            key={player.player_key}
                            onClick={() => onPlayerSelect(player.player_key)}
                            data-testid={`player-row-${player.player_key}`}
                          >
                            <td className="rank-cell">{player.rank}</td>
                            <td className="player-name rankings-player-name">
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  onPlayerSelect(player.player_key)
                                }}
                              >
                                {player.player_display}
                              </button>
                            </td>
                            <td title={POWER_RANKINGS_HELP.composite}>
                              <ScoreBar value={player.composite} max={100} color="cyan" />
                            </td>
                            <td title={POWER_RANKINGS_HELP.form}>
                              <ScoreBar value={player.form} max={100} color="green" />
                            </td>
                            <td title={POWER_RANKINGS_HELP.course}>
                              <ScoreBar value={player.course_fit} max={100} color="gold" />
                            </td>
                            <td className="center">
                              <SgTrajectoryMeter
                                momentumTrend={player.momentum_trend}
                                momentumDirection={player.momentum_direction}
                                normMin={boardTrajectoryBounds.min}
                                normMax={boardTrajectoryBounds.max}
                              />
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
                  }
                  topPicks={
            <div className="card cockpit-stack-card">
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
                        <th title={MATCHUP_TABLE_TOOLTIPS.pick}>Pick</th>
                        <th title={MATCHUP_TABLE_TOOLTIPS.bookOdds}>Book · Odds</th>
                        <th className="center" title={MATCHUP_TABLE_TOOLTIPS.tier}>
                          Tier
                        </th>
                        {predictionTab === "past" ? (
                          <th className="center" title={MATCHUP_TABLE_TOOLTIPS.result}>
                            Res.
                          </th>
                        ) : null}
                        <th className="right" title={MATCHUP_TABLE_TOOLTIPS.ev}>
                          EV
                        </th>
                        <th className="right" title={MATCHUP_TABLE_TOOLTIPS.winPct}>
                          Win%
                        </th>
                        <th style={{ width: 32 }} />
                      </tr>
                    </thead>
                    <tbody>
                      {topPlays.map((matchup) => {
                        const key = buildMatchupKey(matchup)
                        const isExpanded = expandedMatchupKey === key
                        return (
                          <Fragment key={key}>
                            <tr
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
                              {predictionTab === "past" ? (
                                <td className="center" data-testid={`matchup-grade-${key}`}>
                                  <PastPickGradeCell matchup={matchup} leaderboard={pastLeaderboardForGrades} />
                                </td>
                              ) : null}
                              <td className="right">
                                <EV ev={matchup.ev} evPct={matchup.ev_pct} />
                              </td>
                              <td className="right num" title={MATCHUP_TABLE_TOOLTIPS.winPct} style={{ color: "var(--text-muted)", fontSize: 12, cursor: "help" }}>
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
                              <tr>
                                <td colSpan={matchupTableColumnCount} style={{ padding: 0 }}>
                                  <div className="matchup-detail">
                                    <div className="matchup-detail-grid">
                                      <div>
                                        <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.compositeGap}>
                                          Composite gap
                                        </div>
                                        <div className="detail-item-value num">{formatNumber(matchup.composite_gap, 2)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.formGap}>
                                          Form gap
                                        </div>
                                        <div className="detail-item-value num">{formatNumber(matchup.form_gap, 2)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.courseGap}>
                                          Course gap
                                        </div>
                                        <div className="detail-item-value num">{formatNumber(matchup.course_fit_gap, 2)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.impliedProb}>
                                          Implied prob
                                        </div>
                                        <div className="detail-item-value num">{(matchup.implied_prob * 100).toFixed(1)}%</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.conviction}>
                                          Conviction
                                        </div>
                                        <div className="detail-item-value num">{formatNumber(matchup.conviction, 0)}</div>
                                      </div>
                                      <div>
                                        <div className="detail-item-label" title={MATCHUP_DETAIL_TOOLTIPS.momentum}>
                                          Momentum
                                        </div>
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
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
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
                      style={{ marginLeft: 8, color: "var(--cyan)", fontSize: 10, textDecoration: "none" }}
                    >
                      All →
                    </Link>
                  </div>
                </div>
                <div className="table-scroll">
                  {displaySecondaryBets.length > 0 ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th title={MATCHUP_TABLE_TOOLTIPS.player}>Player</th>
                        <th title={MATCHUP_TABLE_TOOLTIPS.market}>Market</th>
                        <th title={MATCHUP_TABLE_TOOLTIPS.bookOdds}>Book · Odds</th>
                        <th className="right" title={MATCHUP_TABLE_TOOLTIPS.ev}>
                          EV
                        </th>
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
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  if (bet.player_key) onPlayerSelect(bet.player_key)
                                }}
                              >
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
              </div>
            )}
          </>
        }
        rightRail={
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
        }
      />
    </div>
  )
}
