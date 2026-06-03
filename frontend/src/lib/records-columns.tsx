import type { ColumnDef } from "@tanstack/react-table"
import { Minus, TrendingDown, TrendingUp } from "lucide-react"

import { formatUnits } from "@/lib/format"
import type { TrackRecordPick } from "@/lib/types"
import type { StaticTrackRecordPick } from "@/lib/track-record"

export function buildGradingPickColumns(): ColumnDef<TrackRecordPick, unknown>[] {
  return [
    {
      id: "pick",
      header: "Pick",
      meta: { label: "Pick", sticky: true },
      cell: ({ row }) => {
        const pick = row.original
        const label = pick.opponent_display
          ? `${pick.player_display} vs ${pick.opponent_display}`
          : pick.player_display
        return <span className="records-pick-label">{label}</span>
      },
    },
    {
      id: "lane",
      accessorKey: "model_variant",
      header: "Lane",
      meta: { label: "Lane", align: "left" },
      cell: ({ getValue }) => (
        <span className="records-lane-chip">{(getValue() as string | undefined) ?? "baseline"}</span>
      ),
    },
    {
      id: "source",
      accessorKey: "source",
      header: "Source",
      meta: { label: "Source", mono: true },
      cell: ({ getValue }) => <span className="records-source">{(getValue() as string | null) ?? "—"}</span>,
    },
    {
      id: "modelWin",
      accessorKey: "model_prob",
      header: "Model Win%",
      meta: { label: "Model Win%", align: "right", mono: true },
      cell: ({ getValue }) => {
        const v = getValue() as number | null | undefined
        return v != null ? `${(v * 100).toFixed(1)}%` : "—"
      },
    },
    {
      id: "edge",
      accessorKey: "ev",
      header: "Edge%",
      meta: { label: "Edge%", align: "right", mono: true },
      cell: ({ getValue }) => {
        const v = getValue() as number | null | undefined
        return v != null ? `${(v * 100).toFixed(1)}%` : "—"
      },
    },
    {
      id: "result",
      accessorKey: "outcome",
      header: "Result",
      meta: { label: "Result", align: "center" },
      cell: ({ getValue }) => (
        <span className="records-result">{(getValue() as string | undefined)?.toUpperCase() ?? "—"}</span>
      ),
    },
    {
      id: "pl",
      accessorKey: "profit",
      header: "P&L",
      meta: { label: "P&L", align: "right", mono: true },
      cell: ({ getValue }) => {
        const profit = Number(getValue() ?? 0)
        const tone = profit > 0 ? "positive" : profit < 0 ? "negative" : "muted"
        return <span className={`records-pl records-pl--${tone}`}>{formatUnits(profit)}</span>
      },
    },
  ]
}

export function buildTrackRecordPickColumns(): ColumnDef<StaticTrackRecordPick, unknown>[] {
  return [
    {
      id: "pick",
      accessorKey: "pick",
      header: "Pick",
      meta: { label: "Pick", sticky: true },
      cell: ({ getValue }) => <span className="records-pick-label">{getValue() as string}</span>,
    },
    {
      id: "lane",
      accessorKey: "modelVariant",
      header: "Lane",
      meta: { label: "Lane" },
      cell: ({ getValue }) => (
        <span className="records-lane-chip">{(getValue() as string | undefined) ?? "baseline"}</span>
      ),
    },
    {
      id: "opponent",
      accessorKey: "opponent",
      header: "Opponent",
      meta: { label: "Opponent" },
    },
    {
      id: "odds",
      accessorKey: "odds",
      header: "Odds",
      meta: { label: "Odds", mono: true },
    },
    {
      id: "modelWin",
      accessorKey: "winProbPct",
      header: "Model Win%",
      meta: { label: "Model Win%", align: "right", mono: true },
      cell: ({ getValue }) => {
        const v = getValue() as number | null | undefined
        return v != null ? `${v.toFixed(1)}%` : "—"
      },
    },
    {
      id: "edge",
      accessorKey: "edgePct",
      header: "Edge%",
      meta: { label: "Edge%", align: "right", mono: true },
      cell: ({ getValue }) => {
        const v = getValue() as number | null | undefined
        return v != null ? `${v.toFixed(1)}%` : "—"
      },
    },
    {
      id: "resultFinish",
      header: "Result / Finish",
      meta: { label: "Result / Finish", align: "center" },
      cell: ({ row }) => {
        const pick = row.original
        const result = pick.result?.toLowerCase() ?? ""
        const isWin = result === "win"
        const isLoss = result === "loss"
        return (
          <div className="records-result-row">
            {isWin ? (
              <TrendingUp size={14} className="records-result-icon records-result-icon--win" aria-hidden />
            ) : isLoss ? (
              <TrendingDown size={14} className="records-result-icon records-result-icon--loss" aria-hidden />
            ) : (
              <Minus size={14} className="records-result-icon records-result-icon--push" aria-hidden />
            )}
            <span className="records-finish">{pick.finish ?? "—"}</span>
          </div>
        )
      },
    },
    {
      id: "pl",
      accessorKey: "pl",
      header: "P&L",
      meta: { label: "P&L", align: "right", mono: true },
      cell: ({ getValue }) => {
        const profit = Number(getValue() ?? 0)
        const tone = profit > 0 ? "positive" : profit < 0 ? "negative" : "muted"
        return <span className={`records-pl records-pl--${tone}`}>{formatUnits(profit)}</span>
      },
    },
  ]
}
