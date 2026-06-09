import { Link } from "react-router-dom"

import { DataHealthPanel } from "@/components/data-health-panel"
import { DiagnosticsGradingPanel } from "@/components/cockpit/event-modules"
import { BentoGrid, BentoPanel, HeroBand } from "@/components/monitoring"
import { buildDiagnosticsModel } from "@/lib/cockpit-event-models"
import type {
  DashboardState,
  FlattenedSecondaryBet,
  GradedTournamentSummary,
  LiveRefreshSnapshot,
  PredictionRunResponse,
} from "@/lib/types"
import type { PredictionTab } from "@/hooks/use-prediction-tab"

export function SystemPage({
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
    <div className="monitor-research-page monitor-scroll-region" data-testid="system-page">
      <main aria-label="System health and diagnostics">
        <HeroBand
          title="System"
          eyebrow="Health"
          meta="Snapshot freshness, pipeline diagnostics, and data health for the operator board."
          action={
            <Link to="/" className="btn btn-ghost btn-sm">
              Back to Dashboard
            </Link>
          }
        />

        <BentoGrid columns={2} testId="system-bento">
          <BentoPanel title="Data health" span={6}>
            <DataHealthPanel />
          </BentoPanel>

          <BentoPanel title="Snapshot diagnostics" span={6}>
            {predictionTab === "past" ? (
              <div className="term-notice" role="note">
                Past replay diagnostics are tied to the selected replay event on the Dashboard.{" "}
                <Link to="/?tab=past" className="link-subtle">
                  Open Dashboard in Past mode
                </Link>
                .
              </div>
            ) : null}
            {predictionTab === "live" && !isLiveActive ? (
              <div className="term-notice" role="note">
                No live tournament is active. Switch to Upcoming on the Dashboard for pre-event diagnostics.
              </div>
            ) : null}
            <DiagnosticsGradingPanel
              metrics={diagnosticsModel.metrics}
              counters={diagnosticsModel.counters}
              reasonCodes={diagnosticsModel.reasonCodes}
              warnings={diagnosticsModel.warnings}
              selectedEventSummary={diagnosticsModel.selectedEventSummary}
            />
          </BentoPanel>
        </BentoGrid>

        <p className="px-5 pb-5 text-xs text-[var(--text-tertiary)]">
          Legacy route:{" "}
          <Link to="/research/diagnostics" className="link-subtle">
            /research/diagnostics
          </Link>
        </p>
      </main>
    </div>
  )
}
