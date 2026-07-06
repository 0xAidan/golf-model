import type { ReactNode } from "react"

import { CockpitTabbedStack, type CockpitTabOption } from "@/components/cockpit/responsive-panels"

type CockpitBoardStackProps = {
  rankings: ReactNode
  topPicks: ReactNode
  secondary: ReactNode
  leaderboard?: ReactNode
  fullPicks?: ReactNode
  fullPicksTabLabel?: string
  hideTopPicksTab?: boolean
  /** Live / past: show leaderboard panel. Upcoming: omit fourth panel. */
  showLeaderboard: boolean
  /** Narrow viewports: vertical scroll stack instead of tabs. */
  layout?: "panels" | "stack"
  /** When set with compact layout, render only one pane (used by mobile dashboard tabs). */
  compactView?: "picks" | "rankings" | "secondary" | "leaderboard" | "full-picks"
  /** Deep-link support e.g. ?tab=full-picks */
  defaultTabId?: string
}

/** Tabbed center column — deterministic board switching (no drag handles). */
export function CockpitResizableStack({
  rankings,
  topPicks,
  secondary,
  leaderboard,
  fullPicks,
  fullPicksTabLabel = "Full picks",
  hideTopPicksTab = false,
  showLeaderboard,
  layout = "panels",
  compactView,
  defaultTabId,
}: CockpitBoardStackProps) {
  const tabs: CockpitTabOption[] = hideTopPicksTab
    ? [
        { id: "rankings", label: "Rankings", content: rankings },
        { id: "markets", label: "Markets", content: secondary },
      ]
    : [
        { id: "picks", label: "Top picks", content: topPicks },
        { id: "rankings", label: "Rankings", content: rankings },
        { id: "markets", label: "Markets", content: secondary },
      ]
  if (showLeaderboard && leaderboard != null) {
    tabs.push({ id: "board", label: "Leaderboard", content: leaderboard })
  }
  if (fullPicks != null) {
    tabs.push({ id: "full-picks", label: fullPicksTabLabel, content: fullPicks })
  }

  if (compactView) {
    const panel =
      compactView === "picks"
        ? topPicks
        : compactView === "rankings"
          ? rankings
          : compactView === "secondary"
            ? secondary
            : compactView === "full-picks"
              ? fullPicks
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
    if (compactView === "full-picks" && fullPicks == null) {
      return (
        <div className="cockpit-mobile-panel-scroll">
          <div className="empty-state" style={{ padding: 24 }}>
            <div className="empty-state-title">Full picks load when event data is available.</div>
          </div>
        </div>
      )
    }
    return <div className="cockpit-mobile-panel-scroll">{panel}</div>
  }

  if (layout === "stack") {
    return (
      <div className="cockpit-stack-scroll">
        {!hideTopPicksTab ? topPicks : null}
        {rankings}
        {secondary}
        {showLeaderboard && leaderboard != null ? leaderboard : null}
        {fullPicks != null ? fullPicks : null}
      </div>
    )
  }

  return (
    <CockpitTabbedStack
      className="cockpit-center-tabbed-stack"
      tabs={tabs}
      defaultTabId={defaultTabId ?? (hideTopPicksTab ? "rankings" : "picks")}
      ariaLabel="Dashboard boards"
    />
  )
}
