import { heatSpectrumFromUnit, heatSpectrumGradientAlongUnit } from "@/lib/metric-heat"
import { cn } from "@/lib/utils"

type RollingExpanded = Record<
  "sg_total" | "sg_ott" | "sg_app" | "sg_arg" | "sg_putt" | "sg_t2g",
  { "10"?: number | null; "25"?: number | null; "50"?: number | null }
>

const ROWS = [
  { key: "sg_total" as const, label: "Total" },
  { key: "sg_ott" as const, label: "OTT" },
  { key: "sg_app" as const, label: "APP" },
  { key: "sg_arg" as const, label: "ARG" },
  { key: "sg_putt" as const, label: "PUTT" },
  { key: "sg_t2g" as const, label: "T2G" },
]

const COLS = ["10", "25", "50"] as const

const heatUnit = (v: number | null | undefined, maxAbs = 2.5) => {
  if (v == null || !Number.isFinite(v)) return 0.5
  return Math.min(1, Math.max(0, (v + maxAbs) / (maxAbs * 2)))
}

const signed = (v: number | null | undefined) => {
  if (v == null || !Number.isFinite(v)) return "—"
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}`
}

export const RollingHeatmap = ({
  data,
  className,
}: {
  data?: RollingExpanded | null
  className?: string
}) => {
  if (!data) {
    return (
      <div className={cn("players-rolling-heatmap players-rolling-heatmap--empty", className)}>
        No rolling window data
      </div>
    )
  }

  return (
    <div className={cn("players-rolling-heatmap", className)} data-testid="players-rolling-heatmap">
      <div className="players-rolling-heatmap__grid" role="grid" aria-label="Rolling SG heatmap">
        <div className="players-rolling-heatmap__corner" />
        {COLS.map((col) => (
          <div key={col} className="players-rolling-heatmap__col-head" role="columnheader">
            L{col}
          </div>
        ))}
        {ROWS.flatMap((row) => [
          <div
            key={`${row.key}-label`}
            className="players-rolling-heatmap__row-head"
            role="rowheader"
          >
            {row.label}
          </div>,
          ...COLS.map((col) => {
            const value = data[row.key]?.[col]
            const unit = heatUnit(value)
            return (
              <div
                key={`${row.key}-${col}`}
                className="players-rolling-heatmap__cell"
                role="gridcell"
                title={`${row.label} L${col}: ${signed(value)}`}
                style={{ background: heatSpectrumGradientAlongUnit(unit, "ltr") }}
              >
                <span
                  className="players-rolling-heatmap__value num"
                  style={{ color: value != null ? heatSpectrumFromUnit(unit) : undefined }}
                >
                  {signed(value)}
                </span>
              </div>
            )
          }),
        ])}
      </div>
    </div>
  )
}
