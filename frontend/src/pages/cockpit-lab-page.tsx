import { useCallback, useState } from "react"
import { Link } from "react-router-dom"

import { LabResearchInstrumentationPanel } from "@/components/cockpit/lab-research-instrumentation-panel"
import { ModelLaneBadge } from "@/components/product"
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

  const workspaceProps: PredictionWorkspacePageProps = {
    ...cockpitWorkspaceProps,
    usingProdSnapshotFallback,
    labLanePartialSections,
  }

  return (
    <div className="cockpit-lab-root lane-lab" data-testid="lab-command-center">
      <div className="cockpit-lab-lane-stripe" aria-hidden data-testid="lab-board-lane-stripe" />
      <div className="cockpit-lab-main">
        <div className="model-command-center pt-5 pb-0" data-testid="lab-board-banner-wrap">
          <div className="cockpit-lab-secondary-note mb-3">
            <ModelLaneBadge lane="lab" />
            <Link
              to="/eval"
              className="cockpit-lab-secondary-chip"
              data-testid="lab-board-secondary-chip"
            >
              Challenger - validation pending
            </Link>
            <p className="text-sm text-[var(--text-secondary)] max-w-3xl">
              Research model via <code className="lab-code-inline">lab_live_tournament</code> /{" "}
              <code className="lab-code-inline">lab_upcoming_tournament</code>.{" "}
              <Link to="/" className="link-subtle">
                Dashboard
              </Link>{" "}
              uses the production snapshot only.
            </p>
          </div>
        </div>

        <div className="cockpit-lab-workspace">
          <PredictionWorkspacePage {...workspaceProps} />
        </div>
        <section
          className="cockpit-lab-instrumentation"
          data-testid="lab-board-instrumentation-section"
          data-research-expanded={researchExpanded ? "true" : "false"}
        >
          <div className="box-border h-full min-h-0 px-3 pb-3 pt-2">
            <p className="mb-2 text-xs uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Secondary instrumentation
            </p>
            <LabResearchInstrumentationPanel
              expanded={researchExpanded}
              onExpandedChange={handleResearchExpandedChange}
              liveSnapshot={cockpitWorkspaceProps.liveSnapshot}
              predictionTab={cockpitWorkspaceProps.predictionTab}
            />
          </div>
        </section>
      </div>
    </div>
  )
}
