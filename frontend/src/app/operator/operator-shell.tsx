import type { ReactNode } from "react"
import { NavLink } from "react-router-dom"

type NavItem = {
  to: string
  label: string
  hint: string
  icon: ReactNode
  end?: boolean
}

const navItems: NavItem[] = [
  {
    to: "/preview",
    label: "Dashboard",
    hint: "Live board",
    end: true,
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true" className="h-[18px] w-[18px]">
        <path d="M3 13h7V3H3v10Zm0 8h7v-6H3v6Zm11 0h7V11h-7v10Zm0-18v6h7V3h-7Z" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    to: "/preview/lab",
    label: "Lab",
    hint: "Research",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true" className="h-[18px] w-[18px]">
        <path d="M9 3h6M10 3v6.5L5 18a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-8.5V3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
]

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "group flex items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm font-medium op-focus transition-colors",
    isActive
      ? "bg-[var(--op-surface-3)] text-white shadow-[inset_2px_0_0_0_var(--op-accent)]"
      : "text-[var(--op-text-secondary)] hover:bg-[var(--op-surface)] hover:text-white",
  ].join(" ")

function BrandMark() {
  return (
    <div className="flex items-center gap-3 px-1">
      <span className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-[var(--op-border-strong)] bg-gradient-to-b from-[#12321f] to-[#0b1a12] text-[var(--op-accent)]">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} aria-hidden="true" className="h-5 w-5">
          <path d="M12 3v13" strokeLinecap="round" />
          <path d="M12 4.5 18 7l-6 2.5V4.5Z" fill="currentColor" stroke="none" />
          <circle cx="12" cy="19.5" r="2.2" />
        </svg>
      </span>
      <div className="leading-tight">
        <p className="text-sm font-semibold tracking-tight text-white">Golf Model</p>
        <p className="op-eyebrow tracking-[0.14em]">Operator console</p>
      </div>
    </div>
  )
}

function SystemStatus() {
  return (
    <div className="op-card flex items-center gap-3 px-3 py-3">
      <span className="op-dot op-dot-live" aria-hidden="true" />
      <div className="leading-tight">
        <p className="text-[13px] font-semibold text-white">Model online</p>
        <p className="text-xs text-[var(--op-text-tertiary)]">Live pipeline healthy</p>
      </div>
    </div>
  )
}

export function OperatorShell({ children }: { children: ReactNode }) {
  return (
    <div className="operator-app flex min-h-screen">
      <aside
        className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col gap-6 border-r border-[var(--op-border)] bg-[var(--op-bg-elevated)]/70 px-4 py-5 backdrop-blur lg:flex"
        aria-label="Operator navigation"
      >
        <BrandMark />
        <nav className="flex flex-col gap-1" aria-label="Sections">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
              <span className="text-[var(--op-text-tertiary)] transition-colors group-hover:text-[var(--op-accent)]">{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              <span className="text-[11px] text-[var(--op-text-tertiary)]">{item.hint}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto">
          <SystemStatus />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <nav className="flex items-center gap-1 border-b border-[var(--op-border)] bg-[var(--op-bg-elevated)]/80 px-4 py-2 backdrop-blur lg:hidden" aria-label="Operator navigation">
          <span className="mr-2 text-sm font-semibold text-white">Golf Model</span>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium op-focus ${isActive ? "bg-[var(--op-surface-3)] text-white" : "text-[var(--op-text-secondary)]"}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="flex-1">{children}</main>
      </div>
    </div>
  )
}
