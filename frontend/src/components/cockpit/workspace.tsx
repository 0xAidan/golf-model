import { cn } from "@/lib/utils"

/* ── Three-column cockpit — fills viewport height, columns scroll internally */
export function CockpitWorkspace({
  leftRail,
  center,
  rightRail,
  className,
}: {
  leftRail: React.ReactNode
  center: React.ReactNode
  rightRail: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(className)}
      style={{
        display: "grid",
        gridTemplateColumns: "256px minmax(0,1fr) 300px",
        gap: 4,
        padding: 6,
        flex: 1,
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      {/* Left column — scrolls internally */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minHeight: 0, overflow: "hidden" }}>
        {leftRail}
      </div>
      {/* Center column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minHeight: 0, overflow: "hidden" }}>
        {center}
      </div>
      {/* Right column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4, minHeight: 0, overflow: "hidden" }}>
        {rightRail}
      </div>
    </div>
  )
}

/* ── Cockpit module card — fills its grid cell, body scrolls */
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
  action?: React.ReactNode
  children?: React.ReactNode
  emptyState?: string
  className?: string
  flex?: number
  tone?: "default" | "accent" | "muted"
}) {
  return (
    <div
      className={cn("cockpit-module", className)}
      style={{
        flex: flex ?? 1,
        minHeight: 0,
        ...(tone === "accent"
          ? { borderColor: "rgba(34,197,94,0.2)" }
          : tone === "muted"
          ? { borderColor: "var(--border)" }
          : undefined),
      }}
    >
      <div className="cockpit-module-header">
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
          <span className="cockpit-module-title">{title}</span>
          {description && (
            <span style={{ fontSize: 9, color: "var(--text-faint)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {description}
            </span>
          )}
        </div>
        {action && <div style={{ flexShrink: 0 }}>{action}</div>}
      </div>
      <div className="cockpit-module-body">
        {children ?? (
          emptyState ? (
            <div className="empty-state">
              <div className="empty-state-title">{emptyState}</div>
            </div>
          ) : null
        )}
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
    { value: "live",     label: "Live" },
    { value: "upcoming", label: "Upcoming" },
    { value: "past",     label: "Past" },
  ]

  return (
    <div className="mode-switcher" role="tablist" aria-label="Event mode">
      {options.map((opt) => {
        const active = opt.value === value
        const isLive = opt.value === "live"
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={cn("mode-tab", active && "active")}
            data-testid={`mode-btn-${opt.value}`}
          >
            {isLive && liveActive && (
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: "50%",
                  background: "var(--green)",
                  display: "inline-block",
                  flexShrink: 0,
                  animation: "pulse-glow 1.8s ease-in-out infinite",
                }}
                aria-hidden="true"
              />
            )}
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
