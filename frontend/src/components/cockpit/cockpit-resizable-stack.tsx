import type { ReactNode } from "react"

import { CockpitTabbedStack, type CockpitTabOption } from "@/components/cockpit/responsive-panels"

type CockpitBoardStackProps = {
  rankings: ReactNode
  topPicks: ReactNode
  secondary: ReactNode
  leaderboard?: ReactNode
  /** Live / past: show leaderboard panel. Upcoming: omit fourth panel. */
  showLeaderboard: boolean
  /** Narrow viewports: vertical scroll stack instead of tabs. */
  layout?: "panels" | "stack"
  /** When set with compact layout, render only one pane (used by mobile dashboard tabs). */
  compactView?: "picks" | "rankings" | "secondary" | "leaderboard"
}

/** Tabbed center column — deterministic board switching (no drag handles). */
export function CockpitResizableStack({
  rankings,
  topPicks,
  secondary,
  leaderboard,
  showLeaderboard,
  layout = "panels",
  compactView,
}: CockpitBoardStackProps) {
  const tabs: CockpitTabOption[] = [
    { id: "picks", label: "Top picks", content: topPicks },
    { id: "rankings", label: "Rankings", content: rankings },
    { id: "markets", label: "Markets", content: secondary },
  ]
  if (showLeaderboard && leaderboard != null) {
    tabs.push({ id: "board", label: "Leaderboard", content: leaderboard })
  }

  if (compactView) {
    const panel =
      compactView === "picks"
        ? topPicks
        : compactView === "rankings"
          ? rankings
          : compactView === "secondary"
            ? secondary
            : leaderboard
    if (compactView === "leaderboard" && (!showLeaderboard || leaderboard == null)) {
      return (
        <div className="cockpit-mobile-panel-scroll">
          <div className="empty-state" style={{ padding: 24 }}>
            <div className="empty-state-title">Leaderboard appears when the event is live or in replay.</div>
          </div>
        </div>
      )
    }
    return <div className="cockpit-mobile-panel-scroll">{panel}</div>
  }

  if (layout === "stack") {
    return (
      <div className="cockpit-stack-scroll">
        {topPicks}
        {rankings}
        {secondary}
        {showLeaderboard && leaderboard != null ? leaderboard : null}
      </div>
    )
  }

  return (
    <CockpitTabbedStack
      className="cockpit-center-tabbed-stack"
      tabs={tabs}
      defaultTabId="picks"
      ariaLabel="Dashboard boards"
    />
  )
}
