import { Link } from "react-router-dom"

import { ResearchInstrumentationDeck } from "@/components/cockpit/research-instrumentation-deck"
import {
  PredictionWorkspacePage,
  type PredictionWorkspacePageProps,
} from "@/pages/prediction-workspace-page"

export function CockpitLabPage({ cockpitWorkspaceProps }: { cockpitWorkspaceProps: PredictionWorkspacePageProps }) {
  return (
    <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ flexShrink: 0 }} data-testid="cockpit-lab-banner-wrap">
        <div
          className="term-notice"
          style={{
            margin: "8px 12px 0",
            fontSize: 12,
            lineHeight: 1.45,
          }}
          data-testid="cockpit-lab-banner"
        >
          <strong>Cockpit (Lab)</strong> — non-streak, read-only research view. Uses the same live snapshot
          subscription as production <strong>/</strong> and does not change staking, grading, or the main card
          pipeline. Production operators should keep using <Link to="/">Cockpit</Link> for the primary surface.
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        <PredictionWorkspacePage {...cockpitWorkspaceProps} />
        <ResearchInstrumentationDeck
          liveSnapshot={cockpitWorkspaceProps.liveSnapshot}
          predictionTab={cockpitWorkspaceProps.predictionTab}
        />
      </div>
    </div>
  )
}
