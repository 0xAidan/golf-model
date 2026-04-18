import { Activity, Columns3, PanelLeftClose, PanelRightClose } from "lucide-react"

import { cn } from "@/lib/utils"

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
    <div className={cn("grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)_360px]", className)}>
      <div className="space-y-4">
        <CockpitZoneLabel icon={PanelLeftClose} label="Left area" description="Switchboard, context, and feed." />
        {leftRail}
      </div>
      <div className="space-y-4">
        <CockpitZoneLabel icon={Columns3} label="Center modules" description="Primary event story and analytical modules." />
        {center}
      </div>
      <div className="space-y-4">
        <CockpitZoneLabel icon={PanelRightClose} label="Right rail" description="Player spotlight and supporting context." />
        {rightRail}
      </div>
    </div>
  )
}

export function CockpitModule({
  title,
  description,
  action,
  children,
  emptyState,
  className,
  tone = "default",
}: {
  title: string
  description?: string
  action?: React.ReactNode
  children?: React.ReactNode
  emptyState?: string
  className?: string
  tone?: "default" | "accent" | "muted"
}) {
  const toneClass =
    tone === "accent"
      ? "border-cyan-400/20 bg-cyan-400/[0.08]"
      : tone === "muted"
        ? "border-white/8 bg-black/20"
        : "border-white/10 bg-white/[0.04]"

  return (
    <section className={cn("rounded-[24px] border p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]", toneClass, className)}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          {description ? <p className="mt-1 text-sm leading-6 text-slate-400">{description}</p> : null}
        </div>
        {action}
      </div>
      <div className="mt-4">
        {children ? (
          children
        ) : emptyState ? (
          <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-slate-400">
            {emptyState}
          </div>
        ) : null}
      </div>
    </section>
  )
}

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
    <div className="rounded-full border border-white/10 bg-black/25 p-1.5 backdrop-blur" role="tablist" aria-label="Event mode switch">
      <div className="flex items-center gap-1">
        {options.map((option) => {
          const active = option.value === value
          return (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onChange(option.value)}
              className={cn(
                "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition",
                active
                  ? "bg-cyan-400/15 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-100",
              )}
            >
              {option.value === "live" && liveActive ? (
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
              ) : null}
              <span>{option.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function CockpitZoneLabel({
  icon: Icon,
  label,
  description,
}: {
  icon: typeof Activity
  label: string
  description: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="rounded-xl bg-white/6 p-2 text-cyan-200">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
        <p className="text-sm text-slate-300">{description}</p>
      </div>
    </div>
  )
}
