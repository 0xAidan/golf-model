import { useCallback, useState } from "react"
import { Link } from "react-router-dom"

import { LabResearchInstrumentationPanel } from "@/components/cockpit/lab-research-instrumentation-panel"
import {
  persistLabResearchInstrumentationExpanded,
  readLabResearchInstrumentationExpanded,
} from "@/lib/lab-research-instrumentation-storage"
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
  const [researchExpanded, setResearchExpanded] = useState(readLabResearchInstrumentationExpanded)

  const handleResearchExpandedChange = useCallback((open: boolean) => {
    setResearchExpanded(open)
    persistLabResearchInstrumentationExpanded(open)
  }, [])

  return (
    <div className="cockpit-lab-root lane-lab">
      <div className="cockpit-lab-main">
        <div className="cockpit-lab-banner-wrap" data-testid="lab-board-banner-wrap">
          <div className="term-notice cockpit-lab-banner" data-testid="lab-board-banner">
            <strong>Lab</strong> — matchup-lab champion (Optuna trial 327) via{" "}
            <strong>lab_live_tournament</strong> / <strong>lab_upcoming_tournament</strong> when{" "}
            <code className="lab-code-inline">live_refresh.lab_profile_enabled</code> is on. Main{" "}
            <Link to="/" aria-label="Leave Lab: open main dashboard">
              Dashboard
            </Link>{" "}
            and{" "}
            <Link to="/matchups" aria-label="Leave Lab: open main picks (matchups)">
              Picks
            </Link>{" "}
            stay on the main snapshot only.
            Lab-only picks logging:{" "}
            <Link to="/lab/picks" aria-label="Open Lab picks within this workspace">
              Lab picks
            </Link>
          </div>
          {usingProdSnapshotFallback ? (
            <div
              className="term-notice amber cockpit-lab-banner"
              data-testid="lab-board-prod-fallback-banner"
            >
              <strong>Lab lane off.</strong> Boards below mirror the main snapshot until the server enables the lab
              profile and the next recompute fills <code className="lab-code-inline">lab_*</code> sections.
            </div>
          ) : null}
          {!usingProdSnapshotFallback && labLanePartialSections ? (
            <div
              className="term-notice amber cockpit-lab-banner"
              data-testid="lab-board-partial-sections-banner"
            >
              <strong>Partial lab snapshot.</strong> Only one of <code className="lab-code-inline">lab_live_tournament</code>{" "}
              / <code className="lab-code-inline">lab_upcoming_tournament</code> is populated — the missing side still uses
              the production board until both sections fill.
            </div>
          ) : null}
        </div>
        <div className="cockpit-lab-workspace">
          <PredictionWorkspacePage {...cockpitWorkspaceProps} />
        </div>
      </div>
      <aside
        className="cockpit-lab-research-aside"
        data-testid="lab-board-research-pane"
        data-research-scroll={researchExpanded ? "auto" : "visible"}
        data-research-expanded={researchExpanded ? "true" : "false"}
      >
        <div className="box-border h-full min-h-0 px-3 pb-3 pt-2">
          <LabResearchInstrumentationPanel
            expanded={researchExpanded}
            onExpandedChange={handleResearchExpandedChange}
            liveSnapshot={cockpitWorkspaceProps.liveSnapshot}
            predictionTab={cockpitWorkspaceProps.predictionTab}
          />
        </div>
      </aside>
    </div>
  )
}
