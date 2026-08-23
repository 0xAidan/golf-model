import { useMemo } from "react"
import ReactECharts from "echarts-for-react"

import { Reveal } from "@/components/motion/primitives"
import { getEchartsAxisStyle, getEchartsTooltipStyle, readCssVar } from "@/lib/chart-theme"
import type { GradingSeasonEvent } from "@/lib/types"

/**
 * SeasonEquityHero — cumulative units across the season's graded
 * events, with a zero baseline. Sits above the existing season grid;
 * purely additive, no data contracts changed.
 */
export function SeasonEquityHero({ events }: { events: GradingSeasonEvent[] }) {
  const series = useMemo(() => {
    // Chronological by grade time; skip events with no graded picks.
    const ordered = [...events]
      .filter((event) => (event.graded_pick_count ?? 0) > 0)
      .sort((a, b) =>
        String(a.last_graded_at ?? a.event_date ?? "").localeCompare(
          String(b.last_graded_at ?? b.event_date ?? ""),
        ),
      )

    let cumulative = 0
    const points: Array<{ name: string; value: number }> = []
    for (const event of ordered) {
      cumulative += Number(event.total_profit ?? 0)
      points.push({
        name: event.name ?? String(event.event_id ?? ""),
        value: Math.round(cumulative * 100) / 100,
      })
    }
    return points
  }, [events])

  if (series.length < 2) return null

  const edgeColor = readCssVar("--accent-edge", "#34d399")
  const redColor = readCssVar("--red", "#f87171")
  const last = series[series.length - 1].value
  const tooltip = getEchartsTooltipStyle()
  const axis = getEchartsAxisStyle()

  return (
    <Reveal>
      <div className="panel mb-4" data-testid="season-equity-hero">
        <div className="panel__header">
          <span className="panel__title">Season equity — cumulative units</span>
          <span
            className="num text-sm font-bold"
            style={{ color: last >= 0 ? edgeColor : redColor }}
            data-testid="season-equity-total"
          >
            {last >= 0 ? "+" : ""}
            {last.toFixed(2)}u
          </span>
        </div>
        <div className="px-2 pb-2 pt-1">
          <ReactECharts
            style={{ height: 220 }}
            notMerge
            option={{
              animation: true,
              animationDuration: 700,
              grid: { top: 14, right: 14, bottom: 26, left: 46 },
              xAxis: {
                type: "category",
                data: series.map((point) => point.name),
                boundaryGap: false,
                ...axis,
              },
              yAxis: { type: "value", scale: true, ...axis },
              tooltip: {
                trigger: "axis",
                formatter: (params: Array<{ name?: string; value?: number }>) => {
                  const point = params[0]
                  return `<b>${point?.name ?? ""}</b><br/>Cumulative: <b>${point?.value ?? 0}u</b>`
                },
                ...tooltip,
              },
              series: [
                {
                  type: "line",
                  data: series.map((point) => point.value),
                  smooth: 0.25,
                  showSymbol: false,
                  connectNulls: true,
                  lineStyle: { width: 2.5, color: edgeColor },
                  areaStyle: {
                    color: {
                      type: "linear",
                      x: 0,
                      y: 0,
                      x2: 0,
                      y2: 1,
                      colorStops: [
                        { offset: 0, color: `${edgeColor}33` },
                        { offset: 1, color: `${edgeColor}00` },
                      ],
                    },
                  },
                  markLine: {
                    silent: true,
                    symbol: "none",
                    label: { show: false },
                    lineStyle: { color: readCssVar("--chart-grid-strong", "#333"), type: "dashed" },
                    data: [{ yAxis: 0 }],
                  },
                },
              ],
            }}
          />
        </div>
      </div>
    </Reveal>
  )
}
