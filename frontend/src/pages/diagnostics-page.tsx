import { Link } from "react-router-dom"

import { DataHealthPanel } from "@/components/data-health-panel"
import { DiagnosticsGradingPanel } from "@/components/cockpit/event-modules"
import { PageHeader } from "@/components/ui/page-header"
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
    diagnostics: predictionTab === "past" ? undefined : activeSection?.diagnostics,
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
    <div className="research-page">
      <main aria-labelledby="diagnostics-page-h1">
        <PageHeader
          titleId="diagnostics-page-h1"
          eyebrow="Research"
          title="Diagnostics"
          description="Runtime health and pipeline state for the cockpit snapshot."
          action={
            <Link to="/" className="btn btn-ghost btn-sm">
              Back to cockpit
            </Link>
          }
        />

        <DataHealthPanel />

        <div className="card research-card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Snapshot diagnostics</h2>
              <div className="card-desc">Grading counters, model warnings, and event context.</div>
            </div>
          </div>
          <div className="card-body research-card-body">
            {predictionTab === "past" ? (
              <div className="term-notice" role="note">
                Past replay diagnostics are tied to the selected replay event on the cockpit page.{" "}
                <Link to="/?tab=past" className="link-subtle">
                  Open cockpit in Past mode
                </Link>
                .
              </div>
            ) : null}
            {predictionTab === "live" && !isLiveActive ? (
              <div className="term-notice" role="status">
                No live event is active right now. Switch the mode to Upcoming for active diagnostics.
              </div>
            ) : null}
            <section aria-labelledby="diagnostics-grading-heading">
              <h2 id="diagnostics-grading-heading" className="research-section-heading">
                Grading and pipeline
              </h2>
              <DiagnosticsGradingPanel
                metrics={diagnosticsModel.metrics}
                counters={diagnosticsModel.counters}
                reasonCodes={diagnosticsModel.reasonCodes}
                warnings={diagnosticsModel.warnings}
                selectedEventSummary={diagnosticsModel.selectedEventSummary}
              />
            </section>
          </div>
        </div>
      </main>
    </div>
  )
}
