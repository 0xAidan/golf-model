import { formatDateTime } from "@/lib/format"
import type { GradingTrustMetrics } from "@/lib/grading-trust"
import { cn } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { StatusBanner } from "@/components/ui/status-banner"
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
  const autoGradeTone =
    metrics.autoGradeMessage && /fail|error/i.test(metrics.autoGradeMessage) ? "warn" : "info"
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
    <div className={cn("grading-trust-strip space-y-3", className)} data-testid="grading-trust-strip">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
        <MacroKpiStrip items={kpiItems} testId="grading-trust-kpis" />
      </div>
      {showSourceToggle ? (
        <div
          className="grading-trust-strip__controls rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
          role="group"
          aria-label="Pick source"
        >
          <span className="filter-bar-label">Pick source</span>
          {(["cockpit", "lab", "all"] as const).map((value) => (
            <Button
              key={value}
              type="button"
              variant={pickSource === value ? "default" : "outline"}
              size="sm"
              onClick={() => onPickSourceChange(value)}
              data-testid={`grading-source-${value}`}
            >
              {value === "cockpit" ? "Dashboard" : value === "lab" ? "Lab" : "All"}
            </Button>
          ))}
          {isFetching ? <span className="filter-bar-hint ml-auto">Updating…</span> : null}
        </div>
      ) : null}
      {metrics.showUngradedBanner ? (
        <div data-testid="grading-ungraded-banner">
          <StatusBanner
            tone="warn"
            title="Ungraded +EV picks remain"
            message={`${metrics.ungradedPositiveEvCount} +EV pick${
              metrics.ungradedPositiveEvCount === 1 ? "" : "s"
            } still need grading. Use Grade event in the header after the tournament completes.`}
          />
        </div>
      ) : null}
      {metrics.autoGradeMessage ? (
        <div data-testid="grading-auto-grade-banner">
          <StatusBanner
            tone={autoGradeTone}
            title="Auto-grade status"
            message={metrics.autoGradeMessage}
          />
        </div>
      ) : null}
    </div>
  )
}
