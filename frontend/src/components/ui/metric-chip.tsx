import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function MetricChip({
  label,
  value,
  detail,
  tone = "neutral",
  title,
  className,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: "neutral" | "positive" | "negative" | "warning"
  title?: string
  className?: string
}) {
  const toneClass =
    tone === "positive"
      ? "metric--positive"
      : tone === "negative"
        ? "metric--negative"
        : tone === "warning"
          ? "metric--warning"
          : "metric--neutral"

  return (
    <div className={cn("kpi-cell", className)} title={title}>
      <div className="kpi-cell-label">{label}</div>
      <div className={cn("kpi-cell-value", "metric", toneClass)}>{value}</div>
      {detail ? <div className="kpi-cell-sub">{detail}</div> : null}
    </div>
  )
}
