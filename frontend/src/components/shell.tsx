import { useCallback, useEffect, useState } from "react"
import { NavLink, useLocation } from "react-router-dom"
import {
  Activity,
  Beaker,
  FlaskConical,
  GraduationCap,
  History,
  LayoutDashboard,
  ListChecks,
  Menu,
  Swords,
  Trophy,
  Users,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useIsNarrowViewport } from "@/hooks/use-media-query"
import type { WorkspaceId } from "@/lib/types"

type NavItem = {
  id: WorkspaceId | "lab-picks"
  label: string
  href: string
  icon: React.ElementType
  /** Primary routes get bottom nav on mobile. */
  primary?: boolean
}

/** Lab board + Lab picks nav on unless build sets `VITE_COCKPIT_LAB=0` (legacy env name). */
const COCKPIT_LAB_ENABLED = import.meta.env.VITE_COCKPIT_LAB !== "0"

const PRIMARY_NAV: NavItem[] = [
  { id: "prediction", label: "Dashboard", href: "/", icon: LayoutDashboard, primary: true },
  { id: "matchups", label: "Picks", href: "/matchups", icon: Swords, primary: true },
  ...(COCKPIT_LAB_ENABLED
    ? ([
        { id: "lab-board", label: "Lab", href: "/lab", icon: Beaker, primary: true },
        { id: "lab-picks", label: "Lab picks", href: "/lab/picks", icon: ListChecks, primary: true },
      ] as NavItem[])
    : []),
  { id: "players", label: "Players", href: "/players", icon: Users, primary: true },
]

const RECORDS_NAV: NavItem[] = [
  { id: "grading", label: "Grading", href: "/grading", icon: GraduationCap },
  { id: "track-record", label: "Track Record", href: "/track-record", icon: Trophy },
]

const RESEARCH_NAV: NavItem[] = [
  { id: "legacy-model", label: "Legacy Model", href: "/research/legacy-model", icon: History },
  { id: "champion-challenger", label: "Champ/Chlgr", href: "/research/champion-challenger", icon: FlaskConical },
  { id: "diagnostics", label: "Diagnostics", href: "/research/diagnostics", icon: Activity },
]

function NavItemLink({ href, icon: Icon, label, id }: NavItem) {
  return (
    <NavLink
      to={href}
      end={href === "/"}
      className={({ isActive }) => cn("nav-item", isActive && "active")}
      data-testid={
        id === "lab-board"
          ? "nav-lab-board"
          : id === "lab-picks"
            ? "nav-lab-picks"
            : `nav-${id}`
      }
    >
      <Icon size={15} />
      <span>{label}</span>
    </NavLink>
  )
}

function MobileBottomNav() {
  const location = useLocation()
  const primary = PRIMARY_NAV

  return (
    <nav className="mobile-bottom-nav" aria-label="Primary navigation">
      {primary.map(({ href, icon: Icon, label, id }) => {
        const active =
          href === "/"
            ? location.pathname === "/"
            : location.pathname === href || location.pathname.startsWith(`${href}/`)
        return (
          <NavLink
            key={href}
            to={href}
            end={href === "/"}
            className={cn("mobile-bottom-nav-item", active && "active")}
            data-testid={
              id === "lab-board"
                ? "nav-lab-board-mobile"
                : id === "lab-picks"
                  ? "nav-lab-picks-mobile"
                  : `nav-${id}-mobile`
            }
            aria-current={active ? "page" : undefined}
          >
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}

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
      <line x1="11" y1="6" x2="11" y2="26" stroke="#22C55E" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 6 L24 11 L11 16 Z" fill="#22C55E" opacity="0.9" />
      <path d="M5 26 Q16 22 27 26" stroke="#22C55E" strokeWidth="1.5" strokeLinecap="round" opacity="0.45" />
      <circle cx="20" cy="25" r="2.5" fill="#E8ECEF" stroke="#4A5660" strokeWidth="0.4" />
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
  const isNarrow = useIsNarrowViewport()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()

  const handleCloseMobileNav = useCallback(() => {
    setMobileNavOpen(false)
  }, [])

  useEffect(() => {
    if (!isNarrow) setMobileNavOpen(false)
  }, [isNarrow])

  useEffect(() => {
    handleCloseMobileNav()
  }, [location.pathname, handleCloseMobileNav])

  useEffect(() => {
    if (!mobileNavOpen || !isNarrow) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleCloseMobileNav()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [mobileNavOpen, isNarrow, handleCloseMobileNav])

  return (
    <div className={cn("app-layout", isNarrow && "app-layout--narrow")}>
      {isNarrow && mobileNavOpen ? (
        <button
          type="button"
          className="mobile-nav-backdrop"
          aria-label="Close navigation menu"
          onClick={handleCloseMobileNav}
        />
      ) : null}

      {/* ── Sidebar */}
      <aside
        className={cn(
          "sidebar",
          isNarrow && "sidebar--mobile-drawer",
          isNarrow && mobileNavOpen && "sidebar--mobile-drawer-open",
        )}
      >
        {/* Logo */}
        <div className="sidebar-logo">
          <LogoMark size={32} />
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-name">Golf Model</span>
            <span className="sidebar-logo-sub">Analytics</span>
          </div>
        </div>

        {/* Navigation */}
        <div className="sidebar-mobile-header">
          <span className="sidebar-mobile-header-title">Menu</span>
          <button
            type="button"
            className="sidebar-mobile-close"
            onClick={handleCloseMobileNav}
            aria-label="Close menu"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <nav
          id="suite-sidebar-nav"
          className="sidebar-nav"
          aria-label="Main navigation"
          onClick={(e) => {
            if (!isNarrow) return
            const target = e.target as HTMLElement
            if (target.closest("a[href]")) handleCloseMobileNav()
          }}
        >
          <div className="sidebar-section-label">Workspace</div>
          {PRIMARY_NAV.map((item) => (
            <NavItemLink key={item.href} {...item} />
          ))}

          <div className="sidebar-section-label" style={{ marginTop: 8 }}>
            Records
          </div>
          {RECORDS_NAV.map((item) => (
            <NavItemLink key={item.href} {...item} />
          ))}

          <div className="sidebar-section-label" style={{ marginTop: 8 }}>
            Research
          </div>
          {RESEARCH_NAV.map((item) => (
            <NavItemLink key={item.href} {...item} />
          ))}
        </nav>

        <div className="sidebar-bottom">{frameStatus}</div>
      </aside>

      <div className="main-area">
        <header className="top-header">
          {isNarrow ? (
            <button
              type="button"
              className="mobile-menu-trigger"
              onClick={() => setMobileNavOpen(true)}
              aria-expanded={mobileNavOpen}
              aria-controls="suite-sidebar-nav"
              data-testid="mobile-menu-open"
            >
              <Menu size={18} aria-hidden />
              <span className="mobile-menu-trigger-label">Menu</span>
            </button>
          ) : null}

          <div className="header-event">
            <div className="header-event-label">Active event</div>
            <div className="header-event-name" data-testid="header-event-name">
              {headline || "No event loaded"}
            </div>
          </div>

          {modeSwitcher && (
            <div className="header-mode-switcher">{modeSwitcher}</div>
          )}

          {actions && <div className="header-actions">{actions}</div>}
        </header>

        <main className="content-scroll">{children}</main>
      </div>

      <MobileBottomNav />
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
  const dotColor =
    runtimeStatus.tone === "good" ? "good" : runtimeStatus.tone === "warn" ? "warn" : "bad"
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div className="sidebar-offline">
        <span className={`sidebar-offline-dot ${dotColor}`} />
        {runtimeStatus.label}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          color: "var(--text-faint)",
          letterSpacing: "0.06em",
        }}
      >
        <Activity size={9} />
        {freshnessLabel}
      </div>
    </div>
  )
}
