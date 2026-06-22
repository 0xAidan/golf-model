import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"

import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import { TeamEventNotice } from "@/components/cockpit/team-event-notice"
import {
  DiagnosticsFunnel,
  EventCommandHeader,
  ModelCommandLayout,
  ModelCommandSection,
  ModelFilterToolbar,
  PlayerInsightDrawer,
  ResultsPreview,
  TrustStatusBanner,
} from "@/components/product"
import { buildLaneTrustState } from "@/features/model-workspace/use-lane-trust"
import {
  buildCourseFeedModel,
  buildLeaderboardModel,
} from "@/lib/cockpit-event-models"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import { isTeamEvent } from "@/lib/event-format"
import { formatUnits } from "@/lib/format"
import {
  getRawGeneratedMatchups,
  getRawGeneratedSecondaryBets,
} from "@/lib/cockpit-picks"
import {
  buildLiveRankingsColumns,
  buildUpcomingRankingsColumns,
} from "@/lib/cockpit-columns"
import { computeSgTrajectoryBounds } from "@/lib/metric-heat"
import { useCockpitSpotlight } from "@/hooks/use-cockpit-spotlight"
import { useIsNarrowViewport } from "@/hooks/use-media-query"

import {
  resolveActiveSection,
  resolveDisplayPredictionRun,
  useWorkspacePastReplay,
} from "./use-workspace-past-replay"
import { WorkspaceAlerts } from "./workspace-alerts"
import {
  WorkspaceCenterBoard,
  WorkspaceLeaderboardModule,
  buildPickColumnsForWorkspace,
  buildSecondaryColumnsForWorkspace,
} from "./workspace-center-board"
import { WorkspaceFullPicksPanel } from "./workspace-full-picks-panel"
import { WorkspaceLeftRail } from "./workspace-left-rail"
import { HIGH_EV_FLOOR, LIVE_OPPORTUNITY_PIN_MS } from "./workspace-constants"
import { TopPicksPipelineHint } from "./workspace-pipeline-hint"
import type { PredictionWorkspacePageProps } from "./workspace-types"

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
  usingProdSnapshotFallback = false,
  labLanePartialSections = false,
  fullPicks,
}: PredictionWorkspacePageProps) {
  const isNarrow = useIsNarrowViewport()
  const [searchParams] = useSearchParams()
  const urlBoardTab = searchParams.get("tab") === "full-picks" ? "full-picks" : undefined
  const [expandedMatchupKey, setExpandedMatchupKey] = useState<string | null>(null)
  const [opportunityFilter, setOpportunityFilter] = useState<"all" | "new" | "high">("all")
  const [dismissedOpportunityGeneratedAt, setDismissedOpportunityGeneratedAt] = useState<string | null>(null)

  const liveTournament = liveSnapshot?.live_tournament
  const upcomingTournament = liveSnapshot?.upcoming_tournament
  const isLiveActive = Boolean(liveTournament?.active)

  const pastReplay = useWorkspacePastReplay({
    predictionTab,
    gradingHistory,
    gradingRecordSummary,
    matchupSearch,
    availableBooks,
    pastReplaySource,
    onPastEventContextChange,
    upcomingSourceEventId: upcomingTournament?.source_event_id,
  })

  const displayPredictionRun = resolveDisplayPredictionRun(
    predictionTab,
    predictionRun,
    pastReplay.pastPredictionRun,
  )

  const displayPlayers = useMemo(
    () => {
      if (predictionTab === "past") {
        return pastReplay.pastPredictionRun?.composite_results ?? []
      }
      if (predictionTab === "live" && !isLiveActive) {
        return []
      }
      return players
    },
    [isLiveActive, pastReplay.pastPredictionRun?.composite_results, players, predictionTab],
  )

  const boardTrajectoryBounds = useMemo(
    () => computeSgTrajectoryBounds(displayPlayers),
    [displayPlayers],
  )

  const displaySecondaryBets =
    predictionTab === "past" ? pastReplay.pastSecondaryBets : secondaryBets

  const activeSection = resolveActiveSection(predictionTab, liveTournament, upcomingTournament)

  const diagnosticsMessage =
    predictionTab === "past"
      ? pastReplay.pastEventsBootstrapping
        ? "Loading past events and graded pick history…"
        : pastReplay.selectedPastEvent
          ? pastReplay.pastReplayLoading
            ? `Loading replay data for ${pastReplay.selectedPastEvent.event_name}…`
            : pastReplay.pastReplayHasData
              ? ""
              : "Replay snapshot is sparse for this event — showing official graded picks when available."
          : pastReplay.pastEventOptions.length === 0
            ? "No completed events available for replay yet."
            : "Select a past event from the replay selector to load market data."
      : getMatchupStateMessage({
          state: activeSection?.diagnostics?.state,
          reasonCodes: activeSection?.diagnostics?.reason_codes,
          hasFilters: selectedBooks.length > 0,
        })

  const topPlays = predictionTab === "past" ? pastReplay.pastMatchups : filteredMatchups

  const liveOpportunityAlerts =
    predictionTab === "live" ? (activeSection?.live_opportunity_alerts ?? []) : []

  const shouldShowOpportunityAlertStrip =
    predictionTab === "live" &&
    liveOpportunityAlerts.length > 0 &&
    dismissedOpportunityGeneratedAt !== (liveSnapshot?.generated_at ?? null)

  useEffect(() => {
    if (predictionTab !== "live") return
    if (!liveSnapshot?.generated_at) return
    setDismissedOpportunityGeneratedAt((current) =>
      current === liveSnapshot.generated_at ? current : null,
    )
  }, [liveSnapshot?.generated_at, predictionTab])

  const opportunityPinClockMs = useMemo(() => {
    if (!liveSnapshot?.generated_at) return 0
    const parsed = Date.parse(liveSnapshot.generated_at)
    return Number.isNaN(parsed) ? 0 : parsed
  }, [liveSnapshot?.generated_at])

  const filteredTopPlays = useMemo(() => {
    const isStillPinnedOpportunity = (firstSeenAt?: string) => {
      if (!firstSeenAt || !opportunityPinClockMs) return false
      const parsed = Date.parse(firstSeenAt)
      if (Number.isNaN(parsed)) return false
      return opportunityPinClockMs - parsed <= LIVE_OPPORTUNITY_PIN_MS
    }
    const passesOpportunityFilter = (row: {
      ev?: number
      is_new_live_opportunity?: boolean
      first_seen_at?: string
    }) => {
      if (predictionTab !== "live") return true
      if (opportunityFilter === "all") return true
      if (opportunityFilter === "new") {
        return Boolean(row.is_new_live_opportunity) || isStillPinnedOpportunity(row.first_seen_at)
      }
      const highEvThreshold = Math.max(minEdge, HIGH_EV_FLOOR)
      return Number(row.ev ?? 0) >= highEvThreshold
    }
    const prioritizeLiveOpportunity = <
      T extends { ev?: number; is_new_live_opportunity?: boolean; first_seen_at?: string },
    >(
      rows: T[],
    ) =>
      [...rows].sort((left, right) => {
        const leftPinned =
          (left.is_new_live_opportunity || isStillPinnedOpportunity(left.first_seen_at)) ? 1 : 0
        const rightPinned =
          (right.is_new_live_opportunity || isStillPinnedOpportunity(right.first_seen_at)) ? 1 : 0
        if (leftPinned !== rightPinned) return rightPinned - leftPinned
        return Number(right.ev ?? 0) - Number(left.ev ?? 0)
      })
    return prioritizeLiveOpportunity(topPlays.filter((row) => passesOpportunityFilter(row)))
  }, [topPlays, opportunityFilter, predictionTab, minEdge, opportunityPinClockMs])

  const filteredSecondaryBets = useMemo(() => {
    const isStillPinnedOpportunity = (firstSeenAt?: string) => {
      if (!firstSeenAt || !opportunityPinClockMs) return false
      const parsed = Date.parse(firstSeenAt)
      if (Number.isNaN(parsed)) return false
      return opportunityPinClockMs - parsed <= LIVE_OPPORTUNITY_PIN_MS
    }
    const passesOpportunityFilter = (row: {
      ev?: number
      is_new_live_opportunity?: boolean
      first_seen_at?: string
    }) => {
      if (predictionTab !== "live") return true
      if (opportunityFilter === "all") return true
      if (opportunityFilter === "new") {
        return Boolean(row.is_new_live_opportunity) || isStillPinnedOpportunity(row.first_seen_at)
      }
      const highEvThreshold = Math.max(minEdge, HIGH_EV_FLOOR)
      return Number(row.ev ?? 0) >= highEvThreshold
    }
    const prioritizeLiveOpportunity = <
      T extends { ev?: number; is_new_live_opportunity?: boolean; first_seen_at?: string },
    >(
      rows: T[],
    ) =>
      [...rows].sort((left, right) => {
        const leftPinned =
          (left.is_new_live_opportunity || isStillPinnedOpportunity(left.first_seen_at)) ? 1 : 0
        const rightPinned =
          (right.is_new_live_opportunity || isStillPinnedOpportunity(right.first_seen_at)) ? 1 : 0
        if (leftPinned !== rightPinned) return rightPinned - leftPinned
        return Number(right.ev ?? 0) - Number(left.ev ?? 0)
      })
    return prioritizeLiveOpportunity(displaySecondaryBets.filter((row) => passesOpportunityFilter(row)))
  }, [displaySecondaryBets, opportunityFilter, predictionTab, minEdge, opportunityPinClockMs])

  const rawGeneratedMatchups = useMemo(() => {
    if (predictionTab === "past") return pastReplay.rawGeneratedMatchups
    return getRawGeneratedMatchups(displayPredictionRun)
  }, [displayPredictionRun, pastReplay.rawGeneratedMatchups, predictionTab])

  const rawGeneratedSecondaryBets = useMemo(() => {
    if (predictionTab === "past") return pastReplay.rawGeneratedSecondaryBets
    return getRawGeneratedSecondaryBets(displayPredictionRun)
  }, [displayPredictionRun, pastReplay.rawGeneratedSecondaryBets, predictionTab])

  const topPicksEmptyMessage = useMemo(() => {
    if (predictionTab === "past") {
      if (
        rawGeneratedMatchups.length > 0 &&
        filteredTopPlays.length === 0 &&
        matchupSearch.trim()
      ) {
        return `${rawGeneratedMatchups.length} recovered matchup line(s) are available; none match your search.`
      }
      return diagnosticsMessage
    }
    const rawLen = rawGeneratedMatchups.length
    if (rawLen > 0 && filteredTopPlays.length === 0) {
      return `${diagnosticsMessage} ${rawLen} matchup line(s) from the model did not pass your filters or min edge — try more books or a lower edge threshold.`
    }
    return diagnosticsMessage
  }, [
    diagnosticsMessage,
    filteredTopPlays.length,
    matchupSearch,
    rawGeneratedMatchups.length,
    predictionTab,
  ])

  const isPastTab = predictionTab === "past"

  const rankingsColumns = useMemo(() => {
    if (predictionTab === "live") {
      return buildLiveRankingsColumns({ onPlayerSelect, trajectoryBounds: boardTrajectoryBounds })
    }
    return buildUpcomingRankingsColumns({
      onPlayerSelect,
      trajectoryBounds: boardTrajectoryBounds,
    })
  }, [onPlayerSelect, boardTrajectoryBounds, predictionTab])

  const pickColumns = useMemo(
    () =>
      buildPickColumnsForWorkspace({
        isPastTab,
        pastLeaderboardForGrades: pastReplay.pastLeaderboardForGrades,
      }),
    [isPastTab, pastReplay.pastLeaderboardForGrades],
  )

  const secondaryColumns = useMemo(
    () =>
      buildSecondaryColumnsForWorkspace({
        isPastTab,
        pastLeaderboardForGrades: pastReplay.pastLeaderboardForGrades,
        onPlayerSelect,
      }),
    [isPastTab, onPlayerSelect, pastReplay.pastLeaderboardForGrades],
  )

  const showTeamEventNotice =
    (predictionTab === "live" || predictionTab === "upcoming") && isTeamEvent(activeSection)

  const mode = predictionTab as "live" | "upcoming" | "past"

  const leaderboardModel = buildLeaderboardModel({
    mode,
    leaderboardRows: activeSection?.leaderboard ?? pastReplay.pastSnapshotSection?.leaderboard ?? [],
    players: displayPlayers,
  })

  const courseFeedModel = buildCourseFeedModel({
    mode,
    snapshotAgeSeconds,
    snapshotNotice,
    players: displayPlayers,
    timelinePoints: pastReplay.pastTimelinePoints,
    diagnosticsState:
      activeSection?.diagnostics?.state ?? pastReplay.pastSnapshotSection?.diagnostics?.state,
    fieldValidation: displayPredictionRun?.field_validation,
  })

  const { spotlight, selectedPlayer } = useCockpitSpotlight({
    predictionTab: mode,
    isLiveActive,
    eventName:
      predictionTab === "past"
        ? pastReplay.pastEventsBootstrapping
          ? "Loading past events…"
          : (pastReplay.selectedPastEvent?.event_name ?? "Past event")
        : (activeSection?.event_name ?? displayPredictionRun?.event_name ?? "No event loaded"),
    selectedPlayerKey,
    onPlayerSelect,
    players: displayPlayers,
    leaderboardRows: activeSection?.leaderboard ?? pastReplay.pastSnapshotSection?.leaderboard ?? [],
    topPlays: filteredTopPlays,
    rawGeneratedMatchups,
    rawGeneratedSecondaryBets,
  })

  const eventName =
    predictionTab === "past"
      ? pastReplay.pastEventsBootstrapping
        ? "Loading past events…"
        : (pastReplay.selectedPastEvent?.event_name ?? "Select a past event")
      : (activeSection?.event_name ?? displayPredictionRun?.event_name ?? "No event loaded")

  const courseName =
    predictionTab === "past"
      ? (pastReplay.pastPredictionRun?.course_name ?? "")
      : (activeSection?.course_name ?? displayPredictionRun?.course_name ?? "")

  const fieldSize =
    predictionTab === "past"
      ? (pastReplay.pastPredictionRun?.field_size ?? null)
      : (activeSection?.field_size ?? displayPredictionRun?.field_size ?? null)

  const modelBaselineLabel = (() => {
    if (predictionTab !== "live") return null
    if ((activeSection?.frozen_pre_teeoff_rankings?.length ?? 0) > 0) return "Baseline: frozen at tee-off"
    return "Baseline: pre-event model order"
  })()

  const scoringBaselineLabel = (() => {
    if (predictionTab !== "live") return null
    if (activeSection?.scoring_baseline_label === "frozen_at_tee_off") return "Scoring baseline: tee-off"
    return "Scoring baseline: since live start"
  })()

  const handleExportMarkdown = () => {
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

  const fullPicksTabLabel = fullPicks?.mode === "lab" ? "Full lab picks" : "Full picks"

  const fullPicksPanel = (
    <WorkspaceFullPicksPanel
      fullPicks={fullPicks}
      predictionTabPast={predictionTab === "past"}
      pastGradedMatchups={predictionTab === "past" ? pastReplay.pastMatchups : undefined}
      pastGradedSecondaryBets={predictionTab === "past" ? pastReplay.pastSecondaryBets : undefined}
    />
  )

  const leaderboardPanel = (
    <WorkspaceLeaderboardModule
      predictionTab={predictionTab}
      leaderboardModel={leaderboardModel}
      onPlayerSelect={onPlayerSelect}
    />
  )

  const renderCenterBoard = (
    compactView?: "picks" | "rankings" | "secondary" | "leaderboard" | "full-picks",
  ) => (
    <WorkspaceCenterBoard
      predictionTab={predictionTab}
      isNarrow={isNarrow}
      compactView={compactView}
      defaultTabId={urlBoardTab}
      showLeaderboard={predictionTab !== "upcoming"}
      displayPlayers={displayPlayers}
      rankingsColumns={rankingsColumns as ColumnDef<(typeof displayPlayers)[number], unknown>[]}
      powerRankingsSubtitle={powerRankingsSubtitle}
      modelBaselineLabel={modelBaselineLabel}
      scoringBaselineLabel={scoringBaselineLabel}
      filteredTopPlays={filteredTopPlays}
      filteredSecondaryBets={filteredSecondaryBets}
      displayPredictionRun={displayPredictionRun}
      minEdge={minEdge}
      selectedBooksLength={selectedBooks.length}
      matchupSearchTrimmed={matchupSearch.trim()}
      activeSectionDiagnostics={activeSection?.diagnostics}
      isLiveActive={isLiveActive}
      onPredictionTabChange={onPredictionTabChange}
      opportunityFilter={opportunityFilter}
      onOpportunityFilterChange={setOpportunityFilter}
      expandedMatchupKey={expandedMatchupKey}
      onExpandedMatchupKeyChange={setExpandedMatchupKey}
      pickColumns={pickColumns as ColumnDef<(typeof filteredTopPlays)[number], unknown>[]}
      secondaryColumns={secondaryColumns as ColumnDef<(typeof filteredSecondaryBets)[number], unknown>[]}
      topPicksEmptyMessage={topPicksEmptyMessage}
      onPlayerSelect={onPlayerSelect}
      onExportMarkdown={handleExportMarkdown}
      leaderboardPanel={leaderboardPanel}
      fullPicksPanel={fullPicksPanel}
      fullPicksTabLabel={fullPicksTabLabel}
    />
  )

  const lane = fullPicks?.mode === "lab" ? "lab" : "dashboard"
  const laneTrust = buildLaneTrustState({
    snapshotNotice: predictionTab === "past" ? null : snapshotNotice,
    displayPredictionRun,
    diagnosticsState: activeSection?.diagnostics?.state,
    usingProdSnapshotFallback,
    labLanePartialSections,
  })

  const eventMeta = [
    courseName,
    fieldSize != null ? `${fieldSize} players` : null,
    predictionTab === "live" ? "Live" : predictionTab === "upcoming" ? "Upcoming" : "Past replay",
  ]
    .filter(Boolean)
    .join(" · ")

  const latestGradedEvent = useMemo(() => {
    if (predictionTab === "past") {
      const selected = gradingHistory.find(
        (event) => String(event.event_id ?? "") === String(pastReplay.selectedPastEvent?.event_id ?? ""),
      )
      if (selected && (selected.graded_pick_count ?? 0) > 0) {
        return selected
      }
    }
    return (
      gradingHistory.find((event) => (event.graded_pick_count ?? 0) > 0) ?? gradingHistory[0] ?? null
    )
  }, [gradingHistory, pastReplay.selectedPastEvent?.event_id, predictionTab])

  const toolbarBooks = predictionTab === "past" ? pastReplay.displayAvailableBooks : availableBooks

  const contextSection = (
    <ModelCommandSection
      id="context"
      title="Context & filters"
      description="Event replay, books, search, and course intel."
    >
      <ModelFilterToolbar
        predictionTab={predictionTab}
        availableBooks={toolbarBooks}
        selectedBooks={selectedBooks}
        matchupSearch={matchupSearch}
        minEdge={minEdge}
      />
      <div className="mt-4">
        <WorkspaceLeftRail
          predictionTab={predictionTab}
          isNarrow={isNarrow}
          pastReplay={pastReplay}
          courseFeedMetrics={courseFeedModel.metrics}
          courseFeedItems={courseFeedModel.feedItems}
          displayAvailableBooks={pastReplay.displayAvailableBooks}
          selectedBooks={selectedBooks}
          onSelectedBooksChange={onSelectedBooksChange}
          matchupSearch={matchupSearch}
          onMatchupSearchChange={onMatchupSearchChange}
          minEdge={minEdge}
          onMinEdgeChange={onMinEdgeChange}
        />
      </div>
    </ModelCommandSection>
  )

  const picksSection = (
    <ModelCommandSection
      id="picks"
      title="Actionable plays"
      description="+EV matchup picks and secondary markets for the active event."
      variant="picks"
      testId="model-section-picks"
    >
      <div className="mb-3">
        <ModelFilterToolbar
          predictionTab={predictionTab}
          availableBooks={toolbarBooks}
          selectedBooks={selectedBooks}
          onSelectedBooksChange={onSelectedBooksChange}
          matchupSearch={matchupSearch}
          onMatchupSearchChange={onMatchupSearchChange}
          minEdge={minEdge}
          onMinEdgeChange={onMinEdgeChange}
        />
      </div>
      {renderCenterBoard("picks")}
    </ModelCommandSection>
  )

  const rankingsSection = (
    <ModelCommandSection
      id="rankings"
      title={predictionTab === "past" ? "Pre-tee-off rankings" : "Power rankings"}
      description={`${displayPlayers.length} players ranked by model`}
      testId="model-section-rankings"
    >
      {renderCenterBoard("rankings")}
    </ModelCommandSection>
  )

  const marketsSection = (
    <ModelCommandSection
      id="markets"
      title="Secondary markets"
      description="Top 10, top 20, and other +EV opportunities."
      testId="model-section-markets"
    >
      {renderCenterBoard("secondary")}
    </ModelCommandSection>
  )

  const leaderboardSection =
    predictionTab !== "upcoming" ? (
      <ModelCommandSection id="leaderboard" title="Leaderboard" description="Live scoring board.">
        {renderCenterBoard("leaderboard")}
      </ModelCommandSection>
    ) : null

  const fullPicksSection = (
    <ModelCommandSection id="full-picks" title={fullPicksTabLabel} description="Full card export and logging.">
      {renderCenterBoard("full-picks")}
    </ModelCommandSection>
  )

  const diagnosticsSection = (
    <ModelCommandSection
      id="diagnostics"
      title="Market diagnostics"
      description="Why picks may be empty or filtered."
    >
      <TopPicksPipelineHint
        diagnostics={activeSection?.diagnostics}
        predictionTab={predictionTab}
        minEdge={minEdge}
        selectedBooksLength={selectedBooks.length}
        matchupSearchTrimmed={matchupSearch.trim()}
      />
      <DiagnosticsFunnel
        diagnostics={activeSection?.diagnostics}
        emptyMessage={filteredTopPlays.length === 0 ? topPicksEmptyMessage : undefined}
      />
    </ModelCommandSection>
  )

  const resultsSection = (
    <ModelCommandSection id="results" title="Results preview" description="Latest graded performance.">
      <ResultsPreview
        latestEvent={latestGradedEvent}
        pickSourceLabel={lane === "lab" ? "Lab" : "Dashboard"}
      />
    </ModelCommandSection>
  )

  const mobileSections = [
    { id: "picks", label: "Plays", badge: filteredTopPlays.length, content: picksSection },
    { id: "rankings", label: "Rankings", content: rankingsSection },
    { id: "markets", label: "Markets", badge: displaySecondaryBets.length || undefined, content: marketsSection },
    ...(leaderboardSection
      ? [{ id: "leaderboard", label: "Board", content: leaderboardSection }]
      : []),
    { id: "context", label: "Filters", content: contextSection, desktopOnly: false },
  ]

  const desktopSections = [
    picksSection,
    rankingsSection,
    marketsSection,
    ...(leaderboardSection ? [leaderboardSection] : []),
    fullPicksSection,
    diagnosticsSection,
    contextSection,
    resultsSection,
  ]

  return (
    <div
      className={
        isNarrow
          ? "prediction-workspace prediction-workspace--narrow prediction-workspace-root monitor-scroll-region"
          : "prediction-workspace prediction-workspace-root monitor-scroll-region"
      }
    >
      <WorkspaceAlerts
        displayPredictionRun={displayPredictionRun}
        shouldShowOpportunityAlertStrip={shouldShowOpportunityAlertStrip}
        liveOpportunityAlerts={liveOpportunityAlerts}
        liveSnapshot={liveSnapshot}
        onDismissOpportunityAlerts={() =>
          setDismissedOpportunityGeneratedAt(liveSnapshot?.generated_at ?? null)
        }
        predictionTabPastLoading={
          predictionTab === "past" &&
          (pastReplay.pastEventsBootstrapping ||
            (pastReplay.pastReplayLoading && !pastReplay.pastReplayHasData))
        }
        pastEventName={pastReplay.selectedPastEvent?.event_name}
        predictionTabPastError={
          predictionTab === "past" &&
          pastReplay.pastReplayHasError &&
          !pastReplay.pastReplayLoading &&
          !pastReplay.pastReplayHasData
        }
        pastReplayErrorMessage={pastReplay.pastReplayErrorMessage ?? "Replay API request failed."}
        predictionTabPastNoEvent={
          predictionTab === "past" &&
          !pastReplay.pastEventsBootstrapping &&
          !pastReplay.pastReplayLoading &&
          !pastReplay.pastReplayHasData &&
          !pastReplay.pastReplayHasError &&
          pastReplay.pastEventOptions.length === 0
        }
      />

      <div className="model-command-center">
        <EventCommandHeader
          lane={lane}
          eventName={eventName}
          meta={eventMeta}
          kpis={[
            {
              id: "combined",
              label: "Combined P&L",
              value: formatUnits(pastReplay.recordSummary.combined.profit),
              tone: pastReplay.recordSummary.combined.profit >= 0 ? "positive" : "negative",
            },
            {
              id: "picks",
              label: "+EV picks",
              value:
                predictionTab === "past"
                  ? String(pastReplay.recordSummary.combined.picks)
                  : String(filteredTopPlays.length),
            },
            {
              id: "field",
              label: "Field",
              value: fieldSize != null ? String(fieldSize) : "—",
            },
          ]}
        />

        {laneTrust ? (
          <TrustStatusBanner tone={laneTrust.tone} title={laneTrust.title} message={laneTrust.message} />
        ) : null}

        {showTeamEventNotice ? (
          <TeamEventNotice
            eventName={eventName}
            courseName={courseName}
            mode={predictionTab === "live" ? "live" : "upcoming"}
          />
        ) : null}

        <ModelCommandLayout
          defaultMobileSectionId="picks"
          sections={
            isNarrow
              ? mobileSections.map((section) =>
                  section.id === "rankings"
                    ? { ...section, content: rankingsSection }
                    : section,
                )
              : desktopSections.map((content, index) => ({
                  id: `desktop-${index}`,
                  label: "",
                  content,
                }))
          }
        />
      </div>

      <PlayerInsightDrawer
        open={Boolean(selectedPlayerKey)}
        onOpenChange={(open) => {
          if (!open) onPlayerSelect("")
        }}
        playerName={selectedPlayer?.player_display}
      >
        <PlayerSpotlightPanel
          spotlight={spotlight}
          player={selectedPlayer}
          profile={selectedPlayerProfile}
          profileState={playerProfileState}
          profileErrorMessage={playerProfileErrorMessage}
          onRetryProfile={onPlayerProfileRetry}
          richProfilesEnabled={richProfilesEnabled}
        />
      </PlayerInsightDrawer>
    </div>
  )
}

export type { PredictionWorkspacePageProps } from "./workspace-types"
