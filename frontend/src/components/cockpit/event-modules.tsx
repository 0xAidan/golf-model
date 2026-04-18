import { CircleAlert, History, Radar, ShieldAlert } from "lucide-react"

import { MetricTile } from "@/components/shell"
import type {
  CockpitFeedItemModel,
  CockpitLeaderboardRowModel,
  CockpitMarketIntelRowModel,
  CockpitMetricModel,
  CockpitReasonCodeModel,
  CockpitReplayItemModel,
  CockpitSelectedEventSummary,
} from "@/lib/cockpit-event-models"

export function CourseWeatherFeedPanel({
  metrics,
  feedItems,
}: {
  metrics: CockpitMetricModel[]
  feedItems: CockpitFeedItemModel[]
}) {
  return (
    <div className="space-y-4">
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns="sm:grid-cols-1" /> : null}
      <div className="space-y-3">
        {feedItems.map((item) => (
          <div key={`${item.label}-${item.detail}`} className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
            <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{item.label}</p>
            <p className="mt-2 text-sm leading-6 text-slate-300">{item.detail}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function LeaderboardPanel({
  metrics,
  rows,
  seededFromRankings,
  emptyMessage,
  onPlayerSelect,
}: {
  metrics: CockpitMetricModel[]
  rows: CockpitLeaderboardRowModel[]
  seededFromRankings: boolean
  emptyMessage: string | null
  onPlayerSelect: (playerKey: string) => void
}) {
  if (rows.length === 0) {
    return <PanelEmptyState icon={Radar} message={emptyMessage ?? "No leaderboard rows are available yet."} />
  }

  return (
    <div className="space-y-4">
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns="md:grid-cols-3" /> : null}
      {seededFromRankings ? (
        <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100">
          Pre-tournament board seeded from model rankings. Live scores will replace this once the event starts.
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm" role="grid">
          <thead>
            <tr className="border-b border-white/10 text-left text-[10px] uppercase tracking-[0.16em] text-slate-500">
              <th className="px-3 py-2 font-medium">Pos</th>
              <th className="px-3 py-2 font-medium">Player</th>
              <th className="px-3 py-2 text-right font-medium">State</th>
              <th className="px-3 py-2 text-right font-medium">Round</th>
              <th className="px-3 py-2 text-right font-medium">Score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.positionLabel}-${row.playerLabel}`} className="border-t border-white/6 transition hover:bg-white/5">
                <td className="px-3 py-2.5 text-slate-400">{row.positionLabel}</td>
                <td className="px-3 py-2.5">
                  <SelectableInlinePlayer playerKey={row.playerKey} label={row.playerLabel} onPlayerSelect={onPlayerSelect} />
                  {row.detail ? <p className="mt-1 text-xs text-slate-500">{row.detail}</p> : null}
                </td>
                <td className="px-3 py-2.5 text-right text-cyan-200">{row.toParLabel}</td>
                <td className="px-3 py-2.5 text-right text-slate-300">{row.roundLabel}</td>
                <td className="px-3 py-2.5 text-right text-slate-300">{row.scoreLabel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function MarketIntelPanel({
  metrics,
  rows,
  emptyMessage,
  onPlayerSelect,
}: {
  metrics: CockpitMetricModel[]
  rows: CockpitMarketIntelRowModel[]
  emptyMessage: string | null
  onPlayerSelect: (playerKey: string) => void
}) {
  if (rows.length === 0) {
    return <PanelEmptyState icon={CircleAlert} message={emptyMessage ?? "No market intel rows are available yet."} />
  }

  return (
    <div className="space-y-4">
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns="md:grid-cols-3" /> : null}
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={`${row.eyebrow}-${row.label}-${row.priceLabel}`} className="rounded-xl border border-white/8 bg-black/20 px-4 py-3">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">{row.eyebrow}</p>
                <p className="mt-1 text-sm font-medium text-white">
                  <SelectableInlinePlayer playerKey={row.playerKey} label={row.label} onPlayerSelect={onPlayerSelect} />
                </p>
                <p className="mt-1 text-xs text-slate-500">{row.detail}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-cyan-200">{row.edgeLabel}</p>
                <p className="text-xs text-slate-500">{row.priceLabel}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ReplayTimelinePanel({
  metrics,
  items,
  emptyMessage,
}: {
  metrics: CockpitMetricModel[]
  items: CockpitReplayItemModel[]
  emptyMessage: string | null
}) {
  return (
    <div className="space-y-4">
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns="md:grid-cols-3" /> : null}
      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={`${item.label}-${item.detail}`} className="rounded-xl border border-white/8 bg-black/20 px-4 py-3">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{item.label}</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">{item.detail}</p>
            </div>
          ))}
        </div>
      ) : null}
      {emptyMessage ? <PanelEmptyState icon={History} message={emptyMessage} /> : null}
    </div>
  )
}

export function DiagnosticsGradingPanel({
  metrics,
  counters,
  reasonCodes,
  warnings,
  selectedEventSummary,
}: {
  metrics: CockpitMetricModel[]
  counters: string[]
  reasonCodes: CockpitReasonCodeModel[]
  warnings: string[]
  selectedEventSummary: CockpitSelectedEventSummary | null
}) {
  return (
    <div className="space-y-4">
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns="sm:grid-cols-2" /> : null}

      <div className="rounded-xl border border-white/8 bg-black/20 p-4">
        <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Diagnostic counters</p>
        <div className="mt-3 grid gap-2 text-sm text-slate-300">
          {counters.map((counter) => (
            <p key={counter}>{counter}</p>
          ))}
        </div>
      </div>

      {reasonCodes.length > 0 ? (
        <div className="rounded-xl border border-white/8 bg-black/20 p-4">
          <div className="mb-3 flex items-center gap-2 text-slate-200">
            <ShieldAlert className="h-4 w-4 text-cyan-200" />
            <p className="text-sm font-semibold">Top exclusion reasons</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {reasonCodes.map((reasonCode) => (
              <span
                key={`${reasonCode.label}-${reasonCode.count}`}
                className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300"
              >
                {reasonCode.label} · {reasonCode.count}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <div className="rounded-xl border border-amber-400/25 bg-amber-500/10 p-3 text-sm text-amber-100">
          {warnings.join(" ")}
        </div>
      ) : null}

      <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Selected event grading context</p>
        {selectedEventSummary ? (
          <div className="mt-3 rounded-xl border border-white/6 bg-black/15 px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="truncate text-sm text-white">{selectedEventSummary.name}</p>
                <p className="text-xs text-slate-500">{selectedEventSummary.hitsLabel}</p>
              </div>
              <p className="text-sm font-semibold text-emerald-300">{selectedEventSummary.profitLabel}</p>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Grade a matching event to attach direct replay-to-results context here.
          </p>
        )}
      </div>
    </div>
  )
}

function MetricGrid({
  metrics,
  columns,
}: {
  metrics: CockpitMetricModel[]
  columns: string
}) {
  return (
    <div className={`grid gap-3 ${columns}`}>
      {metrics.map((metric) => (
        <MetricTile
          key={`${metric.label}-${metric.value}`}
          label={metric.label}
          value={metric.value}
          detail={metric.detail}
          tone={metric.tone}
        />
      ))}
    </div>
  )
}

function SelectableInlinePlayer({
  playerKey,
  label,
  onPlayerSelect,
}: {
  playerKey?: string | null
  label: string
  onPlayerSelect: (playerKey: string) => void
}) {
  if (!playerKey) {
    return <span>{label}</span>
  }

  return (
    <button
      type="button"
      onClick={() => onPlayerSelect(playerKey)}
      className="text-left underline decoration-transparent underline-offset-4 transition hover:text-cyan-200 hover:decoration-cyan-300"
    >
      {label}
    </button>
  )
}

function PanelEmptyState({
  icon: Icon,
  message,
}: {
  icon: typeof Radar
  message: string
}) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-4 py-8 text-center text-sm text-slate-400">
      <Icon className="mx-auto mb-3 h-6 w-6 text-slate-600" />
      {message}
    </div>
  )
}
