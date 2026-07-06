import { LabPicksPage } from "@/pages/lab-picks-page"
import { PicksPage } from "@/pages/picks-page"

import { PanelBackfill } from "../panel-backfill"
import type { WorkspaceFullPicksEmbed, WorkspaceFullPicksProduction } from "./workspace-types"

export function WorkspaceFullPicksPanel({
  fullPicks,
  predictionTabPast,
  pastGradedMatchups,
  pastGradedSecondaryBets,
  pastPicksLoading = false,
}: {
  fullPicks?: WorkspaceFullPicksEmbed
  predictionTabPast: boolean
  pastGradedMatchups?: WorkspaceFullPicksProduction["matchups"]
  pastGradedSecondaryBets?: WorkspaceFullPicksProduction["secondaryBets"]
  pastPicksLoading?: boolean
}) {
  if (predictionTabPast) {
    const pastMatchups = pastGradedMatchups ?? []
    const pastSecondary = pastGradedSecondaryBets ?? []
    return (
      <div className="workspace-full-picks-embed" data-testid="workspace-full-picks-past">
        <PicksPage
          embedded
          lane="production"
          matchups={pastMatchups}
          matchupsEmptyMessage="No graded matchup picks for this event."
          minEdgePct={0}
          secondaryBets={pastSecondary}
          onPlayerSelect={fullPicks?.onPlayerSelect}
          embeddedLoading={pastPicksLoading}
          embeddedLoadingMessage="Loading graded picks for this event…"
          secondaryEmptyMessage="No graded secondary picks for this event."
        />
      </div>
    )
  }

  if (!fullPicks) {
    return (
      <PanelBackfill
        message="Full picks unavailable"
        detail="Pick inventory loads when a live or upcoming event is active."
        loading={false}
        testId="workspace-full-picks-backfill"
      />
    )
  }

  if (fullPicks.mode === "lab") {
    return (
      <div className="workspace-full-picks-embed lane-lab" data-testid="workspace-full-lab-picks">
        <LabPicksPage
          embedded
          matchups={fullPicks.matchups}
          matchupsEmptyMessage={fullPicks.matchupsEmptyMessage}
          matchupDiagnostics={fullPicks.matchupDiagnostics}
          minEdgePct={fullPicks.minEdgePct}
          secondaryBets={fullPicks.secondaryBets}
          onPlayerSelect={fullPicks.onPlayerSelect}
          marketRows={fullPicks.marketRows}
          marketRowsLoading={fullPicks.marketRowsLoading}
          marketRowsError={fullPicks.marketRowsError}
          tournamentId={fullPicks.tournamentId}
          profileName={fullPicks.profileName}
          predictionRun={fullPicks.predictionRun}
        />
      </div>
    )
  }

  return (
    <div className="workspace-full-picks-embed" data-testid="workspace-full-picks">
      <PicksPage
        embedded
        lane="production"
        matchups={fullPicks.matchups}
        matchupsEmptyMessage={fullPicks.matchupsEmptyMessage}
        matchupDiagnostics={fullPicks.matchupDiagnostics}
        minEdgePct={fullPicks.minEdgePct}
        secondaryBets={fullPicks.secondaryBets}
        onPlayerSelect={fullPicks.onPlayerSelect}
        marketRows={fullPicks.marketRows}
        marketRowsLoading={fullPicks.marketRowsLoading}
        marketRowsError={fullPicks.marketRowsError}
      />
    </div>
  )
}
