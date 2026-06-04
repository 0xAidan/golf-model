import { CircleAlert, History, Radar, ShieldAlert } from "lucide-react"
import { useMemo } from "react"

import { MetricTile } from "@/components/shell"
import { PanelChrome } from "@/components/ui/panel-chrome"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { buildLeaderboardColumns } from "@/lib/cockpit-columns"
import { COCKPIT_METRIC_TOOLTIPS } from "@/lib/metric-tooltips"
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
    <PanelChrome
      title="Course & weather"
      description="Conditions and feed context"
      className="panel-chrome--course-weather"
    >
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={3} /> : null}
      <div>
        {feedItems.map((item) => (
          <div key={`${item.label}-${item.detail}`} className="term-row">
            <span className="term-row-eye">{item.label}</span>
            <span className="term-row-det">{item.detail}</span>
          </div>
        ))}
      </div>
    </PanelChrome>
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
  const columns = useMemo(() => buildLeaderboardColumns({ onPlayerSelect }), [onPlayerSelect])

  if (rows.length === 0) {
    return <PanelEmptyState icon={Radar} message={emptyMessage ?? "No leaderboard rows available."} />
  }

  return (
    <div>
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={3} /> : null}
      {seededFromRankings ? (
        <div className="term-notice term-notice--inset">
          Pre-tournament board seeded from model rankings. Live scores replace this once the event starts.
        </div>
      ) : (
        <div className="term-notice term-notice--inset">
          Tournament scoring view: Pos / Start pos / Pos Δ track movement alongside the model board.
        </div>
      )}
      <ProDataGrid
        data={rows}
        columns={columns}
        density="compact"
        getRowId={(row) => `${row.positionLabel}-${row.playerLabel}`}
        getRowTestId={(row) =>
          row.playerKey ? `leaderboard-row-${row.playerKey}` : undefined
        }
        testId="cockpit-leaderboard-grid"
      />
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
    return <PanelEmptyState icon={CircleAlert} message={emptyMessage ?? "No market intel rows available."} />
  }

  return (
    <PanelChrome
      title="Market intel"
      description="Model vs market divergence"
      className="panel-chrome--market-intel"
    >
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={3} /> : null}
      <div>
        {rows.map((row) => (
          <div key={`${row.eyebrow}-${row.label}-${row.priceLabel}`} className="term-row">
            <div className="term-row-split">
              <div className="term-row-split-left">
                <span className="term-row-eye">{row.eyebrow}</span>
                <div className="term-row-val term-row-val-mt">
                  <SelectableInlinePlayer playerKey={row.playerKey} label={row.label} onPlayerSelect={onPlayerSelect} />
                </div>
                {row.detail ? <span className="term-row-det">{row.detail}</span> : null}
              </div>
              <div className="term-row-split-right">
                <div className="term-row-edge">{row.edgeLabel}</div>
                <div className="term-row-price">{row.priceLabel}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </PanelChrome>
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
    <div>
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={3} /> : null}
      {items.length > 0 ? (
        <div>
          {items.map((item) => (
            <div key={`${item.label}-${item.detail}`} className="term-row">
              <span className="term-row-eye">{item.label}</span>
              <span className="term-row-det">{item.detail}</span>
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
    <div>
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={2} /> : null}

      {/* Diagnostic counters */}
      <div className="term-section-head">Diagnostic Counters</div>
      <div>
        {counters.map((counter) => (
          <div key={counter} className="term-row">
            <span className="term-row-det">{counter}</span>
          </div>
        ))}
      </div>

      {reasonCodes.length > 0 ? (
        <>
          <div className="term-section-head" style={{ marginTop: "8px" }}>
            <ShieldAlert style={{ width: 9, height: 9, color: "var(--text-secondary)" }} />
            Top Exclusion Reasons
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", padding: "6px 10px" }}>
            {reasonCodes.map((reasonCode) => (
              <span
                key={`${reasonCode.label}-${reasonCode.count}`}
                className="tier-badge"
              >
                {reasonCode.label} · {reasonCode.count}
              </span>
            ))}
          </div>
        </>
      ) : null}

      {warnings.length > 0 ? (
        <div className="term-notice amber" style={{ margin: "6px 8px" }}>
          {warnings.join(" ")}
        </div>
      ) : null}

      {/* Selected event grading context */}
      <div className="term-section-head" style={{ marginTop: "8px" }}>Selected Event Context</div>
      {selectedEventSummary ? (
        <div className="term-row">
          <div className="term-row-split">
            <div className="term-row-split-left">
              <span className="term-row-val">{selectedEventSummary.name}</span>
              <span className="term-row-det">{selectedEventSummary.hitsLabel}</span>
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700, color: "var(--green)" }}>
              {selectedEventSummary.profitLabel}
            </div>
          </div>
        </div>
      ) : (
        <div className="term-row">
          <span className="term-row-det">Grade a matching event to attach replay-to-results context here.</span>
        </div>
      )}
    </div>
  )
}

function MetricGrid({
  metrics,
  columns,
}: {
  metrics: CockpitMetricModel[]
  columns: number
}) {
  const gridTemplateColumns =
    columns === 1
      ? "1fr"
      : columns === 2
        ? "repeat(auto-fit, minmax(110px, 1fr))"
        : "repeat(auto-fit, minmax(84px, 1fr))"

  return (
    <div style={{ display: "grid", gridTemplateColumns, gap: "4px", padding: "8px" }}>
      {metrics.map((metric) => (
        <MetricTile
          key={`${metric.label}-${metric.value}`}
          label={metric.label}
          value={metric.value}
          detail={metric.detail}
          tone={metric.tone}
          title={COCKPIT_METRIC_TOOLTIPS[metric.label]}
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
      className="player-btn"
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
    <div className="panel-empty">
      <Icon style={{ width: 16, height: 16 }} />
      <span>{message}</span>
    </div>
  )
}
