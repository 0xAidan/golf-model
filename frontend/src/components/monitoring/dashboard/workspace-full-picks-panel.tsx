import { LabPicksPage } from "@/pages/lab-picks-page"
import { PicksPage } from "@/pages/picks-page"

import { PanelBackfill } from "../panel-backfill"
import type { WorkspaceFullPicksEmbed, WorkspaceFullPicksProduction } from "./workspace-types"

export function WorkspaceFullPicksPanel({
  fullPicks,
  predictionTabPast,
  pastGradedMatchups,
  pastGradedSecondaryBets,
}: {
  fullPicks?: WorkspaceFullPicksEmbed
  predictionTabPast: boolean
  pastGradedMatchups?: WorkspaceFullPicksProduction["matchups"]
  pastGradedSecondaryBets?: WorkspaceFullPicksProduction["secondaryBets"]
}) {
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

  if (predictionTabPast) {
    const pastMatchups = pastGradedMatchups ?? []
    const pastSecondary = pastGradedSecondaryBets ?? []
    if (pastMatchups.length === 0 && pastSecondary.length === 0) {
      return (
        <PanelBackfill
          message="Past replay lives on the board tabs"
          detail="Switch to Top picks or use Recent results in Intel for graded history."
          loading={false}
          testId="workspace-full-picks-past-backfill"
        />
      )
    }

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
        />
      </div>
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
