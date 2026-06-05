import { lazy, Suspense } from "react"

const LazyBarTrendChart = lazy(() =>
  import("@/components/charts").then((mod) => ({ default: mod.BarTrendChart })),
)

type BarTrendChartProps = {
  labels: string[]
  values: number[]
  color?: string
  height?: number
}

function ChartSkeleton({ height = 120 }: { height?: number }) {
  return (
    <div
      className="chart-lazy-skeleton"
      data-testid="chart-lazy-skeleton"
      style={{ height, background: "var(--bg-1)", borderRadius: 8 }}
      role="status"
      aria-label="Loading chart"
    />
  )
}

/** Code-splits echarts until a grading / track-record chart mounts. */
export function BarTrendChartLazy(props: BarTrendChartProps) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 120} />}>
      <LazyBarTrendChart {...props} />
    </Suspense>
  )
}
