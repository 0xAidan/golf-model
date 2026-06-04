import type { ColumnDef } from "@tanstack/react-table"

import { SgTrajectoryMeter } from "@/components/sg-trajectory-meter"
import { formatNumber } from "@/lib/format"
import { heatSpectrumFromUnit, heatSpectrumGradientAlongUnit } from "@/lib/metric-heat"
import {
  POWER_RANKINGS_HELP,
  ROLLING_SG_GRID_HEADER_TOOLTIPS,
  ROLLING_WINDOW_ROW_TOOLTIP,
  SG_TRAJECTORY_HELP,
} from "@/lib/metric-tooltips"
import type { CompositePlayer, StandaloneRecentRoundSample } from "@/lib/types"
import { cn } from "@/lib/utils"

export type FieldListRow = {
  player_key: string
  player_display: string
  inField: boolean
  model?: CompositePlayer
}

export type RollingSgGridRow = {
  window: "10" | "25" | "50"
  sg_total?: number | null
  sg_ott?: number | null
  sg_app?: number | null
  sg_arg?: number | null
  sg_putt?: number | null
  sg_t2g?: number | null
}

export type CourseFitRow = {
  course_name: string
  rounds_played: number
  avg_sg_total?: number | null
}

function signed(v?: number | null, digits = 2): string {
  if (v == null) return "—"
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`
}

function formatCompactScore(v?: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—"
  return v.toFixed(1)
}

function heatUnitForSg(v?: number | null, maxAbs = 2.5): number {
  if (v == null) return 0.5
  return Math.min(1, Math.max(0, (v + maxAbs) / (maxAbs * 2)))
}

export type FieldListColumnOptions = {
  selectedKey: string | null
  onSelect: (key: string, display: string) => void
  trajectoryBounds: { min: number; max: number }
}

export function buildFieldListColumns({
  selectedKey,
  onSelect,
  trajectoryBounds,
}: FieldListColumnOptions): ColumnDef<FieldListRow, unknown>[] {
  return [
    {
      id: "player",
      header: "Player",
      meta: { label: "Player", sticky: true },
      cell: ({ row }) => {
        const p = row.original
        const isSelected = selectedKey === p.player_key
        return (
          <button
            type="button"
            className={cn("players-field-row-btn", isSelected && "players-field-row-btn--selected")}
            onClick={(e) => {
              e.stopPropagation()
              onSelect(p.player_key, p.player_display)
            }}
          >
            <div className="players-field-row-name">{p.player_display}</div>
            {!p.inField ? <div className="players-field-row-meta">DB record</div> : null}
            {p.inField && p.model ? (
              <div className="players-field-row-stats">
                <span title={POWER_RANKINGS_HELP.rank}>#{p.model.rank}</span>
                <span className="players-field-stat-cyan" title={POWER_RANKINGS_HELP.composite}>
                  C {formatCompactScore(p.model.composite)}
                </span>
                <span className="players-field-stat-green" title={POWER_RANKINGS_HELP.form}>
                  F {formatCompactScore(p.model.form)}
                </span>
                <span className="players-field-traj">
                  <SgTrajectoryMeter
                    momentumTrend={p.model.momentum_trend}
                    momentumDirection={p.model.momentum_direction}
                    normMin={trajectoryBounds.min}
                    normMax={trajectoryBounds.max}
                  />
                </span>
              </div>
            ) : null}
          </button>
        )
      },
    },
  ]
}

export function buildRollingSgGridColumns(): ColumnDef<RollingSgGridRow, unknown>[] {
  const sgCols = ["TOTAL", "OTT", "APP", "ARG", "PUTT", "T2G"] as const
  const keys: Array<keyof Omit<RollingSgGridRow, "window">> = [
    "sg_total",
    "sg_ott",
    "sg_app",
    "sg_arg",
    "sg_putt",
    "sg_t2g",
  ]

  return [
    {
      id: "window",
      accessorKey: "window",
      header: "Window",
      meta: { label: "Window", align: "left", sticky: true },
      cell: ({ row }) => (
        <span className="players-grid-window" title={ROLLING_WINDOW_ROW_TOOLTIP}>
          L{row.original.window}
        </span>
      ),
    },
    ...sgCols.map((head, index) => ({
      id: head.toLowerCase(),
      header: head,
      meta: { label: head, align: "center" as const },
      cell: ({ row }: { row: { original: RollingSgGridRow } }) => {
        const value = row.original[keys[index]!]
        const heatT = heatUnitForSg(value)
        return (
          <span
            className="players-sg-heat-cell"
            style={{ background: heatSpectrumGradientAlongUnit(heatT, "ltr") }}
          >
            {signed(value, 2)}
          </span>
        )
      },
    })),
  ]
}

export function buildCourseFitColumns(): ColumnDef<CourseFitRow, unknown>[] {
  return [
    {
      id: "course",
      accessorKey: "course_name",
      header: "Course",
      meta: { label: "Course", sticky: true },
      cell: ({ getValue }) => <span className="players-grid-text">{String(getValue() ?? "—")}</span>,
    },
    {
      id: "rounds",
      accessorKey: "rounds_played",
      header: "Rounds",
      meta: { label: "Rounds", align: "center", mono: true },
      cell: ({ getValue }) => <span className="num text-muted-11">{String(getValue() ?? "—")}</span>,
    },
    {
      id: "avgSg",
      accessorKey: "avg_sg_total",
      header: "Avg SG Total",
      meta: { label: "Avg SG Total", align: "center", mono: true },
      cell: ({ row }) => {
        const v = row.original.avg_sg_total
        return (
          <span
            className="num"
            style={{ color: v != null ? heatSpectrumFromUnit(heatUnitForSg(v)) : undefined }}
          >
            {signed(v, 2)}
          </span>
        )
      },
    },
  ]
}

export function buildRecentRoundsColumns(): ColumnDef<StandaloneRecentRoundSample, unknown>[] {
  const heads = ["Date", "Event", "R", "Score", "TOT", "OTT", "APP", "ARG", "PUTT", "T2G"] as const
  const valueKeys: Array<
    | "event_completed"
    | "event_name"
    | "round_num"
    | "score"
    | "sg_total"
    | "sg_ott"
    | "sg_app"
    | "sg_arg"
    | "sg_putt"
    | "sg_t2g"
  > = [
    "event_completed",
    "event_name",
    "round_num",
    "score",
    "sg_total",
    "sg_ott",
    "sg_app",
    "sg_arg",
    "sg_putt",
    "sg_t2g",
  ]

  return heads.map((head, index) => ({
    id: head.toLowerCase().replace(/\s/g, ""),
    header: head,
    meta: {
      label: head,
      align: (head === "Event" ? "left" : "center") as "left" | "center",
      mono: head !== "Event",
    },
    cell: ({ row }: { row: { original: StandaloneRecentRoundSample } }) => {
      const key = valueKeys[index]!
      const raw = row.original[key]
      const value =
        key.startsWith("sg_") && typeof raw === "number"
          ? raw
          : raw ?? "—"
      if (typeof value === "number") {
        return (
          <span className="num" style={{ color: heatSpectrumFromUnit(heatUnitForSg(value)) }}>
            {signed(value, 2)}
          </span>
        )
      }
      const display = value === null || value === undefined ? "—" : String(value)
      const cls =
        head === "Date"
          ? "players-round-date"
          : head === "Event"
            ? "players-grid-text"
            : "num text-muted-11"
      return <span className={cls}>{display}</span>
    },
  }))
}
