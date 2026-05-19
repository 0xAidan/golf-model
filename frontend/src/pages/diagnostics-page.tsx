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
      <main aria-labelledby="diagnostics-page-h1">
        <h1
          id="diagnostics-page-h1"
          style={{
            margin: "0 0 8px",
            fontFamily: "var(--font-mono)",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "var(--text)",
          }}
        >
          Diagnostics
        </h1>
        <p style={{ margin: "0 0 12px", fontSize: 11, color: "var(--text-muted)", maxWidth: 720 }}>
          Runtime health and pipeline state for the cockpit snapshot.
        </p>
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title" style={{ margin: 0, fontSize: 13 }}>
                Snapshot diagnostics
              </h2>
              <div className="card-desc">Grading counters, model warnings, and event context.</div>
            </div>
            <Link to="/" className="btn btn-ghost" style={{ fontSize: 11, padding: "3px 8px" }}>
              Back to cockpit
            </Link>
          </div>
          <div className="card-body" style={{ gap: 10, display: "flex", flexDirection: "column" }}>
            {predictionTab === "past" ? (
              <div className="term-notice" role="note">
                Past replay diagnostics are tied to the selected replay event on the cockpit page.{" "}
                <Link to="/?tab=past" style={{ color: "var(--accent-link)", textDecoration: "underline" }}>
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
              <h2
                id="diagnostics-grading-heading"
                style={{
                  margin: "0 0 8px",
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                }}
              >
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
