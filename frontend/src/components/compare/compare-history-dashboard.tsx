import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { MarketDeltaChartLazy } from "@/components/compare/compare-charts-lazy"
import { CompareSeasonEventsTable } from "@/components/compare/compare-season-events-table"
import { MetricCell, TrackMetricsCard } from "@/components/compare/track-metrics-card"
import { api } from "@/lib/api"
import type { TrackMetrics } from "@/lib/types"

type CompareWindow = "30d" | "90d" | "season"

const WINDOWS: CompareWindow[] = ["30d", "90d", "season"]

function MarketBreakdownTable({
  byMarket,
}: {
  byMarket: Record<string, Record<string, TrackMetrics>> | undefined
}) {
  const markets = useMemo(() => {
    const keys = new Set<string>()
    for (const track of Object.values(byMarket ?? {})) {
      for (const market of Object.keys(track)) keys.add(market)
    }
    return [...keys].sort()
  }, [byMarket])

  if (markets.length === 0) {
    return (
      <p className="text-sm text-[var(--text-secondary)]">No per-market breakdown for this window.</p>
    )
  }

  return (
    <div className="compare-table-wrap overflow-x-auto">
      <table className="compare-data-table w-full min-w-[560px] text-sm" data-testid="compare-market-breakdown-table">
        <thead>
          <tr className="text-left text-[var(--text-secondary)]">
            <th className="py-2 pr-4 font-semibold">Market</th>
            <th className="py-2 pr-4 font-semibold num">Champ ROI</th>
            <th className="py-2 pr-4 font-semibold num">Chlgr ROI</th>
            <th className="py-2 pr-4 font-semibold num">Δ ROI</th>
            <th className="py-2 pr-4 font-semibold num">Champ hit%</th>
            <th className="py-2 pr-4 font-semibold num">Chlgr hit%</th>
            <th className="py-2 pr-2 font-semibold num">Δ hit%</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((market) => {
            const champ = byMarket?.cockpit?.[market]
            const lab = byMarket?.lab?.[market]
            const roiDelta =
              champ?.roi_pct != null && lab?.roi_pct != null ? lab.roi_pct - champ.roi_pct : null
            const hitDelta =
              champ?.hit_rate_pct != null && lab?.hit_rate_pct != null
                ? lab.hit_rate_pct - champ.hit_rate_pct
                : null
            return (
              <tr key={market} className="border-t border-[var(--border)]">
                <td className="py-2 pr-4 capitalize text-[var(--text-primary)]">{market}</td>
                <td className="py-2 pr-4 num">{champ?.roi_pct ?? "—"}</td>
                <td className="py-2 pr-4 num">{lab?.roi_pct ?? "—"}</td>
                <td className="py-2 pr-4 num">
                  {roiDelta == null ? "—" : `${roiDelta > 0 ? "+" : ""}${roiDelta.toFixed(2)}`}
                </td>
                <td className="py-2 pr-4 num">{champ?.hit_rate_pct ?? "—"}</td>
                <td className="py-2 pr-4 num">{lab?.hit_rate_pct ?? "—"}</td>
                <td className="py-2 pr-2 num">
                  {hitDelta == null ? "—" : `${hitDelta > 0 ? "+" : ""}${hitDelta.toFixed(2)}`}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function CompareHistoryDashboard({
  onSelectEvent,
}: {
  onSelectEvent?: (eventId: string) => void
}) {
  const [window, setWindow] = useState<CompareWindow>("30d")
  const query = useQuery({
    queryKey: ["track-comparison", window],
    queryFn: () => api.getTrackComparison(window),
    refetchInterval: 60_000,
  })
  const seasonQuery = useQuery({
    queryKey: ["compare-grading-season"],
    queryFn: () => api.getGradingSeason({ lane: "all", includePicks: false, limit: 200 }),
    staleTime: 60_000,
  })
  const data = query.data

  const chartData = useMemo(() => {
    const markets = new Set<string>()
    for (const track of Object.values(data?.by_market ?? {})) {
      for (const market of Object.keys(track)) markets.add(market)
    }
    const labels = [...markets].sort()
    return {
      labels,
      championValues: labels.map((m) => data?.by_market?.cockpit?.[m]?.roi_pct ?? 0),
      challengerValues: labels.map((m) => data?.by_market?.lab?.[m]?.roi_pct ?? 0),
    }
  }, [data?.by_market])

  return (
    <div className="compare-dashboard flex flex-col gap-6" data-testid="compare-history-dashboard">
      <section className="card compare-panel" data-testid="compare-season-events-section">
        <div className="card-header">
          <div className="card-title">Season by event</div>
          <div className="text-xs text-[var(--text-secondary)]">
            Aggregate and per-tournament graded performance for both tracks
          </div>
        </div>
        <div className="card-body">
          <CompareSeasonEventsTable season={seasonQuery.data} onSelectEvent={onSelectEvent} />
        </div>
      </section>

      <div className="flex items-center gap-2" role="group" aria-label="Track record window">
        {WINDOWS.map((w) => (
          <button
            key={w}
            type="button"
            className={`filter-chip${window === w ? " active" : ""}`}
            onClick={() => setWindow(w)}
            data-testid={`compare-window-${w}`}
            aria-pressed={window === w}
          >
            {w}
          </button>
        ))}
      </div>

      <p className="text-sm text-[var(--text-secondary)]">{data?.note ?? "Loading track record…"}</p>

      <div className="grid gap-4 md:grid-cols-2">
        <TrackMetricsCard track="dashboard" metrics={data?.tracks?.cockpit} />
        <TrackMetricsCard track="lab" metrics={data?.tracks?.lab} />
      </div>

      <section className="card compare-panel" data-testid="compare-history-market-chart">
        <div className="card-header">
          <div className="card-title">ROI by market</div>
        </div>
        <div className="card-body">
          <MarketDeltaChartLazy
            labels={chartData.labels}
            championValues={chartData.championValues}
            challengerValues={chartData.challengerValues}
            suffix="%"
          />
        </div>
      </section>

      <section className="card compare-panel" data-testid="compare-history-market-table">
        <div className="card-header">
          <div className="card-title">Market breakdown</div>
        </div>
        <div className="card-body">
          <MarketBreakdownTable byMarket={data?.by_market} />
        </div>
      </section>

      <section className="card compare-panel" data-testid="compare-history-overlap">
        <div className="card-header">
          <div className="card-title">Pick overlap (graded window)</div>
        </div>
        <div className="card-body grid grid-cols-3 gap-3 text-center">
          <MetricCell label="Both" value={data?.overlap?.both ?? null} />
          <MetricCell label="Champion only" value={data?.overlap?.cockpit_only ?? null} />
          <MetricCell label="Challenger only" value={data?.overlap?.lab_only ?? null} />
        </div>
      </section>
    </div>
  )
}
