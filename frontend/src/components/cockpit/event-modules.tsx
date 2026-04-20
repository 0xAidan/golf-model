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
    <div>
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={1} /> : null}
      <div>
        {feedItems.map((item) => (
          <div key={`${item.label}-${item.detail}`} className="term-row">
            <span className="term-row-eye">{item.label}</span>
            <span className="term-row-det">{item.detail}</span>
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
    return <PanelEmptyState icon={Radar} message={emptyMessage ?? "No leaderboard rows available."} />
  }

  return (
    <div>
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={3} /> : null}
      {seededFromRankings ? (
        <div className="term-notice" style={{ margin: "6px 8px" }}>
          Pre-tournament board seeded from model rankings. Live scores replace this once the event starts.
        </div>
      ) : null}
      <div className="table-scroll">
        <table className="data-table" role="grid">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th style={{ textAlign: "right" }}>Score</th>
              <th style={{ textAlign: "right" }}>Rd</th>
              <th style={{ textAlign: "right" }}>Tot</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.positionLabel}-${row.playerLabel}`}>
                <td style={{ color: "var(--text-muted)" }}>{row.positionLabel}</td>
                <td>
                  <SelectableInlinePlayer playerKey={row.playerKey} label={row.playerLabel} onPlayerSelect={onPlayerSelect} />
                  {row.detail ? <div style={{ fontSize: "9px", color: "var(--text-faint)", marginTop: "1px" }}>{row.detail}</div> : null}
                </td>
                <td style={{ textAlign: "right", color: "var(--cyan)", fontFamily: "var(--font-mono)" }}>{row.toParLabel}</td>
                <td style={{ textAlign: "right" }}>{row.roundLabel}</td>
                <td style={{ textAlign: "right" }}>{row.scoreLabel}</td>
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
    return <PanelEmptyState icon={CircleAlert} message={emptyMessage ?? "No market intel rows available."} />
  }

  return (
    <div>
      {metrics.length > 0 ? <MetricGrid metrics={metrics} columns={3} /> : null}
      <div>
        {rows.map((row) => (
          <div key={`${row.eyebrow}-${row.label}-${row.priceLabel}`} className="term-row">
            <div className="term-row-split">
              <div className="term-row-split-left">
                <span className="term-row-eye">{row.eyebrow}</span>
                <div className="term-row-val" style={{ marginTop: "2px" }}>
                  <SelectableInlinePlayer playerKey={row.playerKey} label={row.label} onPlayerSelect={onPlayerSelect} />
                </div>
                {row.detail ? <span className="term-row-det">{row.detail}</span> : null}
              </div>
              <div className="term-row-split-right">
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700, color: "var(--cyan)" }}>{row.edgeLabel}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--text-faint)", marginTop: "1px" }}>{row.priceLabel}</div>
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
            <ShieldAlert style={{ width: 9, height: 9, color: "var(--cyan)" }} />
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
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${columns}, 1fr)`, gap: "4px", padding: "8px" }}>
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
