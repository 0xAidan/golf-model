import ReactECharts from "echarts-for-react"

import type { RankScatterPoint } from "@/components/compare/compare-types"
import type { ComponentDriverSummary } from "@/components/compare/compare-types"
import { getEchartsTooltipStyle } from "@/lib/chart-theme"

const T = {
  surface: "var(--surface)",
  border: "var(--border)",
  text: "var(--text)",
  faint: "var(--text-faint)",
  green: "var(--green)",
  cyan: "var(--cyan)",
  gold: "var(--gold)",
  red: "var(--red)",
  mono: "var(--font-mono)",
}

function ChartEmpty({ height = 220, message = "No data" }: { height?: number; message?: string }) {
  return (
    <div
      style={{
        height,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: T.surface,
        border: `1px dashed ${T.border}`,
        borderRadius: 3,
        fontFamily: T.mono,
        fontSize: 10,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: T.faint,
      }}
    >
      {message}
    </div>
  )
}

export function RankScatterChart({
  points,
  height = 280,
  highlightedKey,
  onPointClick,
}: {
  points: RankScatterPoint[]
  height?: number
  highlightedKey?: string | null
  onPointClick?: (playerKey: string) => void
}) {
  if (!points.length) return <ChartEmpty height={height} message="No overlapping ranks" />

  const maxRank = Math.max(...points.flatMap((p) => [p.championRank, p.challengerRank]), 1)

  const seriesData = points.map((p) => ({
    value: [p.championRank, p.challengerRank],
    name: p.player,
    playerKey: p.playerKey,
    delta: p.delta,
    itemStyle: {
      color: p.playerKey === highlightedKey ? T.gold : T.cyan,
      opacity: highlightedKey && p.playerKey !== highlightedKey ? 0.35 : 0.85,
    },
  }))

  return (
    <ReactECharts
      style={{ height }}
      onEvents={{
        click: (params: { data?: { playerKey?: string } }) => {
          const key = params?.data?.playerKey
          if (key) onPointClick?.(key)
        },
      }}
      option={{
        animation: false,
        grid: { top: 16, right: 16, bottom: 36, left: 44 },
        tooltip: {
          ...getEchartsTooltipStyle(),
          trigger: "item",
          formatter: (params: { data?: { name?: string; value?: number[]; delta?: number } }) => {
            const d = params.data
            if (!d?.value) return ""
            return [
              `<strong>${d.name ?? ""}</strong>`,
              `Champion #${d.value[0]}`,
              `Challenger #${d.value[1]}`,
              `Δ ${d.delta != null && d.delta > 0 ? "+" : ""}${d.delta ?? "—"}`,
            ].join("<br/>")
          },
        },
        xAxis: {
          type: "value",
          name: "Champion rank",
          nameLocation: "middle",
          nameGap: 22,
          min: 1,
          max: maxRank,
          inverse: false,
          axisLabel: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
        },
        yAxis: {
          type: "value",
          name: "Challenger rank",
          nameLocation: "middle",
          nameGap: 32,
          min: 1,
          max: maxRank,
          inverse: true,
          axisLabel: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
        },
        series: [
          {
            type: "line",
            data: [
              [1, 1],
              [maxRank, maxRank],
            ],
            symbol: "none",
            lineStyle: { color: T.border, type: "dashed", width: 1 },
            silent: true,
            z: 0,
          },
          {
            type: "scatter",
            data: seriesData,
            symbolSize: 8,
            z: 1,
          },
        ],
      }}
    />
  )
}

export function ComponentDriversChart({
  summary,
  height = 200,
}: {
  summary: ComponentDriverSummary
  height?: number
}) {
  if (summary.sampleSize === 0) {
    return <ChartEmpty height={height} message="No rank disagreements above threshold" />
  }

  const labels = ["Composite", "Form", "Course", "Momentum"]
  const values = [summary.composite, summary.form, summary.courseFit, summary.momentum]

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 8, right: 12, bottom: 28, left: 72 },
        tooltip: {
          ...getEchartsTooltipStyle(),
          trigger: "axis",
          formatter: (params: Array<{ name?: string; value?: number }>) => {
            const p = params[0]
            if (!p) return ""
            return `${p.name}: ${Number(p.value).toFixed(2)} avg |Δ|`
          },
        },
        xAxis: {
          type: "value",
          axisLabel: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
        },
        yAxis: {
          type: "category",
          data: labels,
          axisLabel: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
          axisTick: { show: false },
          axisLine: { show: false },
        },
        series: [
          {
            type: "bar",
            data: values.map((v, i) => ({
              value: v,
              itemStyle: { color: [T.cyan, T.green, T.gold, T.red][i] ?? T.cyan },
            })),
            barMaxWidth: 18,
          },
        ],
      }}
    />
  )
}

export function MarketDeltaChart({
  labels,
  championValues,
  challengerValues,
  height = 200,
  suffix = "%",
}: {
  labels: string[]
  championValues: number[]
  challengerValues: number[]
  height?: number
  suffix?: string
}) {
  if (!labels.length) return <ChartEmpty height={height} message="No market breakdown" />

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        legend: {
          data: ["Champion", "Challenger"],
          textStyle: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
          top: 0,
        },
        grid: { top: 32, right: 12, bottom: 28, left: 44 },
        tooltip: {
          ...getEchartsTooltipStyle(),
          trigger: "axis",
          valueFormatter: (v: number) => `${v}${suffix}`,
        },
        xAxis: {
          type: "category",
          data: labels,
          axisLabel: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
        },
        yAxis: {
          type: "value",
          axisLabel: { color: T.faint, fontFamily: T.mono, fontSize: 10 },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
        },
        series: [
          {
            name: "Champion",
            type: "bar",
            data: championValues,
            itemStyle: { color: T.cyan },
            barGap: "20%",
          },
          {
            name: "Challenger",
            type: "bar",
            data: challengerValues,
            itemStyle: { color: T.gold },
          },
        ],
      }}
    />
  )
}
