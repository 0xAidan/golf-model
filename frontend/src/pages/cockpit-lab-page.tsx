import { useCallback, useState } from "react"
import { Link } from "react-router-dom"

import { LabResearchInstrumentationPanel } from "@/components/cockpit/lab-research-instrumentation-panel"
import { ModelLaneBadge, TrustStatusBanner } from "@/components/product"
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
    <div className="cockpit-lab-root lane-lab" data-testid="lab-command-center">
      <div className="cockpit-lab-main">
        <div className="model-command-center pt-5 pb-0" data-testid="lab-board-banner-wrap">
          <div className="flex flex-wrap items-center gap-3 mb-3">
            <ModelLaneBadge lane="lab" />
            <p className="text-sm text-[var(--text-secondary)] max-w-3xl">
              Research model via <code className="lab-code-inline">lab_live_tournament</code> /{" "}
              <code className="lab-code-inline">lab_upcoming_tournament</code>.{" "}
              <Link to="/" className="link-subtle">
                Dashboard
              </Link>{" "}
              uses the production snapshot only.
            </p>
          </div>

          {usingProdSnapshotFallback ? (
            <TrustStatusBanner
              tone="warn"
              title="Lab lane off"
              message="Boards below mirror the main snapshot until the server enables the lab profile and the next recompute fills lab_* sections."
              testId="lab-board-prod-fallback-banner"
            />
          ) : null}
          {!usingProdSnapshotFallback && labLanePartialSections ? (
            <TrustStatusBanner
              tone="warn"
              title="Partial lab snapshot"
              message="Only one lab section is populated — the missing side still uses the production board until both sections fill."
              testId="lab-board-partial-sections-banner"
            />
          ) : null}

          <div
            className="term-notice cockpit-lab-banner"
            data-testid="lab-board-banner"
            role="status"
            aria-live="polite"
          >
            <strong>Lab</strong> — matchup-lab champion via{" "}
            <strong>lab_live_tournament</strong> / <strong>lab_upcoming_tournament</strong> when{" "}
            <code className="lab-code-inline">live_refresh.lab_profile_enabled</code> is on.
          </div>
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
