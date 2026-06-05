import { Activity } from "lucide-react"
import { MonitoringShell } from "@/components/monitoring/monitoring-shell"
import { StatusDot } from "@/components/ui/status-dot"
import { cn } from "@/lib/utils"

/** @deprecated Use MonitoringShell — alias kept for tests and legacy imports. */
export function SuiteShell({
  children,
  headline,
  subheadline,
  modeSwitcher,
  frameStatus,
  actions,
}: {
  children: React.ReactNode
  headline: string
  subheadline?: string
  modeSwitcher?: React.ReactNode
  frameStatus?: React.ReactNode
  actions?: React.ReactNode
}) {
  return (
    <MonitoringShell
      headline={headline}
      subheadline={subheadline}
      laneSwitcher={modeSwitcher}
      frameStatus={frameStatus}
      actions={actions}
    >
      {children}
    </MonitoringShell>
  )
}

export const CommandShell = SuiteShell

/* ── Surface card ─────────────────────────────── */
export function SurfaceCard({
  children,
  className,
  title,
  description,
  action,
}: {
  children: React.ReactNode
  className?: string
  title?: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className={cn("card", className)}>
      {(title || action) && (
        <div className="card-header">
          <div>
            {title && <div className="card-title">{title}</div>}
            {description && <div className="card-desc">{description}</div>}
          </div>
          {action}
        </div>
      )}
      <div className="card-body">{children}</div>
    </div>
  )
}

/* ── Metric tile ───────────────────────────────── */
export function MetricTile({
  label,
  value,
  detail,
  tone = "default",
  title,
}: {
  label: string
  value: string
  detail?: string
  tone?: "default" | "positive" | "warning"
  title?: string
}) {
  const colorClass =
    tone === "positive" ? "green" : tone === "warning" ? "gold" : "neutral"

  return (
    <div
      className={cn("kpi-tile", colorClass)}
      data-testid="metric-tile"
      title={title}
      style={title ? { cursor: "help" } : undefined}
    >
      <div className="kpi-label">{label}</div>
      <div className={cn("kpi-value", colorClass)}>{value}</div>
      {detail && <div className="kpi-detail">{detail}</div>}
    </div>
  )
}

/* ── Section title ─────────────────────────────── */
export function SectionTitle({
  title,
  description,
  action,
  titleId,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  titleId?: string
}) {
  return (
    <div className="section-header">
      <div>
        <div className="section-title" id={titleId}>
          {title}
        </div>
        {description && <div className="section-desc">{description}</div>}
      </div>
      {action}
    </div>
  )
}

/* ── Status pill ──────────────────────────────── */
export function StatusPill({
  tone,
  label,
  pulse = false,
}: {
  tone: "good" | "warn" | "bad" | "muted"
  label: string
  pulse?: boolean
}) {
  return (
    <span className={cn("status-pill", tone)} data-testid="status-pill">
      {pulse && <span className="pulse-dot" />}
      {label}
    </span>
  )
}

/* ── Sidebar runtime status widget ─────────────── */
export function SidebarStatus({
  runtimeStatus,
  freshnessLabel,
}: {
  runtimeStatus: { label: string; tone: "good" | "warn" | "bad" }
  freshnessLabel: string
}) {
  const dotTone =
    runtimeStatus.tone === "good" ? "good" : runtimeStatus.tone === "warn" ? "warn" : "bad"
  return (
    <div className="sidebar-status">
      <div className="sidebar-offline">
        <StatusDot tone={dotTone} />
        {runtimeStatus.label}
      </div>
      <div className="sidebar-freshness">
        <Activity size={9} aria-hidden />
        {freshnessLabel}
      </div>
    </div>
  )
}
