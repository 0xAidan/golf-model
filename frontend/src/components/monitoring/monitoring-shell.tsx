import { useCallback, useEffect, useState, type ElementType, type MouseEvent, type ReactNode } from "react"
import { NavLink, useLocation } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import {
  Activity,
  Beaker,
  FlaskConical,
  History,
  LayoutDashboard,
  Menu,
  Settings2,
  Trophy,
  Users,
  X,
} from "lucide-react"

import { RouteTransition } from "@/components/route-transition"
import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import { useIsNarrowViewport } from "@/hooks/use-media-query"
import { api } from "@/lib/api"
import type { WorkspaceId } from "@/lib/types"
import { cn } from "@/lib/utils"

type NavItem = {
  id: WorkspaceId | "lab-picks" | "diagnostics-legacy"
  label: string
  href: string
  icon: ElementType
  prefetch?: boolean
}

const COCKPIT_LAB_ENABLED = import.meta.env.VITE_COCKPIT_LAB !== "0"

const PRIMARY_NAV: NavItem[] = [
  { id: "prediction", label: "Dashboard", href: "/", icon: LayoutDashboard, prefetch: true },
  ...(COCKPIT_LAB_ENABLED
    ? ([{ id: "lab-board", label: "Lab", href: "/lab", icon: Beaker, prefetch: true }] as NavItem[])
    : []),
  { id: "players", label: "Players", href: "/players", icon: Users, prefetch: true },
  { id: "grading", label: "Results", href: "/results", icon: Trophy, prefetch: true },
  { id: "diagnostics", label: "System", href: "/system", icon: Settings2 },
]

const RESEARCH_NAV: NavItem[] = [
  { id: "legacy-model", label: "Legacy Model", href: "/research/legacy-model", icon: History },
  { id: "champion-challenger", label: "Champ/Chlgr", href: "/research/champion-challenger", icon: FlaskConical },
  { id: "diagnostics-legacy", label: "Diagnostics (legacy)", href: "/research/diagnostics", icon: Activity },
]

function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      className="sidebar-logo-mark"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-label="Golf Model"
    >
      <line x1="11" y1="6" x2="11" y2="26" stroke="var(--logo-accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M11 6 L24 11 L11 16 Z" fill="var(--logo-accent)" opacity="0.9" />
      <path d="M5 26 Q16 22 27 26" stroke="var(--logo-accent)" strokeWidth="1.5" strokeLinecap="round" opacity="0.45" />
      <circle cx="20" cy="25" r="2.5" fill="var(--logo-ball)" stroke="var(--logo-ball-stroke)" strokeWidth="0.4" />
    </svg>
  )
}

function navTestId(id: NavItem["id"]) {
  if (id === "lab-board") return "nav-lab-board"
  if (id === "diagnostics-legacy") return "nav-diagnostics"
  return `nav-${id}`
}

function NavItemLink({
  href,
  icon: Icon,
  label,
  id,
  onPrefetch,
}: NavItem & { onPrefetch?: (href: string) => void }) {
  const handleMouseEnter = useCallback(() => {
    onPrefetch?.(href)
  }, [href, onPrefetch])

  return (
    <NavLink
      to={href}
      end={href === "/"}
      className={({ isActive }) => cn("nav-item", isActive && "active")}
      data-testid={navTestId(id)}
      data-cursor
      data-cursor-accent="link"
      onMouseEnter={handleMouseEnter}
      onFocus={handleMouseEnter}
    >
      <Icon size={15} aria-hidden />
      <span>{label}</span>
    </NavLink>
  )
}

function MonitoringDrawerNav({
  onNavigate,
  onPrefetch,
}: {
  onNavigate?: (event: React.MouseEvent<HTMLElement>) => void
  onPrefetch: (href: string) => void
}) {
  return (
    <nav className="monitoring-shell-nav" onClick={onNavigate}>
      <div className="monitoring-shell-nav__brand">
        <LogoMark />
        <div className="sidebar-logo-text">
          <span className="sidebar-logo-name">Golf Model</span>
          <span className="sidebar-logo-sub">Golf Model</span>
        </div>
      </div>

      <div className="sidebar-section-label">Product</div>
      {PRIMARY_NAV.map((item) => (
        <NavItemLink key={item.href} {...item} onPrefetch={onPrefetch} />
      ))}

      <div className="sidebar-section-label sidebar-section-label--spaced">Research</div>
      {RESEARCH_NAV.map((item) => (
        <NavItemLink key={item.href} {...item} onPrefetch={onPrefetch} />
      ))}
    </nav>
  )
}

export type MonitoringShellProps = {
  children: ReactNode
  headline: string
  subheadline?: string
  laneSwitcher?: ReactNode
  frameStatus?: ReactNode
  actions?: ReactNode
  className?: string
  testId?: string
}

export function MonitoringShell({
  children,
  headline,
  subheadline,
  laneSwitcher,
  frameStatus,
  actions,
  className,
  testId = "monitoring-shell",
}: MonitoringShellProps) {
  const isNarrow = useIsNarrowViewport()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  const queryClient = useQueryClient()

  const handleCloseDrawer = useCallback(() => setDrawerOpen(false), [])
  const handleToggleDrawer = useCallback(() => setDrawerOpen((open) => !open), [])

  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!drawerOpen || !isNarrow) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") handleCloseDrawer()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [drawerOpen, isNarrow, handleCloseDrawer])

  const handlePrefetch = useCallback(
    (href: string) => {
      if (href === "/" || href === "/lab" || href === "/players") {
        void queryClient.prefetchQuery({
          queryKey: ["live-refresh-snapshot"],
          queryFn: api.getLiveRefreshSnapshot,
          staleTime: 15_000,
        })
        void queryClient.prefetchQuery({
          queryKey: ["dashboard-state"],
          queryFn: api.getDashboardState,
          staleTime: 15_000,
        })
      }
      if (href === "/lab") {
        void import("@/pages/cockpit-lab-page")
      }
      if (href === "/players") {
        void import("@/pages/players-page")
      }
    },
    [queryClient],
  )

  const handleDrawerNavigate = useCallback(
    (event: MouseEvent<HTMLElement>) => {
      if (!isNarrow) return
      const target = event.target as HTMLElement
      if (target.closest("a[href]")) handleCloseDrawer()
    },
    [isNarrow, handleCloseDrawer],
  )

  return (
    <div className={cn("monitoring-shell", className)} data-testid={testId}>
      <header className="monitoring-shell-header" data-testid={`${testId}-header`}>
        <div className="monitoring-shell-header__row">
          <div className="monitoring-shell-header__start">
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className="md:hidden"
              aria-label={drawerOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={drawerOpen}
              onClick={handleToggleDrawer}
              data-testid="mobile-menu-open"
            >
              {drawerOpen ? <X size={18} /> : <Menu size={18} />}
            </Button>

            <div className="header-event">
              <div className="header-event-name" data-testid="header-event-name">
                {headline || "No event loaded"}
              </div>
              {subheadline ? (
                <span className="header-event-meta" data-testid="header-event-meta">
                  {subheadline}
                </span>
              ) : null}
            </div>
          </div>

          {laneSwitcher ? (
            <div className="monitoring-shell-lane-switcher header-mode-switcher">{laneSwitcher}</div>
          ) : null}

          <div className="header-actions">
            <ThemeToggle />
            {actions}
          </div>
        </div>
      </header>

      <div className="monitoring-shell-body">
        <aside
          className={cn("monitoring-shell-drawer", !drawerOpen && isNarrow && "monitoring-shell-drawer--closed")}
          data-testid={`${testId}-drawer`}
          aria-label="Main navigation"
          aria-hidden={isNarrow && !drawerOpen ? true : undefined}
          {...(isNarrow && drawerOpen
            ? { role: "dialog", "aria-modal": true as const }
            : {})}
        >
          <MonitoringDrawerNav onNavigate={handleDrawerNavigate} onPrefetch={handlePrefetch} />
          {frameStatus ? <div className="monitoring-shell-drawer__status">{frameStatus}</div> : null}
        </aside>

        {drawerOpen && isNarrow ? (
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/40 md:hidden"
            aria-label="Close navigation overlay"
            onClick={handleCloseDrawer}
          />
        ) : null}

        <main className="monitoring-shell-main monitor-lane" data-testid={`${testId}-main`}>
          <RouteTransition>{children}</RouteTransition>
        </main>
      </div>
    </div>
  )
}
