import { lazy, Suspense, type ReactNode } from "react"

import type { ComponentDriverSummary } from "@/components/compare/compare-types"
import type { RankScatterPoint } from "@/components/compare/compare-types"

const LazyRankScatterChart = lazy(() =>
  import("@/components/compare/compare-charts").then((mod) => ({ default: mod.RankScatterChart })),
)

const LazyComponentDriversChart = lazy(() =>
  import("@/components/compare/compare-charts").then((mod) => ({
    default: mod.ComponentDriversChart,
  })),
)

const LazyMarketDeltaChart = lazy(() =>
  import("@/components/compare/compare-charts").then((mod) => ({ default: mod.MarketDeltaChart })),
)

function ChartSkeleton({ height = 220 }: { height?: number }) {
  return (
    <div
      className="chart-lazy-skeleton"
      data-testid="compare-chart-skeleton"
      style={{ height, background: "var(--bg-1)", borderRadius: 8 }}
      role="status"
      aria-label="Loading chart"
    />
  )
}

function ChartSuspense({ height, children }: { height?: number; children: ReactNode }) {
  return <Suspense fallback={<ChartSkeleton height={height} />}>{children}</Suspense>
}

export function RankScatterChartLazy(props: {
  points: RankScatterPoint[]
  height?: number
  highlightedKey?: string | null
  onPointClick?: (playerKey: string) => void
}) {
  return (
    <ChartSuspense height={props.height ?? 280}>
      <LazyRankScatterChart {...props} />
    </ChartSuspense>
  )
}

export function ComponentDriversChartLazy(props: {
  summary: ComponentDriverSummary
  height?: number
}) {
  return (
    <ChartSuspense height={props.height ?? 200}>
      <LazyComponentDriversChart {...props} />
    </ChartSuspense>
  )
}

export function MarketDeltaChartLazy(props: {
  labels: string[]
  championValues: number[]
  challengerValues: number[]
  height?: number
  suffix?: string
}) {
  return (
    <ChartSuspense height={props.height ?? 200}>
      <LazyMarketDeltaChart {...props} />
    </ChartSuspense>
  )
}
