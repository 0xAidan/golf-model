import type { ColumnDef } from "@tanstack/react-table"
import { Download, ExternalLink, Radar } from "lucide-react"
import { Link } from "react-router-dom"
import type { ReactNode } from "react"

import { MatchupExpandDetail } from "@/components/cockpit/matchup-expand-detail"
import { LeaderboardPanel } from "@/components/cockpit/event-modules"
import { CockpitResizableStack } from "@/components/cockpit/cockpit-resizable-stack"
import { CockpitModule } from "@/components/cockpit/workspace"
import { BentoGrid } from "@/components/monitoring/bento-grid"
import { BentoPanel } from "@/components/monitoring/bento-panel"
import { HeroDataGrid } from "@/components/monitoring/hero-data-grid"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import {
  buildMatchupKey,
  buildPickColumns,
  buildSecondaryColumns,
} from "@/lib/cockpit-columns"
import type {
  CompositePlayer,
  FlattenedSecondaryBet,
  LiveLeaderboardRow,
  LiveTournamentSnapshot,
  MatchupBet,
  PredictionRunResponse,
} from "@/lib/types"

import { TopPicksPipelineHint } from "./workspace-pipeline-hint"
import { PastPickGradeCell, PastSecondaryGradeCell, WorkspaceEmptyState } from "./workspace-grade-cells"

export type WorkspaceCenterBoardProps = {
  predictionTab: PredictionTab
  isNarrow: boolean
  compactView?: "picks" | "rankings" | "secondary" | "leaderboard" | "full-picks"
  defaultTabId?: string
  showLeaderboard: boolean
  displayPlayers: CompositePlayer[]
  rankingsColumns: ColumnDef<CompositePlayer, unknown>[]
  powerRankingsSubtitle?: string | null
  modelBaselineLabel: string | null
  scoringBaselineLabel: string | null
  filteredTopPlays: MatchupBet[]
  filteredSecondaryBets: FlattenedSecondaryBet[]
  displayPredictionRun: PredictionRunResponse | null
  minEdge: number
  selectedBooksLength: number
  matchupSearchTrimmed: string
  activeSectionDiagnostics?: LiveTournamentSnapshot["diagnostics"]
  isLiveActive: boolean
  onPredictionTabChange: (value: PredictionTab) => void
  opportunityFilter: "all" | "new" | "high"
  onOpportunityFilterChange: (value: "all" | "new" | "high") => void
  expandedMatchupKey: string | null
  onExpandedMatchupKeyChange: (key: string | null) => void
  pickColumns: ColumnDef<MatchupBet, unknown>[]
  secondaryColumns: ColumnDef<FlattenedSecondaryBet, unknown>[]
  topPicksEmptyMessage: string
  onPlayerSelect: (playerKey: string) => void
  onExportMarkdown: () => void
  leaderboardPanel: ReactNode
  fullPicksPanel: ReactNode
  fullPicksTabLabel: string
}

export function WorkspaceCenterBoard({
  predictionTab,
  isNarrow,
  compactView,
  defaultTabId,
  showLeaderboard,
  displayPlayers,
  rankingsColumns,
  powerRankingsSubtitle,
  modelBaselineLabel,
  scoringBaselineLabel,
  filteredTopPlays,
  filteredSecondaryBets,
  displayPredictionRun,
  minEdge,
  selectedBooksLength,
  matchupSearchTrimmed,
  activeSectionDiagnostics,
  isLiveActive,
  onPredictionTabChange,
  opportunityFilter,
  onOpportunityFilterChange,
  expandedMatchupKey,
  onExpandedMatchupKeyChange,
  pickColumns,
  secondaryColumns,
  topPicksEmptyMessage,
  onPlayerSelect,
  onExportMarkdown,
  leaderboardPanel,
  fullPicksPanel,
  fullPicksTabLabel,
}: WorkspaceCenterBoardProps) {
  const rankings = (
    <div className="card cockpit-stack-card">
      <div className="card-header card-header--stacked">
        <div className="card-header-main">
          <div className="card-title">
            {predictionTab === "past" ? "Pre-tee-off rankings" : "Power rankings"}
          </div>
          <div className="card-desc">
            {predictionTab === "past"
              ? `${displayPlayers.length} players — last rankings before tee off`
              : `${displayPlayers.length} players ranked by model`}
          </div>
        </div>
        {(predictionTab === "live" && (modelBaselineLabel || scoringBaselineLabel)) ||
        powerRankingsSubtitle ? (
          <div className="card-header-meta" data-testid="rankings-header-meta">
            {predictionTab === "live" && modelBaselineLabel ? (
              <span className="card-meta-chip">{modelBaselineLabel}</span>
            ) : null}
            {predictionTab === "live" && scoringBaselineLabel ? (
              <span className="card-meta-chip">{scoringBaselineLabel}</span>
            ) : null}
            {powerRankingsSubtitle ? (
              <span className="card-meta-chip card-meta-chip--subtle">{powerRankingsSubtitle}</span>
            ) : null}
          </div>
        ) : null}
        <Link to="/players" className="card-header-link">
          All <ExternalLink size={11} />
        </Link>
      </div>
      <div className="table-scroll">
        {predictionTab === "live" && !isLiveActive ? (
          <div className="card-body">
            <div className="empty-state">
              <Radar size={28} className="empty-state-icon" />
              <div className="empty-state-title">No live tournament right now</div>
              <div className="empty-state-desc">
                Switch to{" "}
                <button
                  type="button"
                  className="text-link-btn"
                  onClick={() => onPredictionTabChange("upcoming")}
                >
                  Upcoming
                </button>{" "}
                for pre-tournament picks and rankings.
              </div>
            </div>
          </div>
        ) : displayPlayers.length > 0 ? (
          <HeroDataGrid
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
            <WorkspaceEmptyState message="No rankings available for this event context." />
          </div>
        )}
      </div>
    </div>
  )

  const topPicks = (
    <div className="card cockpit-stack-card cockpit-stack-card--picks">
      <div className="card-header">
        <div>
          <div className="card-title">
            {predictionTab === "past" ? "Generated picks" : "Top picks"}
          </div>
          <div className="card-desc">
            {predictionTab === "past"
              ? `${filteredTopPlays.length} recovered +EV matchup lines`
              : `${filteredTopPlays.length} qualifying lines · edge ≥ ${(minEdge * 100).toFixed(0)}%`}
          </div>
        </div>
        {!displayPredictionRun?.card_content ? (
          <p id="cockpit-export-disabled-help" className="export-help-text">
            Export stays off until the run includes generated card content for this event.
          </p>
        ) : null}
        <button
          className="btn btn-ghost btn-export"
          onClick={onExportMarkdown}
          disabled={!displayPredictionRun?.card_content}
          data-testid="btn-export"
          aria-describedby={!displayPredictionRun?.card_content ? "cockpit-export-disabled-help" : undefined}
        >
          <Download size={12} />
          Export
        </button>
      </div>

      <TopPicksPipelineHint
        diagnostics={activeSectionDiagnostics}
        predictionTab={predictionTab}
        minEdge={minEdge}
        selectedBooksLength={selectedBooksLength}
        matchupSearchTrimmed={matchupSearchTrimmed}
      />
      {predictionTab === "live" ? (
        <div className="filter-strip workspace-opportunity-filters" role="group" aria-label="Live opportunity filters">
          <button
            type="button"
            className={`filter-chip${opportunityFilter === "all" ? " active" : ""}`}
            onClick={() => onOpportunityFilterChange("all")}
          >
            All
          </button>
          <button
            type="button"
            className={`filter-chip${opportunityFilter === "new" ? " active" : ""}`}
            onClick={() => onOpportunityFilterChange("new")}
          >
            New this refresh
          </button>
          <button
            type="button"
            className={`filter-chip${opportunityFilter === "high" ? " active" : ""}`}
            onClick={() => onOpportunityFilterChange("high")}
          >
            High EV
          </button>
        </div>
      ) : null}

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
        ) : filteredTopPlays.length > 0 ? (
          <HeroDataGrid
            data={filteredTopPlays}
            columns={pickColumns}
            density="compact"
            virtualizeAfter={80}
            getRowId={(matchup) => buildMatchupKey(matchup)}
            getRowTestId={(matchup) => `matchup-row-${buildMatchupKey(matchup)}`}
            expandedRowId={expandedMatchupKey}
            onRowClick={(matchup) => {
              const key = buildMatchupKey(matchup)
              onExpandedMatchupKeyChange(expandedMatchupKey === key ? null : key)
            }}
            renderSubRow={(matchup) => <MatchupExpandDetail matchup={matchup} />}
            getRowClassName={(matchup) =>
              matchup.is_new_live_opportunity
                ? "row-live-opportunity"
                : matchup.is_material_ev_increase
                  ? "row-live-material"
                  : undefined
            }
            testId="cockpit-picks-grid"
          />
        ) : (
          <div className="card-body">
            <WorkspaceEmptyState message={topPicksEmptyMessage} />
          </div>
        )}
      </div>
    </div>
  )

  const secondary = (
    <div className="card cockpit-stack-card">
      <div className="card-header">
        <div className="card-title">Secondary markets</div>
        <div className="card-desc">
          {filteredSecondaryBets.length} picks
          <Link
            to="/?tab=full-picks"
            style={{ marginLeft: 8, color: "var(--accent-link)", fontSize: 10, textDecoration: "none" }}
          >
            All →
          </Link>
        </div>
      </div>
      <div className="table-scroll">
        {filteredSecondaryBets.length > 0 ? (
          <HeroDataGrid
            data={filteredSecondaryBets}
            columns={secondaryColumns}
            density="compact"
            virtualizeAfter={80}
            getRowId={(bet) => `${bet.market}-${bet.player}-${bet.odds}`}
            getRowTestId={(bet) => `secondary-row-${bet.player}`}
            onRowClick={(bet) => bet.player_key && onPlayerSelect(bet.player_key)}
            getRowClassName={(bet) =>
              bet.is_new_live_opportunity
                ? "row-live-opportunity"
                : bet.is_material_ev_increase
                  ? "row-live-material"
                  : undefined
            }
            testId="cockpit-secondary-grid"
          />
        ) : (
          <div className="card-body">
            <WorkspaceEmptyState message="No secondary market edges in this context." />
          </div>
        )}
      </div>
    </div>
  )

  const stack = (
    <CockpitResizableStack
      layout={compactView != null ? "stack" : isNarrow ? "stack" : "panels"}
      compactView={compactView}
      defaultTabId={defaultTabId}
      showLeaderboard={showLeaderboard}
      fullPicksTabLabel={fullPicksTabLabel}
      rankings={rankings}
      topPicks={topPicks}
      secondary={secondary}
      fullPicks={fullPicksPanel}
      leaderboard={leaderboardPanel}
    />
  )

  if (compactView != null) {
    return stack
  }

  return (
    <BentoGrid columns={12} testId="workspace-bento-grid" className="workspace-bento-grid">
      <BentoPanel span={12} rowSpan={2} testId="workspace-bento-board">
        {stack}
      </BentoPanel>
    </BentoGrid>
  )
}

export function buildPickColumnsForWorkspace({
  isPastTab,
  pastLeaderboardForGrades,
  completedReplay = false,
}: {
  isPastTab: boolean
  pastLeaderboardForGrades: LiveLeaderboardRow[]
  completedReplay?: boolean
}) {
  return buildPickColumns({
    isPast: isPastTab,
    renderResult: isPastTab
      ? (matchup) => (
          <span data-testid={`matchup-grade-${buildMatchupKey(matchup)}`}>
            <PastPickGradeCell
              matchup={matchup}
              leaderboard={pastLeaderboardForGrades}
              completedReplay={completedReplay}
            />
          </span>
        )
      : undefined,
  })
}

export function buildSecondaryColumnsForWorkspace({
  isPastTab,
  pastLeaderboardForGrades,
  onPlayerSelect,
}: {
  isPastTab: boolean
  pastLeaderboardForGrades: LiveLeaderboardRow[]
  onPlayerSelect: (playerKey: string) => void
}) {
  return buildSecondaryColumns({
    isPast: isPastTab,
    onPlayerSelect,
    renderResult: isPastTab
      ? (bet) => (
          <span data-testid={`secondary-grade-${bet.market}-${bet.player}`}>
            <PastSecondaryGradeCell
              bet={bet}
              leaderboard={pastLeaderboardForGrades}
              completedReplay={isPastTab}
            />
          </span>
        )
      : undefined,
  })
}

export function WorkspaceLeaderboardModule({
  predictionTab,
  leaderboardModel,
  onPlayerSelect,
}: {
  predictionTab: PredictionTab
  leaderboardModel: {
    metrics: Parameters<typeof LeaderboardPanel>[0]["metrics"]
    rows: Parameters<typeof LeaderboardPanel>[0]["rows"]
    seededFromRankings: boolean
    emptyMessage: string | null
  }
  onPlayerSelect: (playerKey: string) => void
}) {
  if (predictionTab === "upcoming") return null

  return (
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
  )
}
