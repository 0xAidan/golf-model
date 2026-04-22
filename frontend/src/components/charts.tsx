import ReactECharts from "echarts-for-react"

/* ─── Design tokens (match index.css) ───────────────────────────────── */
const T = {
  bg:       "#0d1012",
  surface:  "#141719",
  border:   "#1f2426",
  text:     "#e8ecef",
  muted:    "#6b7a84",
  faint:    "#374349",
  green:    "#22c55e",
  cyan:     "#22c55e",
  gold:     "#f5b418",
  red:      "#ef4444",
  amber:    "#f59e0b",
  mono:     "'JetBrains Mono', 'Fira Code', monospace",
}

const TOOLTIP_STYLE = {
  backgroundColor: T.bg,
  borderColor: T.border,
  borderWidth: 1,
  textStyle: { color: T.text, fontSize: 11, fontFamily: T.mono },
  extraCssText: "border-radius:3px;box-shadow:0 4px 16px rgba(0,0,0,0.5);",
}

/* ─── Empty placeholder ─────────────────────────────────────────────── */
function ChartEmpty({ height = 120, message = "No data available" }: { height?: number; message?: string }) {
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

/* ─── 1. Sparkline ──────────────────────────────────────────────────── */
export function SparklineChart({
  values,
  color = T.cyan,
  height = 80,
  showZeroLine = true,
}: {
  values: number[]
  color?: string
  height?: number
  showZeroLine?: boolean
}) {
  if (!values.length) return <ChartEmpty height={height} />

  const hasNegative = values.some((v) => v < 0)
  const markLine = showZeroLine && hasNegative
    ? {
        silent: true,
        symbol: ["none", "none"],
        lineStyle: { color: T.border, width: 1, type: "solid" },
        data: [{ yAxis: 0 }],
        label: { show: false },
      }
    : undefined

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 8, right: 4, bottom: 4, left: 4 },
        xAxis: { type: "category", data: values.map((_, i) => i + 1), show: false },
        yAxis: { type: "value", show: false, scale: true },
        series: [
          {
            data: values,
            type: "line",
            smooth: 0.4,
            showSymbol: false,
            lineStyle: { color, width: 2 },
            areaStyle: {
              color: {
                type: "linear", x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: `${color}40` },
                  { offset: 1, color: `${color}04` },
                ],
              },
            },
            markLine,
          },
        ],
        tooltip: {
          trigger: "axis",
          ...TOOLTIP_STYLE,
          formatter: (params: Array<{ value?: number | number[]; dataIndex?: number; [k: string]: unknown }>) => {
            const v = params[0]?.value
            return `Round ${(params[0]?.dataIndex ?? 0) + 1}<br/><b style="color:${color}">${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(3)} SG</b>`
          },
        },
      }}
    />
  )
}

/* ─── 2. SG Rolling Line Chart (with benchmark band) ───────────────── */
export function SgRollingChart({
  values,
  benchmarkValue,
  benchmarkLabel = "Benchmark",
  height = 180,
}: {
  values: number[]
  benchmarkValue?: number | null
  benchmarkLabel?: string
  height?: number
}) {
  if (!values.length) return <ChartEmpty height={height} message="No form data" />

  const seriesData = values.map((v, i) => [i + 1, v])

  const series: Array<Record<string, unknown>> = [
    {
      name: "SG / Round",
      type: "line",
      data: seriesData,
      smooth: 0.35,
      showSymbol: values.length <= 15,
      symbolSize: 4,
      lineStyle: { color: T.cyan, width: 2 },
      itemStyle: { color: T.cyan },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: `${T.cyan}35` },
            { offset: 1, color: `${T.cyan}04` },
          ],
        },
      },
      markLine: {
        silent: true,
        symbol: ["none", "none"],
        lineStyle: { color: T.border, width: 1, type: "dashed" },
        data: [{ yAxis: 0 }],
        label: { show: true, formatter: "Tour Avg (0)", fontSize: 9, color: T.faint, fontFamily: T.mono, position: "end" },
      },
    },
  ]

  if (benchmarkValue != null) {
    series.push({
      name: benchmarkLabel,
      type: "line",
      data: seriesData.map(([x]) => [x, benchmarkValue]),
      smooth: false,
      showSymbol: false,
      lineStyle: { color: T.gold, width: 1.5, type: "dashed" },
      itemStyle: { color: T.gold },
    })
  }

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 16, right: 16, bottom: 28, left: 42 },
        legend: benchmarkValue != null
          ? {
              data: ["SG / Round", benchmarkLabel],
              textStyle: { color: T.muted, fontSize: 9, fontFamily: T.mono },
              top: 0,
              right: 0,
              itemHeight: 8,
              itemWidth: 16,
            }
          : undefined,
        xAxis: {
          type: "value",
          name: "Round (oldest → newest)",
          nameTextStyle: { color: T.faint, fontSize: 9, fontFamily: T.mono },
          min: 1,
          max: values.length,
          axisLabel: { color: T.faint, fontSize: 9, fontFamily: T.mono },
          axisLine: { lineStyle: { color: T.border } },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: {
            color: T.muted,
            fontSize: 9,
            fontFamily: T.mono,
            formatter: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`,
          },
          axisLine: { show: false },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
        },
        series,
        tooltip: {
          trigger: "axis",
          ...TOOLTIP_STYLE,
          formatter: (params: Array<{ value?: number | number[]; color?: string; seriesName?: string; [k: string]: unknown }>) => {
            return params.map((p) => {
              const v = Array.isArray(p.value) ? p.value[1] : p.value
              const sign = Number(v) > 0 ? "+" : ""
              return `<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${sign}${Number(v).toFixed(3)}</b>`
            }).join("<br/>")
          },
        },
      }}
    />
  )
}

/* ─── 3. SG Skills Diverging Bar Chart ─────────────────────────────── */
export function SgSkillBarsChart({
  skills,
  height = 200,
}: {
  skills: Array<{ label: string; value: number; color?: string }>
  height?: number
}) {
  if (!skills.length) return <ChartEmpty height={height} message="No skill data" />

  const labels = skills.map((s) => s.label)
  const values = skills.map((s) => s.value)

  const itemColors = values.map((v) =>
    v > 0.3 ? T.green : v > 0 ? `${T.green}bb` : v > -0.3 ? `${T.red}bb` : T.red
  )

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 8, right: 60, bottom: 8, left: 120 },
        xAxis: {
          type: "value",
          scale: true,
          axisLabel: {
            color: T.muted,
            fontSize: 9,
            fontFamily: T.mono,
            formatter: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`,
          },
          axisLine: { lineStyle: { color: T.border } },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
          markLine: {
            data: [{ xAxis: 0 }],
            lineStyle: { color: T.muted, width: 1 },
          },
        },
        yAxis: {
          type: "category",
          data: labels,
          axisLabel: {
            color: T.muted,
            fontSize: 10,
            fontFamily: T.mono,
          },
          axisLine: { lineStyle: { color: T.border } },
          splitLine: { show: false },
        },
        series: [
          {
            type: "bar",
            data: values.map((v, i) => ({
              value: v,
              itemStyle: { color: itemColors[i], borderRadius: v >= 0 ? [0, 2, 2, 0] : [2, 0, 0, 2] },
            })),
            barMaxWidth: 18,
            label: {
              show: true,
              position: (params: { value?: number; [k: string]: unknown }) => ((params.value ?? 0) >= 0 ? "right" : "left"),
              formatter: (params: { value?: number; [k: string]: unknown }) => {
                const v = Number(params.value)
                return `${v > 0 ? "+" : ""}${v.toFixed(3)}`
              },
              color: T.muted,
              fontSize: 9,
              fontFamily: T.mono,
            },
          },
        ],
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          ...TOOLTIP_STYLE,
          formatter: (params: Array<{ value?: number; name?: string; [k: string]: unknown }>) => {
            const p = params[0]
            const v = Number(p.value)
            const sign = v > 0 ? "+" : ""
            const col = v > 0 ? T.green : T.red
            return `${p.name}<br/><b style="color:${col}">${sign}${v.toFixed(3)} SG/round</b>`
          },
        },
      }}
    />
  )
}

/* ─── 4. Approach Buckets Grouped Bar Chart ─────────────────────────── */
export function ApproachBucketsChart({
  buckets,
  height = 200,
}: {
  buckets: Array<{ label: string; value: number }>
  height?: number
}) {
  if (!buckets.length) return <ChartEmpty height={height} message="No approach data" />

  // Split FW vs Rough
  const fw = buckets.filter((b) => b.label.includes("FW"))
  const rgh = buckets.filter((b) => b.label.includes("Rough"))
  const fwLabels = fw.map((b) => b.label.replace(" (FW)", ""))

  if (!fw.length) return <ChartEmpty height={height} message="No approach buckets" />

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 28, right: 12, bottom: 36, left: 12 },
        legend: {
          data: ["Fairway", "Rough"],
          textStyle: { color: T.muted, fontSize: 9, fontFamily: T.mono },
          top: 0,
          itemHeight: 8,
          itemWidth: 14,
        },
        xAxis: {
          type: "category",
          data: fwLabels,
          axisLabel: {
            color: T.muted,
            fontSize: 9,
            fontFamily: T.mono,
            rotate: 15,
          },
          axisLine: { lineStyle: { color: T.border } },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: {
            color: T.muted,
            fontSize: 9,
            fontFamily: T.mono,
            formatter: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}`,
          },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
          axisLine: { show: false },
        },
        series: [
          {
            name: "Fairway",
            type: "bar",
            data: fw.map((b) => ({
              value: b.value,
              itemStyle: {
                color: b.value >= 0 ? `${T.green}cc` : `${T.red}99`,
                borderRadius: [2, 2, 0, 0],
              },
            })),
            barGap: "10%",
          },
          {
            name: "Rough",
            type: "bar",
            data: rgh.map((b) => ({
              value: b.value,
              itemStyle: {
                color: b.value >= 0 ? `${T.green}99` : `${T.red}66`,
                borderRadius: [2, 2, 0, 0],
              },
            })),
          },
        ],
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          ...TOOLTIP_STYLE,
          formatter: (params: Array<{ value?: number; color?: string; seriesName?: string; [k: string]: unknown }>) => {
            return params.map((p) => {
              const v = Number(p.value)
              const sign = v >= 0 ? "+" : ""
              const col = v >= 0 ? T.green : T.red
              return `<span style="color:${p.color}">●</span> ${p.seriesName}: <b style="color:${col}">${sign}${v.toFixed(3)}</b>`
            }).join("<br/>")
          },
        },
      }}
    />
  )
}

/* ─── 5. Tournament History Bar Chart (SG per event) ───────────────── */
export function TournamentHistoryChart({
  events,
  height = 160,
}: {
  events: Array<{ event_name: string; avg_sg_total?: number | null; fin_text?: string | null }>
  height?: number
}) {
  const filtered = events.filter((e) => e.avg_sg_total != null).slice(0, 16).reverse()
  if (!filtered.length) return <ChartEmpty height={height} message="No event history" />

  const labels = filtered.map((e) => {
    const name = e.event_name ?? ""
    // Abbreviate long names
    const words = name.split(" ")
    return words.length > 2 ? words.slice(0, 2).join(" ") : name
  })
  const values = filtered.map((e) => e.avg_sg_total!)

  const itemColors = values.map((v) =>
    v >= 1.5 ? T.green : v >= 0.5 ? `${T.green}99` : v >= 0 ? `${T.green}55` : v >= -0.5 ? `${T.amber}99` : T.red
  )

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 8, right: 8, bottom: 60, left: 44 },
        xAxis: {
          type: "category",
          data: labels,
          axisLabel: {
            color: T.faint,
            fontSize: 8,
            fontFamily: T.mono,
            rotate: 35,
            interval: 0,
          },
          axisLine: { lineStyle: { color: T.border } },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: {
            color: T.muted,
            fontSize: 9,
            fontFamily: T.mono,
            formatter: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`,
          },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
          axisLine: { show: false },
        },
        series: [
          {
            type: "bar",
            data: values.map((v, i) => ({
              value: v,
              itemStyle: { color: itemColors[i], borderRadius: v >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2] },
            })),
            barMaxWidth: 28,
            markLine: {
              silent: true,
              symbol: ["none", "none"],
              lineStyle: { color: T.muted, width: 1, type: "dashed" },
              data: [{ yAxis: 0 }],
              label: { show: false },
            },
          },
        ],
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          ...TOOLTIP_STYLE,
          formatter: (params: Array<{ value?: number; dataIndex?: number; [k: string]: unknown }>) => {
            const p = params[0]
            const v = Number(p.value)
            const sign = v > 0 ? "+" : ""
            const col = v > 0 ? T.green : T.red
            const idx = p.dataIndex ?? 0
            const ev = filtered[idx]
            const fin = ev?.fin_text ? ` · ${ev.fin_text}` : ""
            return `${filtered[idx]?.event_name}<br/><b style="color:${col}">${sign}${v.toFixed(3)} SG/round</b>${fin}`
          },
        },
      }}
    />
  )
}

/* ─── 6. Legacy BarTrendChart (kept for matchups page) ─────────────── */
export function BarTrendChart({
  labels,
  values,
  color = T.green,
  height = 220,
}: {
  labels: string[]
  values: number[]
  color?: string
  height?: number
}) {
  if (!labels.length || !values.length) return <ChartEmpty height={height} />

  return (
    <ReactECharts
      style={{ height }}
      option={{
        animation: false,
        grid: { top: 16, right: 12, bottom: 36, left: 36 },
        xAxis: {
          type: "category",
          data: labels,
          axisLabel: { color: T.muted, fontSize: 9, fontFamily: T.mono, rotate: 20 },
          axisLine: { lineStyle: { color: T.border } },
          splitLine: { show: false },
        },
        yAxis: {
          type: "value",
          scale: true,
          axisLabel: { color: T.muted, fontSize: 9, fontFamily: T.mono },
          splitLine: { lineStyle: { color: T.border, type: "dashed" } },
          axisLine: { show: false },
        },
        series: [
          {
            type: "bar",
            data: values.map((v) => ({
              value: v,
              itemStyle: {
                color: v >= 0 ? color : T.red,
                borderRadius: v >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2],
              },
            })),
            barMaxWidth: 36,
          },
        ],
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          ...TOOLTIP_STYLE,
        },
      }}
    />
  )
}
