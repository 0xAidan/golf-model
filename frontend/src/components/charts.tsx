import ReactECharts from "echarts-for-react"

export function SparklineChart({
  values,
  color,
}: {
  values: number[]
  color: string
}) {
  return (
    <ReactECharts
      style={{ height: 110 }}
      option={{
        animation: false,
        grid: { top: 12, right: 6, bottom: 8, left: 6 },
        xAxis: {
          type: "category",
          data: values.map((_, index) => index + 1),
          show: false,
        },
        yAxis: {
          type: "value",
          show: false,
          scale: true,
        },
        series: [
          {
            data: values,
            type: "line",
            smooth: true,
            showSymbol: false,
            lineStyle: { color, width: 3 },
            areaStyle: {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: `${color}55` },
                  { offset: 1, color: `${color}05` },
                ],
              },
            },
          },
        ],
        tooltip: {
          trigger: "axis",
          backgroundColor: "#081018",
          borderColor: "rgba(255,255,255,0.1)",
          textStyle: { color: "#e2e8f0" },
        },
      }}
    />
  )
}

export function BarTrendChart({
  labels,
  values,
  color,
}: {
  labels: string[]
  values: number[]
  color: string
}) {
  return (
    <ReactECharts
      style={{ height: 260 }}
      option={{
        animation: false,
        grid: { top: 18, right: 14, bottom: 30, left: 32 },
        xAxis: {
          type: "category",
          data: labels,
          axisLabel: { color: "#94a3b8" },
          axisLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
        },
        yAxis: {
          type: "value",
          axisLabel: { color: "#94a3b8" },
          splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
        },
        tooltip: {
          trigger: "axis",
          backgroundColor: "#081018",
          borderColor: "rgba(255,255,255,0.1)",
          textStyle: { color: "#e2e8f0" },
        },
        series: [
          {
            type: "bar",
            data: values,
            itemStyle: {
              color,
              borderRadius: [8, 8, 0, 0],
            },
          },
        ],
      }}
    />
  )
}
