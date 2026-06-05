import { LabPicksPage } from "@/pages/lab-picks-page"
import { PicksPage } from "@/pages/picks-page"

import { PanelBackfill } from "../panel-backfill"
import type { WorkspaceFullPicksEmbed } from "./workspace-types"

export function WorkspaceFullPicksPanel({
  fullPicks,
  predictionTabPast,
}: {
  fullPicks?: WorkspaceFullPicksEmbed
  predictionTabPast: boolean
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
    return (
      <PanelBackfill
        message="Past replay lives on the board tabs"
        detail="Switch to Top picks or use Recent results in Intel for graded history."
        loading={false}
        testId="workspace-full-picks-past-backfill"
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
