import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown } from "lucide-react"

import { BarTrendChart } from "@/components/charts"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { FilterBar } from "@/components/ui/filter-bar"
import { FilterSheet } from "@/components/ui/filter-sheet"
import { TerminalPageHeader } from "@/components/ui/terminal-page-header"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { buildGradingPickColumns, buildTrackRecordPickColumns } from "@/lib/records-columns"
import { api } from "@/lib/api"
import { formatDateTime, formatUnits } from "@/lib/format"
import { mergeTrackRecordEvents, type MergedTrackRecordEvent } from "@/lib/track-record"
import { GRADING_KPI_STRIP_TOOLTIPS } from "@/lib/metric-tooltips"
import { cn } from "@/lib/utils"

/* ── Shared mini-components ─────────────────── */
function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-title">{message}</div>
    </div>
  )
}

/* ── Grading page ───────────────────────────── */
const gradingPickColumns = buildGradingPickColumns()
const trackRecordPickColumns = buildTrackRecordPickColumns()

export function GradingPage() {
  const [pickSource, setPickSource] = useState<"all" | "cockpit" | "lab">("cockpit")
  const gradingHistoryQuery = useQuery({
    queryKey: ["grading-history", pickSource],
    queryFn: () => api.getGradingHistory({ pickSource }),
  })
  const gradingHistory = gradingHistoryQuery.data?.tournaments ?? []
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const labels = gradingHistory
    .slice(0, 8)
    .reverse()
    .map((item) => item.name.replace(/open|championship|invitational/gi, "").trim().split(" ").slice(-1)[0] ?? item.name)
  const profits = gradingHistory
    .slice(0, 8)
    .reverse()
    .map((item) => Number(item.total_profit ?? 0))

  const totalProfit = gradingHistory.reduce((s, t) => s + Number(t.total_profit ?? 0), 0)
  const totalHits = gradingHistory.reduce((s, t) => s + (t.hits ?? 0), 0)
  const totalPicks = gradingHistory.reduce((s, t) => s + (t.graded_pick_count ?? 0), 0)

  const sourceFilters = (
    <>
      <span className="filter-bar-label">Pick source</span>
      {(["cockpit", "lab", "all"] as const).map((value) => (
        <button
          key={value}
          type="button"
          className={`btn ${pickSource === value ? "btn-primary" : "btn-ghost"} btn-sm`}
          onClick={() => setPickSource(value)}
          data-testid={`grading-source-${value}`}
        >
          {value === "cockpit" ? "Dashboard" : value === "lab" ? "Lab" : "All"}
        </button>
      ))}
      {gradingHistoryQuery.isFetching ? (
        <span className="filter-bar-hint">Updating…</span>
      ) : null}
    </>
  )

  return (
    <div className="records-page">
      <TerminalPageHeader
        eyebrow="Records"
        title="Grading history"
        description="Tournament-by-tournament performance tracking."
      />

      <FilterSheet title="Grading filters" description="Pick source for graded history">
        <FilterBar>{sourceFilters}</FilterBar>
      </FilterSheet>

      <div className="kpi-grid">
        <div className="kpi-tile green kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS["Total P&L"]}>
          <div className="kpi-label">Total P&L</div>
          <div className={`kpi-value num ${totalProfit >= 0 ? "green" : ""}`}>{formatUnits(totalProfit)}</div>
        </div>
        <div className="kpi-tile neutral kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS.Tournaments}>
          <div className="kpi-label">Tournaments</div>
          <div className="kpi-value num">{gradingHistory.length}</div>
        </div>
        <div className="kpi-tile neutral kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS["Hit rate"]}>
          <div className="kpi-label">Hit rate</div>
          <div className="kpi-value num">
            {totalPicks > 0 ? `${((totalHits / totalPicks) * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="kpi-detail">{totalHits}/{totalPicks} picks</div>
        </div>
        <div className="kpi-tile gold kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS["Latest event"]}>
          <div className="kpi-label">Latest event</div>
          <div className="kpi-value kpi-value--title">{gradingHistory[0]?.name ?? "—"}</div>
          <div className="kpi-detail">{formatDateTime(gradingHistory[0]?.last_graded_at)}</div>
        </div>
      </div>

      <div className="records-grid-2col">
        <CollapsibleSection
          title="Season P&L trend"
          description="Last 8 graded events"
          defaultOpen={false}
          className="records-chart-collapsible"
        >
          {profits.length > 0 ? (
            <BarTrendChart labels={labels} values={profits} color="#22C55E" />
          ) : (
            <EmptyState message="Grade a tournament to start the season trend view." />
          )}
        </CollapsibleSection>

        <div className="stack-col-8">
          {gradingHistory.map((item) => {
            const id = `${item.event_id}-${item.year}`
            const isExpanded = expandedId === id
            const profit = Number(item.total_profit ?? 0)
            const picks = item.graded_pick_count ?? 0
            const hits = item.hits ?? 0
            const hr = picks > 0 ? `${((hits / picks) * 100).toFixed(0)}%` : "—"

            return (
              <div key={id} className="tr-event">
                <div
                  className="tr-event-header"
                  onClick={() => setExpandedId(isExpanded ? null : id)}
                  data-testid={`grading-event-${id}`}
                >
                  <div className="tr-event-meta">
                    <div className="tr-event-name">{item.name}</div>
                    <div className="tr-event-sub">
                      {hits}/{picks} hits · {hr}
                    </div>
                  </div>
                  <div className="tr-event-actions">
                    <span
                      className={cn(
                        "tr-event-profit",
                        profit >= 0 ? "tr-event-profit--pos" : "tr-event-profit--neg",
                      )}
                    >
                      {formatUnits(profit)}
                    </span>
                    <ChevronDown
                      size={13}
                      className={cn("tr-event-chevron", isExpanded && "tr-event-chevron--open")}
                    />
                  </div>
                </div>
                {isExpanded && (
                  <div className="tr-event-body">
                    <div className="records-event-kpi-row">
                      <div className="kpi-tile neutral kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS.Course}>
                        <div className="kpi-label">Course</div>
                        <div className="kpi-value kpi-value--sm">{item.course ?? "—"}</div>
                      </div>
                      <div className="kpi-tile neutral kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS.Year}>
                        <div className="kpi-label">Year</div>
                        <div className="kpi-value num kpi-value--md">{item.year ?? "—"}</div>
                      </div>
                    </div>
                    {(item.picks?.length ?? 0) > 0 && (
                      <div className="records-picks-grid">
                        <ProDataGrid
                          data={item.picks ?? []}
                          columns={gradingPickColumns}
                          getRowId={(row) => `${row.player_display}-${row.opponent_display ?? "solo"}`}
                          density="compact"
                          testId={`grading-picks-${id}`}
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
          {gradingHistory.length === 0 && (
            <div className="card">
              <div className="card-body">
                <EmptyState message="No graded events yet." />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Track Record page ──────────────────────── */
export function TrackRecordPage() {
  const trackRecordQuery = useQuery({
    queryKey: ["track-record"],
    queryFn: api.getTrackRecord,
  })

  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const mergedResult = mergeTrackRecordEvents(trackRecordQuery.data?.events ?? [])
  // mergeTrackRecordEvents returns { events, totals } — never a plain array
  const events: MergedTrackRecordEvent[] = Array.isArray(mergedResult)
    ? (mergedResult as MergedTrackRecordEvent[])
    : ((mergedResult as { events: MergedTrackRecordEvent[] }).events ?? [])

  // MergedTrackRecordEvent fields: name, course, wins, losses, pushes, profit, picks[]
  const totalProfit = events.reduce((s, e) => s + Number(e.profit ?? 0), 0)
  const totalWins   = events.reduce((s, e) => s + (e.wins ?? 0), 0)
  const totalPicks  = events.reduce((s, e) => s + (e.wins ?? 0) + (e.losses ?? 0) + (e.pushes ?? 0), 0)

  if (trackRecordQuery.isLoading) {
    return (
      <div className="records-loading">Loading track record…</div>
    )
  }

  return (
    <div className="records-page">
      <TerminalPageHeader
        eyebrow="Records"
        title="Track record"
        description="Full historical model performance across all graded tournaments."
      />

      <div className="kpi-grid">
        <div
          className={cn("kpi-tile kpi-tile--help", totalProfit >= 0 ? "green" : "neutral")}
          title={GRADING_KPI_STRIP_TOOLTIPS["Total P&L"]}
        >
          <div className="kpi-label">Total P&L</div>
          <div className={`kpi-value num ${totalProfit >= 0 ? "green" : ""}`}>{formatUnits(totalProfit)}</div>
          <div className="kpi-detail">all tournaments</div>
        </div>
        <div className="kpi-tile neutral kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS.Tournaments}>
          <div className="kpi-label">Tournaments</div>
          <div className="kpi-value num">{events.length}</div>
        </div>
        <div className="kpi-tile neutral kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS["Win rate"]}>
          <div className="kpi-label">Win rate</div>
          <div className="kpi-value num">
            {totalPicks > 0 ? `${((totalWins / totalPicks) * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="kpi-detail">{totalWins}/{totalPicks} picks</div>
        </div>
        <div className="kpi-tile gold kpi-tile--help" title={GRADING_KPI_STRIP_TOOLTIPS.Wins}>
          <div className="kpi-label">Wins</div>
          <div className="kpi-value num gold">{totalWins}</div>
          <div className="kpi-detail">outright picks won</div>
        </div>
      </div>

      <div className="records-event-stack">
        {events.length > 0 ? (
          events.map((event, idx) => {
            // Use index as key — MergedTrackRecordEvent has no id field
            const isExpanded = expandedIdx === idx
            const profit = Number(event.profit ?? 0)
            const picks = event.picks ?? []
            const eventTotal = (event.wins ?? 0) + (event.losses ?? 0) + (event.pushes ?? 0)
            const hr = eventTotal > 0
              ? `${(((event.wins ?? 0) / eventTotal) * 100).toFixed(0)}%`
              : "—"

            return (
              <div key={`${event.name}-${idx}`} className="tr-event">
                <div
                  className="tr-event-header"
                  onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                  data-testid={`track-record-event-${idx}`}
                >
                  <div className="tr-event-meta">
                    <div className="tr-event-name">{event.name}</div>
                    <div className="tr-event-sub">
                      {event.wins ?? 0}W / {event.losses ?? 0}L / {event.pushes ?? 0}P · {hr}
                      {event.course ? ` · ${event.course}` : ""}
                    </div>
                  </div>
                  <div className="tr-event-actions">
                    <span
                      className={cn(
                        "tr-event-profit",
                        profit >= 0 ? "tr-event-profit--pos" : "tr-event-profit--neg",
                      )}
                    >
                      {formatUnits(profit)}
                    </span>
                    <ChevronDown
                      size={13}
                      className={cn("tr-event-chevron", isExpanded && "tr-event-chevron--open")}
                    />
                  </div>
                </div>

                {isExpanded && picks.length > 0 && (
                  <div className="tr-event-body">
                    <ProDataGrid
                      data={picks}
                      columns={trackRecordPickColumns}
                      getRowId={(row) => `${row.pick}-${row.opponent}-${row.odds}`}
                      getRowTestId={(row) => `pick-row-${row.pick}`}
                      density="compact"
                      testId={`track-record-picks-${idx}`}
                    />
                  </div>
                )}

                {isExpanded && picks.length === 0 && (
                  <div className="tr-event-body">
                    <EmptyState message="No pick detail available for this tournament." />
                  </div>
                )}
              </div>
            )
          })
        ) : (
          <div className="card">
            <div className="card-body">
              <EmptyState message="No track record data yet. Grade tournaments to build your history." />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
