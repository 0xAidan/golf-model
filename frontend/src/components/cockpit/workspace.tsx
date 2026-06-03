import type { ReactNode } from "react"
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels"

import { CockpitTabbedStack, type CockpitTabOption } from "@/components/cockpit/responsive-panels"
import { useViewportTier } from "@/hooks/use-viewport"
import { cn } from "@/lib/utils"

/* ── Three-column dashboard workspace — fills viewport height; columns resize via drag handles.
    Sizes persist in localStorage (autoSaveId). Center uses CockpitResizableStack for
    vertical splits; left rail may nest a vertical PanelGroup from the page. */
export type CockpitWorkspaceLayout = "columns" | "stack"

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
      <div className={cn("cockpit-tablet-workspace", className)} data-testid="cockpit-tablet-workspace">
        <div className="cockpit-tablet-rail">{leftRail}</div>
        <PanelGroup
          direction="horizontal"
          autoSaveId="golf-model-cockpit-columns-tablet"
          className="cockpit-horizontal-panels cockpit-tablet-columns"
        >
          <Panel defaultSize={62} minSize={40} className="cockpit-column-panel">
            <div className="cockpit-column-fill">{center}</div>
          </Panel>
          <PanelResizeHandle
            className="cockpit-resize-handle cockpit-resize-handle-col"
            aria-label="Resize center and player columns"
          />
          <Panel defaultSize={38} minSize={22} maxSize={52} className="cockpit-column-panel">
            <div className="cockpit-column-scroll">{rightRail}</div>
          </Panel>
        </PanelGroup>
      </div>
    )
  }

  return (
    <PanelGroup
      direction="horizontal"
      autoSaveId="golf-model-cockpit-columns"
      className={cn("cockpit-horizontal-panels", className)}
    >
      <Panel defaultSize={14} minSize={12} maxSize={40} className="cockpit-column-panel">
        <div className="cockpit-column-stack">{leftRail}</div>
      </Panel>
      <PanelResizeHandle
        className="cockpit-resize-handle cockpit-resize-handle-col"
        aria-label="Resize left and center columns"
      />
      <Panel defaultSize={62} minSize={36} className="cockpit-column-panel">
        <div className="cockpit-column-fill">{center}</div>
      </Panel>
      <PanelResizeHandle
        className="cockpit-resize-handle cockpit-resize-handle-col"
        aria-label="Resize center and right columns"
      />
      <Panel defaultSize={24} minSize={15} maxSize={48} className="cockpit-column-panel">
        <div className="cockpit-column-scroll">{rightRail}</div>
      </Panel>
    </PanelGroup>
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
