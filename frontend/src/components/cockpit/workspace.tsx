import type { ReactNode } from "react"

import { CockpitTabbedStack, type CockpitTabOption } from "@/components/cockpit/responsive-panels"
import { useViewportTier } from "@/hooks/use-viewport"
import { cn } from "@/lib/utils"

/* ── Three-column dashboard workspace — fixed grid, no drag handles.
    Center uses CockpitResizableStack (tabbed boards); left rail uses vertical tabs.
    @deprecated Product command centers use ModelCommandLayout (`frontend/src/components/product/`).
    Retained for unit tests and gradual migration only. */
export type CockpitWorkspaceLayout = "columns" | "stack"

/** @deprecated Use ModelCommandLayout for operator surfaces. */
export function CockpitWorkspace({
  leftRail,
  center,
  rightRail,
  className,
  layout = "columns",
  mobilePanels,
}: {
  leftRail: ReactNode
  center: ReactNode
  rightRail: ReactNode
  className?: string
  /** `stack`: single vertical scroll column (narrow viewports). */
  layout?: CockpitWorkspaceLayout
  /** Flat mobile tabs (Picks / Rankings / …) — avoids burying picks under filters. */
  mobilePanels?: CockpitTabOption[]
}) {
  const tier = useViewportTier()
  const useMobileTabs = layout === "stack" || tier === "mobile"

  if (useMobileTabs && mobilePanels && mobilePanels.length > 0) {
    return (
      <div className={cn("cockpit-mobile-workspace", className)} data-testid="cockpit-mobile-workspace">
        <CockpitTabbedStack
          tabs={mobilePanels}
          defaultTabId="picks"
          ariaLabel="Dashboard boards"
          className="cockpit-mobile-dashboard-tabs"
        />
      </div>
    )
  }

  if (useMobileTabs) {
    const tabs: CockpitTabOption[] = [
      { id: "picks", label: "Picks", content: center },
      { id: "rankings", label: "Rankings", content: center },
      { id: "intel", label: "Intel", content: leftRail },
      { id: "player", label: "Player", content: rightRail },
    ]
    return (
      <div className={cn("cockpit-mobile-workspace", className)} data-testid="cockpit-mobile-workspace">
        <CockpitTabbedStack tabs={tabs} defaultTabId="picks" ariaLabel="Dashboard sections" />
      </div>
    )
  }

  if (tier === "tablet") {
    return (
      <div className={cn("cockpit-tablet-workspace cockpit-grid-workspace", className)} data-testid="cockpit-tablet-workspace">
        <div className="cockpit-tablet-rail">{leftRail}</div>
        <div className="cockpit-grid-columns cockpit-grid-columns--tablet">
          <div className="cockpit-column-fill">{center}</div>
          <div className="cockpit-column-scroll">{rightRail}</div>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn("cockpit-grid-workspace cockpit-grid-columns cockpit-grid-columns--desktop", className)}
      data-testid="cockpit-desktop-workspace"
    >
      <div className="cockpit-column-stack">{leftRail}</div>
      <div className="cockpit-column-fill">{center}</div>
      <div className="cockpit-column-scroll">{rightRail}</div>
    </div>
  )
}

/* ── Workspace module card — fills its grid cell, body scrolls */
export function CockpitModule({
  title,
  description,
  action,
  children,
  emptyState,
  className,
  flex,
  tone = "default",
}: {
  title: string
  description?: string
  action?: ReactNode
  children?: ReactNode
  emptyState?: string
  className?: string
  flex?: number
  tone?: "default" | "accent" | "muted"
}) {
  return (
    <div
      className={cn(
        "cockpit-module",
        tone === "accent" && "cockpit-module--accent",
        tone === "muted" && "cockpit-module--muted",
        flex != null && `cockpit-module--flex-${flex}`,
        className,
      )}
    >
      <div className="cockpit-module-header">
        <div className="cockpit-module-header-main">
          <span className="cockpit-module-title">{title}</span>
          {description ? <span className="cockpit-module-desc">{description}</span> : null}
        </div>
        {action ? <div className="cockpit-module-header-action">{action}</div> : null}
      </div>
      <div className="cockpit-module-body">
        {children ??
          (emptyState ? (
            <div className="empty-state">
              <div className="empty-state-title">{emptyState}</div>
            </div>
          ) : null)}
      </div>
    </div>
  )
}

/* ── Live / Upcoming / Past mode switcher */
export function CockpitModeSwitch({
  value,
  onChange,
  liveActive,
}: {
  value: "live" | "upcoming" | "past"
  onChange: (value: "live" | "upcoming" | "past") => void
  liveActive?: boolean
}) {
  const options: Array<{ value: "live" | "upcoming" | "past"; label: string }> = [
    { value: "live", label: "Live" },
    { value: "upcoming", label: "Upcoming" },
    { value: "past", label: "Past" },
  ]

  return (
    <div className="mode-switcher" role="radiogroup" aria-label="Event mode">
      {options.map((opt, idx) => {
        const active = opt.value === value
        const isLive = opt.value === "live"
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-posinset={idx + 1}
            aria-setsize={options.length}
            onClick={() => onChange(opt.value)}
            className={cn("mode-tab", active && "active")}
            data-testid={`mode-btn-${opt.value}`}
          >
            {isLive && liveActive && (
              <span className="mode-live-dot" aria-hidden="true" />
            )}
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
