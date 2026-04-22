import { NavLink } from "react-router-dom"
import {
  Activity,
  FlaskConical,
  GraduationCap,
  LayoutDashboard,
  Route,
  Swords,
  Trophy,
  Users,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { WorkspaceId } from "@/lib/types"

type NavItem = {
  id: WorkspaceId
  label: string
  href: string
  icon: React.ElementType
}

const NAV_ITEMS: NavItem[] = [
  { id: "prediction",   label: "Cockpit",      href: "/",            icon: LayoutDashboard },
  { id: "players",      label: "Players",      href: "/players",     icon: Users },
  { id: "matchups",     label: "Matchups",     href: "/matchups",    icon: Swords },
  { id: "course",       label: "Course",       href: "/course",      icon: Route },
  { id: "grading",      label: "Grading",      href: "/grading",     icon: GraduationCap },
  { id: "track-record", label: "Track Record", href: "/track-record",icon: Trophy },
  { id: "champion-challenger", label: "Champ/Chlgr", href: "/research/champion-challenger", icon: FlaskConical },
]

/* ── Logo SVG mark ────────────────────────────── */
function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      className="sidebar-logo-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-label="Golf Model"
    >
      {/* Flag pole */}
      <line x1="11" y1="6" x2="11" y2="26" stroke="#22C55E" strokeWidth="2" strokeLinecap="round" />
      {/* Flag */}
      <path d="M11 6 L24 11 L11 16 Z" fill="#22C55E" opacity="0.9" />
      {/* Ground arc */}
      <path d="M5 26 Q16 22 27 26" stroke="#22C55E" strokeWidth="1.5" strokeLinecap="round" opacity="0.45" />
      {/* Ball */}
      <circle cx="20" cy="25" r="2.5" fill="#F59E0B" />
    </svg>
  )
}

/* ── Shell ────────────────────────────────────── */
export function SuiteShell({
  children,
  headline,
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
    <div className="app-layout">
      {/* ── Sidebar */}
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar-logo">
          <LogoMark size={32} />
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-name">Golf Model</span>
            <span className="sidebar-logo-sub">Analytics</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav" aria-label="Main navigation">
          <div className="sidebar-section-label">Workspace</div>
          {NAV_ITEMS.slice(0, 4).map(({ href, icon: Icon, label, id }) => (
            <NavLink
              key={href}
              to={href}
              end={href === "/"}
              className={({ isActive }) =>
                cn("nav-item", isActive && "active")
              }
              data-testid={`nav-${id}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}

          <div className="sidebar-section-label" style={{ marginTop: 8 }}>Records</div>
          {NAV_ITEMS.slice(4, 6).map(({ href, icon: Icon, label, id }) => (
            <NavLink
              key={href}
              to={href}
              end={href === "/"}
              className={({ isActive }) =>
                cn("nav-item", isActive && "active")
              }
              data-testid={`nav-${id}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}

          <div className="sidebar-section-label" style={{ marginTop: 8 }}>Research</div>
          {NAV_ITEMS.slice(6).map(({ href, icon: Icon, label, id }) => (
            <NavLink
              key={href}
              to={href}
              end={href === "/"}
              className={({ isActive }) =>
                cn("nav-item", isActive && "active")
              }
              data-testid={`nav-${id}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Bottom status */}
        <div className="sidebar-bottom">
          {frameStatus}
        </div>
      </aside>

      {/* ── Main area */}
      <div className="main-area">
        {/* Top header */}
        <header className="top-header">
          <div className="header-event">
            <div className="header-event-label">Active event</div>
            <div className="header-event-name" data-testid="header-event-name">
              {headline || "No event loaded"}
            </div>
          </div>

          {modeSwitcher && (
            <div style={{ flexShrink: 0 }}>{modeSwitcher}</div>
          )}

          {actions && (
            <div className="header-actions">{actions}</div>
          )}
        </header>

        {/* Content area — fills remaining height, children control scroll */}
        <main className="content-scroll" style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
          {children}
        </main>
      </div>
    </div>
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
}: {
  label: string
  value: string
  detail?: string
  tone?: "default" | "positive" | "warning"
}) {
  const colorClass =
    tone === "positive" ? "green" : tone === "warning" ? "gold" : "neutral"

  return (
    <div className={cn("kpi-tile", colorClass)} data-testid="metric-tile">
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
}: {
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="section-header">
      <div>
        <div className="section-title">{title}</div>
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
  const dotColor =
    runtimeStatus.tone === "good" ? "good" : runtimeStatus.tone === "warn" ? "warn" : "bad"
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div className="sidebar-offline">
        <span className={`sidebar-offline-dot ${dotColor}`} />
        {runtimeStatus.label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-faint)", letterSpacing: "0.06em" }}>
        <Activity size={9} />
        {freshnessLabel}
      </div>
    </div>
  )
}
