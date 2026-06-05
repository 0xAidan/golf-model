import { Radar } from "lucide-react"

import { MacroKpiStrip, type MacroKpiItem } from "@/components/monitoring/macro-kpi-strip"
import type { DisplayRecordSummary } from "@/lib/record-summary"

export function WorkspaceMacroKpis({
  eventName,
  courseName,
  fieldSize,
  recordSummary,
  isNarrow,
}: {
  eventName: string
  courseName: string
  fieldSize: number | null
  recordSummary: DisplayRecordSummary
  isNarrow: boolean
}) {
  const items: MacroKpiItem[] = [
    {
      id: "event",
      label: "Event",
      value: eventName,
      tone: "neutral",
    },
    {
      id: "field",
      label: "Field",
      value: fieldSize ?? "—",
      suffix: "players",
      tone: "neutral",
    },
    {
      id: "combined",
      label: "Combined",
      value: recordSummary.combined.profit,
      tone: recordSummary.combined.profit >= 0 ? "positive" : "negative",
    },
    {
      id: "matchups",
      label: "Matchups",
      value: recordSummary.matchups.profit,
      tone: recordSummary.matchups.profit >= 0 ? "positive" : "negative",
    },
    {
      id: "outrights",
      label: "Outrights",
      value: recordSummary.outrights.profit,
      tone: recordSummary.outrights.profit >= 0 ? "positive" : "negative",
    },
  ]

  return (
    <div className={isNarrow ? "kpi-strip kpi-strip--compact" : "kpi-strip"} data-testid="workspace-macro-kpis">
      <MacroKpiStrip
        testId="workspace-kpi-strip"
        items={items.map((item) => {
          if (item.id === "event") {
            return {
              ...item,
              value: eventName,
            }
          }
          if (item.id === "combined") {
            return {
              ...item,
              spark: (
                <span className="kpi-cell-sub">
                  {recordSummary.combined.recordLabel} · {recordSummary.combined.hitRateLabel}
                </span>
              ),
            }
          }
          if (item.id === "matchups") {
            return {
              ...item,
              spark: (
                <span className="kpi-cell-sub">
                  {recordSummary.matchups.recordLabel} · {recordSummary.matchups.hitRateLabel}
                </span>
              ),
            }
          }
          if (item.id === "outrights") {
            return {
              ...item,
              spark: (
                <span className="kpi-cell-sub">
                  {recordSummary.outrights.recordLabel} · {recordSummary.outrights.hitRateLabel}
                </span>
              ),
            }
          }
          return item
        })}
      />
      {courseName && !isNarrow ? (
        <div className="kpi-cell-sub workspace-kpi-course" data-testid="workspace-kpi-course">
          <Radar size={11} aria-hidden /> {courseName}
        </div>
      ) : null}
    </div>
  )
}
