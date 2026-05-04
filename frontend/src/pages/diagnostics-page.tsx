import { Link } from "react-router-dom"

import { DiagnosticsGradingPanel } from "@/components/cockpit/event-modules"
import type { PredictionTab } from "@/hooks/use-prediction-tab"
import { buildDiagnosticsModel } from "@/lib/cockpit-event-models"
import type {
  DashboardState,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  PredictionRunResponse,
} from "@/lib/types"

export function DiagnosticsPage({
  dashboard,
  liveSnapshot,
  predictionTab,
  isLiveActive,
  gradingHistory,
  predictionRun,
  secondaryBets,
}: {
  dashboard?: DashboardState
  liveSnapshot: LiveRefreshSnapshot | null
  predictionTab: PredictionTab
  isLiveActive: boolean
  gradingHistory: GradedTournamentSummary[]
  predictionRun: PredictionRunResponse | null
  secondaryBets: FlattenedSecondaryBet[]
}) {
  const activeSection =
    predictionTab === "upcoming"
      ? liveSnapshot?.upcoming_tournament
      : liveSnapshot?.live_tournament

  const diagnosticsModel = buildDiagnosticsModel({
    mode: predictionTab,
    diagnostics:
      predictionTab === "past"
        ? undefined
        : activeSection?.diagnostics,
    dashboardAiAvailable: dashboard?.ai_status?.available ?? false,
    strategySource: dashboard?.baseline_provenance?.strategy_source,
    strategyName: dashboard?.baseline_provenance?.live_strategy_name,
    warnings: predictionRun?.warnings,
    gradingHistory,
    selectedEventId: undefined,
    timelinePoints: [],
    currentSecondaryBets: secondaryBets,
  })

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "10px 12px" }}>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Diagnostics</div>
            <div className="card-desc">Runtime health and pipeline state.</div>
          </div>
          <Link to="/" className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }}>
            Back to cockpit
          </Link>
        </div>
        <div className="card-body" style={{ gap: 10, display: "flex", flexDirection: "column" }}>
          {predictionTab === "past" ? (
            <div className="term-notice">
              Past replay diagnostics are tied to the selected replay event on the cockpit page.
            </div>
          ) : null}
          {predictionTab === "live" && !isLiveActive ? (
            <div className="term-notice">
              No live event is active right now. Switch the mode to Upcoming for active diagnostics.
            </div>
          ) : null}
          <DiagnosticsGradingPanel
            metrics={diagnosticsModel.metrics}
            counters={diagnosticsModel.counters}
            reasonCodes={diagnosticsModel.reasonCodes}
            warnings={diagnosticsModel.warnings}
            selectedEventSummary={diagnosticsModel.selectedEventSummary}
          />
        </div>
      </div>
    </div>
  )
}
