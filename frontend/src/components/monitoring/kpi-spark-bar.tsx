import { cn } from "@/lib/utils"

export type KpiSparkBarProps = {
  values: number[]
  max?: number
  className?: string
  testId?: string
}

export function KpiSparkBar({ values, max, className, testId = "monitoring-kpi-spark-bar" }: KpiSparkBarProps) {
  const peak = max ?? Math.max(...values, 1)

  return (
    <div
      className={cn("monitoring-kpi-spark-bar", className)}
      data-testid={testId}
      role="img"
      aria-label="Spark trend"
    >
      {values.map((value, index) => {
        const heightPct = Math.max(8, Math.round((value / peak) * 100))
        const isActive = index === values.length - 1
        return (
          <span
            key={index}
            className={cn(
              "monitoring-kpi-spark-bar__bar",
              isActive && "monitoring-kpi-spark-bar__bar--active",
            )}
            style={{ height: `${heightPct}%` }}
          />
        )
      })}
    </div>
  )
}
