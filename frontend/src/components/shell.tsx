import { NavLink } from "react-router-dom"
import { Activity, BarChart3, BookOpen, Gauge, GraduationCap, LayoutDashboard, Route, Swords, Users } from "lucide-react"

import { cn } from "@/lib/utils"
import type { WorkspaceId } from "@/lib/types"

type NavItem = {
  id: WorkspaceId
  label: string
  href: string
  icon: typeof LayoutDashboard
}

const NAV_ITEMS: NavItem[] = [
  { id: "prediction", label: "Prediction", href: "/", icon: LayoutDashboard },
  { id: "players", label: "Players", href: "/players", icon: Users },
  { id: "matchups", label: "Matchups", href: "/matchups", icon: Swords },
  { id: "course", label: "Course", href: "/course", icon: Route },
  { id: "grading", label: "Grading", href: "/grading", icon: GraduationCap },
  { id: "history", label: "History", href: "/history", icon: BarChart3 },
  { id: "research", label: "Research", href: "/research", icon: BookOpen },
]

export function CommandShell({
  children,
  headline,
  subheadline,
  actions,
}: {
  children: React.ReactNode
  headline: string
  subheadline: string
  actions?: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-transparent text-foreground">
      <div className="mx-auto grid min-h-screen max-w-[1680px] grid-cols-[280px_minmax(0,1fr)] gap-6 px-6 py-6">
        <aside className="rounded-[28px] border border-white/10 bg-white/5 p-5 shadow-[0_20px_80px_rgba(5,10,18,0.45)] backdrop-blur-xl">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-400/15 text-cyan-200">
              <Gauge className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-cyan-200/70">Golf Model</p>
              <h1 className="text-lg font-semibold text-white">Command Station</h1>
            </div>
          </div>
          <nav className="space-y-2">
            {NAV_ITEMS.map(({ href, icon: Icon, label }) => (
              <NavLink
                key={href}
                to={href}
                end={href === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition",
                    isActive
                      ? "bg-cyan-400/15 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-100",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-8 rounded-2xl border border-cyan-400/15 bg-cyan-400/8 p-4">
            <div className="mb-2 flex items-center gap-2 text-cyan-100">
              <Activity className="h-4 w-4" />
              <span className="text-sm font-semibold">Operator Mode</span>
            </div>
            <p className="text-sm leading-6 text-slate-300">
              Matchups stay front and center, but every player, course, and grading lane is one click away.
            </p>
          </div>
        </aside>
        <main className="min-w-0 rounded-[28px] border border-white/10 bg-slate-950/65 p-6 shadow-[0_28px_100px_rgba(0,0,0,0.35)] backdrop-blur-xl">
          <header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-white/10 pb-5">
            <div>
              <p className="mb-2 text-xs uppercase tracking-[0.24em] text-slate-400">Operator workspace</p>
              <h2 className="text-3xl font-semibold tracking-tight text-white">{headline}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{subheadline}</p>
            </div>
            {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
          </header>
          {children}
        </main>
      </div>
    </div>
  )
}

export function SurfaceCard({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn("rounded-[24px] border border-white/10 bg-white/4 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]", className)}>
      {children}
    </section>
  )
}

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
  const toneClass =
    tone === "positive"
      ? "text-emerald-300"
      : tone === "warning"
        ? "text-amber-200"
        : "text-white"

  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className={cn("mt-2 text-2xl font-semibold", toneClass)}>{value}</p>
      {detail ? <p className="mt-2 text-sm text-slate-400">{detail}</p> : null}
    </div>
  )
}

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
    <div className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        {description ? <p className="mt-1 text-sm text-slate-400">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}
