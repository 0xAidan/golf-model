import NumberFlow from "@number-flow/react"
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type MacroKpiItem = {
  id: string
  label: string
  value: number | string
  suffix?: string
  tone?: "neutral" | "positive" | "negative" | "warning"
  spark?: ReactNode
}

export type MacroKpiStripProps = {
  items: MacroKpiItem[]
  className?: string
  testId?: string
}

function MacroKpiValue({ value, suffix }: { value: number | string; suffix?: string }) {
  if (typeof value === "number") {
    return (
      <span className="monitoring-macro-kpi-value kpi-value num">
        <NumberFlow value={value} />
        {suffix ? <span className="text-[var(--text-xs)] text-[var(--text-tertiary)]">{suffix}</span> : null}
      </span>
    )
  }

  return (
    <span className="monitoring-macro-kpi-value kpi-value num">
      {value}
      {suffix ? <span className="text-[var(--text-xs)] text-[var(--text-tertiary)]"> {suffix}</span> : null}
    </span>
  )
}

const toneClass: Record<NonNullable<MacroKpiItem["tone"]>, string> = {
  neutral: "",
  positive: "text-[var(--positive)]",
  negative: "text-[var(--danger)]",
  warning: "text-[var(--warning)]",
}

export function MacroKpiStrip({ items, className, testId = "monitoring-macro-kpi-strip" }: MacroKpiStripProps) {
  return (
    <div className={cn("monitoring-macro-kpi-strip", className)} data-testid={testId} role="list">
      {items.map((item) => (
        <div
          key={item.id}
          className="monitoring-macro-kpi-cell"
          role="listitem"
          data-testid={`${testId}-${item.id}`}
        >
          <span className="monitoring-macro-kpi-label">{item.label}</span>
          <div className={cn("flex items-end gap-2", item.tone && toneClass[item.tone])}>
            <MacroKpiValue value={item.value} suffix={item.suffix} />
            {item.spark}
          </div>
        </div>
      ))}
    </div>
  )
}
