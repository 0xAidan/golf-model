import { Link } from "react-router-dom"

import { ResearchInstrumentationDeck } from "@/components/cockpit/research-instrumentation-deck"
import {
  PredictionWorkspacePage,
  type PredictionWorkspacePageProps,
} from "@/pages/prediction-workspace-page"

export function CockpitLabPage({
  cockpitWorkspaceProps,
  usingProdSnapshotFallback = false,
  labLanePartialSections = false,
}: {
  cockpitWorkspaceProps: PredictionWorkspacePageProps
  usingProdSnapshotFallback?: boolean
  /** True when only one of lab_live / lab_upcoming exists — merged view mixes lab + production. */
  labLanePartialSections?: boolean
}) {
  return (
    <div
      className="cockpit-lab-root"
      style={{
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      <div style={{ minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
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
            <strong>Cockpit (Lab)</strong> — sandbox boards read from <strong>lab_live_tournament</strong> /{" "}
            <strong>lab_upcoming_tournament</strong> when the server has{" "}
            <code style={{ fontSize: 11 }}>live_refresh.lab_profile_enabled</code> on. Production{" "}
            <Link to="/">Cockpit</Link> and <Link to="/matchups">Picks</Link> stay on the main snapshot only.
            Lab-only picks logging: <Link to="/lab/picks">Lab picks</Link>.
          </div>
          {usingProdSnapshotFallback ? (
            <div
              className="term-notice amber"
              style={{
                margin: "8px 12px 0",
                fontSize: 12,
                lineHeight: 1.45,
              }}
              data-testid="cockpit-lab-prod-fallback-banner"
            >
              <strong>Lab lane off.</strong> Boards below mirror the main snapshot until the server enables the lab
              profile and the next recompute fills <code style={{ fontSize: 11 }}>lab_*</code> sections.
            </div>
          ) : null}
          {!usingProdSnapshotFallback && labLanePartialSections ? (
            <div
              className="term-notice amber"
              style={{
                margin: "8px 12px 0",
                fontSize: 12,
                lineHeight: 1.45,
              }}
              data-testid="cockpit-lab-partial-sections-banner"
            >
              <strong>Partial lab snapshot.</strong> Only one of <code style={{ fontSize: 11 }}>lab_live_tournament</code>{" "}
              / <code style={{ fontSize: 11 }}>lab_upcoming_tournament</code> is populated — the missing side still uses
              the production board until both sections fill.
            </div>
          ) : null}
        </div>
        <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
          <PredictionWorkspacePage {...cockpitWorkspaceProps} />
        </div>
      </div>
      <aside
        className="cockpit-lab-research-aside"
        style={{
          minHeight: 0,
          overflowY: "auto",
          borderLeft: "1px solid var(--border)",
          background: "var(--surface-0)",
        }}
        data-testid="cockpit-lab-research-pane"
      >
        <ResearchInstrumentationDeck
          liveSnapshot={cockpitWorkspaceProps.liveSnapshot}
          predictionTab={cockpitWorkspaceProps.predictionTab}
        />
      </aside>
    </div>
  )
}
