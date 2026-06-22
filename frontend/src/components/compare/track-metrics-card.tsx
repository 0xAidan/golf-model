import { TrackBadge } from "@/components/product/track-badge"
import type { TrackMetrics } from "@/lib/types"

function MetricCell({
  label,
  value,
  suffix = "",
}: {
  label: string
  value: number | null
  suffix?: string
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-[var(--text-faint)]">{label}</div>
      <div className="num text-lg text-[var(--text-primary)]">
        {value == null ? "—" : `${value}${suffix}`}
      </div>
    </div>
  )
}

export function TrackMetricsCard({
  track,
  metrics,
}: {
  track: "dashboard" | "lab"
  metrics?: TrackMetrics
}) {
  return (
    <section className="card" data-testid={`track-metrics-${track}`}>
      <div className="card-header flex items-center gap-2">
        <TrackBadge track={track} />
        {metrics?.low_sample ? (
          <span className="text-xs text-[var(--amber,#d97706)]" data-testid={`low-sample-${track}`}>
            low sample (n&lt;30)
          </span>
        ) : null}
      </div>
      <div className="card-body grid grid-cols-3 gap-3">
        <MetricCell label="Bets" value={metrics?.n ?? null} />
        <MetricCell label="Hit rate" value={metrics?.hit_rate_pct ?? null} suffix="%" />
        <MetricCell label="ROI (1u)" value={metrics?.roi_pct ?? null} suffix="%" />
        <MetricCell label="P/L (u)" value={metrics?.pnl_units ?? null} />
        <MetricCell label="Brier" value={metrics?.brier ?? null} />
        <MetricCell label="Wins" value={metrics?.wins ?? null} />
      </div>
    </section>
  )
}

export { MetricCell }
