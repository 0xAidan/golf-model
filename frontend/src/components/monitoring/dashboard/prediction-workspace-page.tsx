import type { ColumnDef } from "@tanstack/react-table"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"

import { PlayerSpotlightPanel } from "@/components/cockpit/player-spotlight"
import { TeamEventNotice } from "@/components/cockpit/team-event-notice"
import { CockpitModule, CockpitWorkspace } from "@/components/cockpit/workspace"
import {
  buildCourseFeedModel,
  buildLeaderboardModel,
} from "@/lib/cockpit-event-models"
import { getMatchupStateMessage } from "@/lib/cockpit-matchups"
import { isTeamEvent } from "@/lib/event-format"
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
import { WorkspaceMacroKpis } from "./workspace-macro-kpis"
import { HIGH_EV_FLOOR, LIVE_OPPORTUNITY_PIN_MS } from "./workspace-constants"
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
  fullPicks,
}: PredictionWorkspacePageProps) {
  const isNarrow = useIsNarrowViewport()
  const [searchParams] = useSearchParams()
  const urlBoardTab = searchParams.get("tab") === "full-picks" ? "full-picks" : undefined
  const [expandedMatchupKey, setExpandedMatchupKey] = useState<string | null>(null)
  const [opportunityFilter, setOpportunityFilter] = useState<"all" | "new" | "high">("all")
  const [dismissedOpportunityGeneratedAt, setDismissedOpportunityGeneratedAt] = useState<string | null>(null)

  const pastReplay = useWorkspacePastReplay({
    predictionTab,
    gradingHistory,
    gradingRecordSummary,
    matchupSearch,
    availableBooks,
    pastReplaySource,
    onPastEventContextChange,
  })

  const liveTournament = liveSnapshot?.live_tournament
  const upcomingTournament = liveSnapshot?.upcoming_tournament
  const isLiveActive = Boolean(liveTournament?.active)

  const displayPredictionRun = resolveDisplayPredictionRun(
    predictionTab,
    predictionRun,
    pastReplay.pastPredictionRun,
  )

  const displayPlayers = useMemo(
    () =>
      predictionTab === "past"
        ? (pastReplay.pastPredictionRun?.composite_results ?? [])
        : players,
    [pastReplay.pastPredictionRun?.composite_results, players, predictionTab],
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
      ? "Select a past event from the replay selector to load market data."
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
      return buildLiveRankingsColumns({ onPlayerSelect })
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
        ? (pastReplay.selectedPastEvent?.event_name ?? "Past event snapshot unavailable")
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
      ? (pastReplay.selectedPastEvent?.event_name ?? "Past event snapshot unavailable")
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
    <WorkspaceFullPicksPanel fullPicks={fullPicks} predictionTabPast={predictionTab === "past"} />
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

  const leftRail = (
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
  )

  const rightRail = (
    <CockpitModule
      flex={3}
      title="Player spotlight"
      tone="accent"
      emptyState={selectedPlayerKey ? undefined : "Click any player to open spotlight."}
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
    </CockpitModule>
  )

  return (
    <div
      className={
        isNarrow
          ? "prediction-workspace prediction-workspace--narrow prediction-workspace-root"
          : "prediction-workspace prediction-workspace-root"
      }
    >
      <WorkspaceAlerts
        snapshotNotice={snapshotNotice}
        displayPredictionRun={displayPredictionRun}
        shouldShowOpportunityAlertStrip={shouldShowOpportunityAlertStrip}
        liveOpportunityAlerts={liveOpportunityAlerts}
        liveSnapshot={liveSnapshot}
        onDismissOpportunityAlerts={() =>
          setDismissedOpportunityGeneratedAt(liveSnapshot?.generated_at ?? null)
        }
        predictionTabPastLoading={
          predictionTab === "past" && pastReplay.pastReplayLoading && !pastReplay.pastReplayHasData
        }
        pastEventName={pastReplay.selectedPastEvent?.event_name}
        predictionTabPastError={
          predictionTab === "past" &&
          pastReplay.pastReplayHasError &&
          !pastReplay.pastReplayLoading &&
          !pastReplay.pastReplayHasData
        }
        pastReplayErrorMessage={pastReplay.pastReplayErrorMessage ?? "Replay API request failed."}
      />

      <WorkspaceMacroKpis
        eventName={eventName}
        courseName={courseName}
        fieldSize={fieldSize}
        recordSummary={pastReplay.recordSummary}
        isNarrow={isNarrow}
      />

      {isNarrow ? (
        <div className="workspace-filter-summary-row">
          <span className="filter-summary-chip" data-testid="filter-summary-chip">
            {selectedBooks.length > 0
              ? `${selectedBooks.length} book${selectedBooks.length === 1 ? "" : "s"}`
              : "All books"}
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
                  badge: filteredTopPlays.length,
                  content: renderCenterBoard("picks"),
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
                  id: "full-picks",
                  label: fullPicksTabLabel,
                  content: renderCenterBoard("full-picks"),
                },
                {
                  id: "intel",
                  label: "Intel",
                  content: leftRail,
                },
                {
                  id: "player",
                  label: "Player",
                  content: rightRail,
                },
              ]
            : undefined
        }
        leftRail={isNarrow ? null : leftRail}
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
                <div className="cockpit-center-stack">{renderCenterBoard()}</div>
              )}
            </>
          )
        }
        rightRail={isNarrow ? null : rightRail}
      />
    </div>
  )
}

export type { PredictionWorkspacePageProps } from "./workspace-types"
