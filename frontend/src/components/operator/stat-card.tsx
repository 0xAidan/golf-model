import type { ReactNode } from "react"

type StatTone = "neutral" | "positive" | "warning"

const valueTone: Record<StatTone, string> = {
  neutral: "text-white",
  positive: "text-[var(--op-accent)]",
  warning: "text-[var(--op-warning)]",
}

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
}: {
  label: string
  value: string
  hint?: string
  tone?: StatTone
  icon?: ReactNode
}) {
  return (
    <div className="op-card op-card-hover flex flex-col gap-3 px-4 py-4">
      <div className="flex items-center justify-between">
        <span className="op-eyebrow">{label}</span>
        {icon ? <span className="text-[var(--op-text-tertiary)]">{icon}</span> : null}
      </div>
      <span className={`op-num text-[26px] font-semibold leading-none tracking-tight ${valueTone[tone]}`}>{value}</span>
      {hint ? <span className="text-xs text-[var(--op-text-tertiary)]">{hint}</span> : null}
    </div>
  )
}
