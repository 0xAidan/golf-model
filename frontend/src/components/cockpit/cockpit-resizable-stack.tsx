import type { ReactNode } from "react"
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels"

import { CockpitTabbedStack, type CockpitTabOption } from "@/components/cockpit/responsive-panels"
import { useViewportTier } from "@/hooks/use-viewport"

type CockpitResizableStackProps = {
  rankings: ReactNode
  topPicks: ReactNode
  secondary: ReactNode
  leaderboard?: ReactNode
  /** Live / past: show leaderboard panel. Upcoming: omit fourth panel. */
  showLeaderboard: boolean
  /** Narrow viewports: vertical scroll stack instead of draggable panes. */
  layout?: "panels" | "stack"
}

/* Vertical split panes for dashboard center column — sizes persist in localStorage per layout mode. */
export function CockpitResizableStack({
  rankings,
  topPicks,
  secondary,
  leaderboard,
  showLeaderboard,
  layout = "panels",
}: CockpitResizableStackProps) {
  const tier = useViewportTier()
  const persistKey = showLeaderboard
    ? "golf-model-cockpit-center-with-lb"
    : "golf-model-cockpit-center-upcoming"

  const tabs: CockpitTabOption[] = [
    { id: "picks", label: "Top picks", content: topPicks },
    { id: "rankings", label: "Rankings", content: rankings },
    { id: "markets", label: "Markets", content: secondary },
  ]
  if (showLeaderboard && leaderboard != null) {
    tabs.push({ id: "board", label: "Leaderboard", content: leaderboard })
  }

  const useCompact = layout === "stack" || tier === "mobile" || tier === "tablet"

  if (useCompact) {
    return (
      <CockpitTabbedStack
        className="cockpit-center-tabbed-stack"
        tabs={tabs}
        defaultTabId="picks"
        ariaLabel="Dashboard boards"
      />
    )
  }

  return (
    <PanelGroup
      autoSaveId={persistKey}
      direction="vertical"
      className="cockpit-vertical-panels"
    >
      <Panel defaultSize={showLeaderboard ? 38 : 42} minSize={10} className="cockpit-panel-shell">
        <div className="cockpit-panel-fill">{rankings}</div>
      </Panel>
      <PanelResizeHandle
        className="cockpit-resize-handle cockpit-resize-handle-row"
        aria-label="Resize power rankings and top picks"
      />
      <Panel defaultSize={showLeaderboard ? 32 : 38} minSize={10} className="cockpit-panel-shell">
        <div className="cockpit-panel-fill">{topPicks}</div>
      </Panel>
      <PanelResizeHandle
        className="cockpit-resize-handle cockpit-resize-handle-row"
        aria-label="Resize top picks and secondary markets"
      />
      <Panel defaultSize={showLeaderboard ? 18 : 20} minSize={8} className="cockpit-panel-shell">
        <div className="cockpit-panel-fill">{secondary}</div>
      </Panel>
      {showLeaderboard && leaderboard != null && (
        <>
          <PanelResizeHandle
            className="cockpit-resize-handle cockpit-resize-handle-row"
            aria-label="Resize secondary markets and leaderboard"
          />
          <Panel defaultSize={12} minSize={10} className="cockpit-panel-shell">
            <div className="cockpit-panel-fill">{leaderboard}</div>
          </Panel>
        </>
      )}
    </PanelGroup>
  )
}
