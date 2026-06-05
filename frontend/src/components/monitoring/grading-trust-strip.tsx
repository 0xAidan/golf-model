import { formatDateTime } from "@/lib/format"
import type { GradingTrustMetrics } from "@/lib/grading-trust"
import { cn } from "@/lib/utils"

import { MacroKpiStrip, type MacroKpiItem } from "./macro-kpi-strip"

export type GradingTrustStripProps = {
  metrics: GradingTrustMetrics
  pickSource: "all" | "cockpit" | "lab"
  onPickSourceChange: (source: "all" | "cockpit" | "lab") => void
  isFetching?: boolean
  showSourceToggle?: boolean
  className?: string
}

export function GradingTrustStrip({
  metrics,
  pickSource,
  onPickSourceChange,
  isFetching,
  showSourceToggle = true,
  className,
}: GradingTrustStripProps) {
  const kpiItems: MacroKpiItem[] = [
    {
      id: "last-graded",
      label: "Last graded",
      value: metrics.lastGradedAt ? formatDateTime(metrics.lastGradedAt) : "—",
    },
    {
      id: "positive-ev",
      label: "+EV picks",
      value: String(metrics.positiveEvPickCount),
      tone: "positive",
    },
    {
      id: "ungraded",
      label: "Ungraded +EV",
      value: String(metrics.ungradedPositiveEvCount),
      tone: metrics.ungradedPositiveEvCount > 0 ? "warning" : "neutral",
    },
  ]

  return (
    <div className={cn("grading-trust-strip", className)} data-testid="grading-trust-strip">
      <MacroKpiStrip items={kpiItems} testId="grading-trust-kpis" />
      {showSourceToggle ? (
        <div className="grading-trust-strip__controls" role="group" aria-label="Pick source">
          <span className="filter-bar-label">Pick source</span>
          {(["cockpit", "lab", "all"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={cn("btn btn-sm", pickSource === value ? "btn-primary" : "btn-ghost")}
              onClick={() => onPickSourceChange(value)}
              data-testid={`grading-source-${value}`}
            >
              {value === "cockpit" ? "Dashboard" : value === "lab" ? "Lab" : "All"}
            </button>
          ))}
          {isFetching ? <span className="filter-bar-hint">Updating…</span> : null}
        </div>
      ) : null}
      {metrics.showUngradedBanner ? (
        <div
          className="grading-ungraded-banner alert-banner alert-banner--warn"
          role="status"
          data-testid="grading-ungraded-banner"
        >
          {metrics.ungradedPositiveEvCount} +EV pick
          {metrics.ungradedPositiveEvCount === 1 ? "" : "s"} still need grading. Use{" "}
          <strong>Grade event</strong> in the header after the tournament completes.
        </div>
      ) : null}
    </div>
  )
}
