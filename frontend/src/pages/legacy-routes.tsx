import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown } from "lucide-react"

import { BarTrendChart } from "@/components/charts"
import {
  BentoGrid,
  BentoPanel,
  GradingTrustStrip,
  HeroBand,
  HeroDataGrid,
  MacroKpiStrip,
  type MacroKpiItem,
} from "@/components/monitoring"
import { CollapsibleSection } from "@/components/ui/collapsible-section"
import { buildGradingPickColumns, buildTrackRecordPickColumns } from "@/lib/records-columns"
import { api } from "@/lib/api"
import { formatDateTime, formatUnits } from "@/lib/format"
import { buildGradingTrustMetrics } from "@/lib/grading-trust"
import { formatSeasonEventDate, laneStatusLabel, seasonEventsToGradingHistory, seasonLaneFromPickSource } from "@/lib/grading-season"
import type { GradingSeasonEvent } from "@/lib/types"
import { mergeTrackRecordEvents, type MergedTrackRecordEvent } from "@/lib/track-record"
import { GRADING_KPI_STRIP_TOOLTIPS } from "@/lib/metric-tooltips"
import { cn } from "@/lib/utils"

function RecordsEmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-title">{message}</div>
    </div>
  )
}

const gradingPickColumns = buildGradingPickColumns()
const trackRecordPickColumns = buildTrackRecordPickColumns()

export function GradingPage() {
  const [pickSource, setPickSource] = useState<"all" | "cockpit" | "lab">("cockpit")
  const seasonQuery = useQuery({
    queryKey: ["grading-season", pickSource],
    queryFn: () =>
      api.getGradingSeason({
        year: 2026,
        lane: seasonLaneFromPickSource(pickSource),
        includePicks: true,
        limit: 100,
      }),
  })
  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    staleTime: 60_000,
  })
  const gradingHistoryData = useMemo(
    () => seasonEventsToGradingHistory(seasonQuery.data, pickSource),
    [seasonQuery.data, pickSource],
  )
  const trustMetrics = useMemo(
    () => buildGradingTrustMetrics(gradingHistoryData, dashboardQuery.data),
    [gradingHistoryData, dashboardQuery.data],
  )

  const gradingHistory = gradingHistoryData.tournaments ?? []
  const seasonEvents: GradingSeasonEvent[] = seasonQuery.data?.events ?? []
  const seasonSummary = seasonQuery.data?.summary
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

  const summaryKpis = useMemo((): MacroKpiItem[] => {
    if (pickSource === "all" && seasonSummary) {
      return [
        {
          id: "dash-pnl",
          label: "Dashboard P&L",
          value: formatUnits(seasonSummary.dashboard.profit),
          tone: seasonSummary.dashboard.profit >= 0 ? "positive" : "negative",
        },
        {
          id: "lab-pnl",
          label: "Lab P&L",
          value: formatUnits(seasonSummary.lab.profit),
          tone: seasonSummary.lab.profit >= 0 ? "positive" : "negative",
        },
        {
          id: "events",
          label: "Tournaments",
          value: String(gradingHistory.length),
        },
        {
          id: "overlap",
          label: "Overlap matchups",
          value: String(seasonSummary.comparison.overlap_matchups),
        },
      ]
    }

    return [
      {
        id: "pnl",
        label: "Total P&L",
        value: formatUnits(totalProfit),
        tone: totalProfit >= 0 ? "positive" : "negative",
      },
      {
        id: "events",
        label: "Tournaments",
        value: String(gradingHistory.length),
      },
      {
        id: "hit-rate",
        label: "Hit rate",
        value: totalPicks > 0 ? `${((totalHits / totalPicks) * 100).toFixed(0)}%` : "—",
        suffix: totalPicks > 0 ? `${totalHits}/${totalPicks}` : undefined,
      },
      {
        id: "latest",
        label: "Latest event",
        value: gradingHistory[0]?.name ?? "—",
        suffix: gradingHistory[0]?.last_graded_at
          ? formatDateTime(gradingHistory[0].last_graded_at)
          : undefined,
      },
    ]
  }, [gradingHistory, pickSource, seasonSummary, totalHits, totalPicks, totalProfit])

  return (
    <div className="monitor-records-page monitor-scroll-region" data-testid="grading-page">
      <HeroBand
        eyebrow="Records"
        title="Grading history"
        meta="2026 season — Dashboard vs Lab (+EV picks only). Use All to compare both models."
      />

      <GradingTrustStrip
        metrics={trustMetrics}
        pickSource={pickSource}
        onPickSourceChange={setPickSource}
        isFetching={seasonQuery.isFetching}
      />

      <MacroKpiStrip items={summaryKpis} testId="grading-summary-kpis" />

      <BentoGrid columns={2} testId="grading-bento">
        <BentoPanel title="Season P&L trend" span={6}>
          {profits.length > 0 ? (
            <BarTrendChart labels={labels} values={profits} color="#22C55E" />
          ) : (
            <RecordsEmptyState message="Grade a tournament to start the season trend view." />
          )}
        </BentoPanel>

        <BentoPanel title="Season events" span={6} className="monitor-records-events-panel">
          <div className="stack-col-8">
            {(pickSource === "all" ? seasonEvents : gradingHistory).map((item) => {
              const id = `${item.event_id}-${item.year}`
              const isExpanded = expandedId === id
              const seasonEvent: GradingSeasonEvent | undefined =
                pickSource === "all"
                  ? (item as GradingSeasonEvent)
                  : seasonEvents.find((row) => row.event_id === item.event_id)
              const showComparison = pickSource === "all" && seasonEvent?.lanes != null

              if (showComparison && seasonEvent?.lanes) {
                const dash = seasonEvent.lanes.dashboard
                const lab = seasonEvent.lanes.lab
                return (
                  <div key={id} className="tr-event">
                    <div
                      className="tr-event-header"
                      onClick={() => setExpandedId(isExpanded ? null : id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault()
                          setExpandedId(isExpanded ? null : id)
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      data-testid={`grading-event-${id}`}
                    >
                      <div className="tr-event-meta">
                        <div className="tr-event-name">{item.name}</div>
                        <div className="tr-event-sub">
                          {formatSeasonEventDate(seasonEvent?.event_date) ? (
                            <span>{formatSeasonEventDate(seasonEvent?.event_date)} · </span>
                          ) : null}
                          Dashboard {dash.hits ?? 0}/{dash.graded_pick_count} · Lab {lab.hits ?? 0}/{lab.graded_pick_count}
                          {seasonEvent?.picks_detail_missing ? " · Rollup detail missing" : ""}
                          {seasonEvent?.status === "in_progress" ? " · In progress" : ""}
                        </div>
                      </div>
                      <div className="tr-event-actions">
                        <span className="tr-event-profit tr-event-profit--pos">
                          {formatUnits(dash.total_profit ?? 0)}
                        </span>
                        <span className="tr-event-profit tr-event-profit--neg ml-2">
                          {formatUnits(lab.total_profit ?? 0)}
                        </span>
                        <ChevronDown
                          size={13}
                          className={cn("tr-event-chevron", isExpanded && "tr-event-chevron--open")}
                        />
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="tr-event-body stack-col-8">
                        <div className="grid gap-3 md:grid-cols-2">
                          <div>
                            <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">
                              Dashboard · {laneStatusLabel(dash.status)}
                            </div>
                            {(dash.picks?.length ?? 0) > 0 ? (
                              <HeroDataGrid
                                data={dash.picks ?? []}
                                columns={gradingPickColumns}
                                getRowId={(row) => `dash-${row.player_display}-${row.opponent_display ?? "solo"}`}
                                density="compact"
                                testId={`grading-picks-dashboard-${id}`}
                              />
                            ) : (
                              <RecordsEmptyState message="No graded Dashboard picks for this event." />
                            )}
                          </div>
                          <div>
                            <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">
                              Lab · {laneStatusLabel(lab.status)}
                            </div>
                            {(lab.picks?.length ?? 0) > 0 ? (
                              <HeroDataGrid
                                data={lab.picks ?? []}
                                columns={gradingPickColumns}
                                getRowId={(row) => `lab-${row.player_display}-${row.opponent_display ?? "solo"}`}
                                density="compact"
                                testId={`grading-picks-lab-${id}`}
                              />
                            ) : (
                              <RecordsEmptyState message="No graded Lab picks for this event." />
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              }

              const profit = Number(item.total_profit ?? 0)
              const picks = item.graded_pick_count ?? 0
              const hits = item.hits ?? 0
              const hr = picks > 0 ? `${((hits / picks) * 100).toFixed(0)}%` : "—"
              const laneStatus = seasonEvent
                ? laneStatusLabel(
                    pickSource === "lab"
                      ? seasonEvent.lanes?.lab.status
                      : seasonEvent.lanes?.dashboard.status,
                  )
                : null

              return (
                <div key={id} className="tr-event">
                  <div
                    className="tr-event-header"
                    onClick={() => setExpandedId(isExpanded ? null : id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault()
                        setExpandedId(isExpanded ? null : id)
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    data-testid={`grading-event-${id}`}
                  >
                    <div className="tr-event-meta">
                      <div className="tr-event-name">{item.name}</div>
                      <div className="tr-event-sub">
                        {formatSeasonEventDate(seasonEvent?.event_date) ? (
                          <span>{formatSeasonEventDate(seasonEvent?.event_date)} · </span>
                        ) : null}
                        {hits}/{picks} hits · {hr}
                        {laneStatus ? ` · ${laneStatus}` : ""}
                        {seasonEvent?.picks_detail_missing ? " · Rollup detail missing" : ""}
                        {seasonEvent?.status === "in_progress" ? " · In progress" : ""}
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
                        <div
                          className="kpi-tile neutral kpi-tile--help"
                          title={GRADING_KPI_STRIP_TOOLTIPS.Course}
                        >
                          <div className="kpi-label">Course</div>
                          <div className="kpi-value kpi-value--sm">{item.course ?? "—"}</div>
                        </div>
                        <div
                          className="kpi-tile neutral kpi-tile--help"
                          title={GRADING_KPI_STRIP_TOOLTIPS.Year}
                        >
                          <div className="kpi-label">Year</div>
                          <div className="kpi-value num kpi-value--md">{item.year ?? "—"}</div>
                        </div>
                      </div>
                      {(item.picks?.length ?? 0) > 0 && (
                        <div className="records-picks-grid">
                          <HeroDataGrid
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
            {(pickSource === "all" ? seasonEvents : gradingHistory).length === 0 && (
              <RecordsEmptyState message="No season events with picks yet. Run hydration or grade a tournament." />
            )}
          </div>
        </BentoPanel>
      </BentoGrid>
    </div>
  )
}

export function TrackRecordPage() {
  const trackRecordQuery = useQuery({
    queryKey: ["track-record"],
    queryFn: api.getTrackRecord,
  })
  const gradingHistoryQuery = useQuery({
    queryKey: ["grading-history", "all"],
    queryFn: () => api.getGradingHistory({ pickSource: "all" }),
  })
  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    staleTime: 60_000,
  })
  const trustMetrics = useMemo(
    () => buildGradingTrustMetrics(gradingHistoryQuery.data, dashboardQuery.data),
    [gradingHistoryQuery.data, dashboardQuery.data],
  )

  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const mergedResult = mergeTrackRecordEvents(trackRecordQuery.data?.events ?? [])
  const events: MergedTrackRecordEvent[] = Array.isArray(mergedResult)
    ? (mergedResult as MergedTrackRecordEvent[])
    : ((mergedResult as { events: MergedTrackRecordEvent[] }).events ?? [])

  const totalProfit = events.reduce((s, e) => s + Number(e.profit ?? 0), 0)
  const totalWins = events.reduce((s, e) => s + (e.wins ?? 0), 0)
  const totalPicks = events.reduce((s, e) => s + (e.wins ?? 0) + (e.losses ?? 0) + (e.pushes ?? 0), 0)

  const summaryKpis = useMemo((): MacroKpiItem[] => {
    return [
      {
        id: "pnl",
        label: "Total P&L",
        value: formatUnits(totalProfit),
        tone: totalProfit >= 0 ? "positive" : "negative",
      },
      { id: "events", label: "Tournaments", value: String(events.length) },
      {
        id: "win-rate",
        label: "Win rate",
        value: totalPicks > 0 ? `${((totalWins / totalPicks) * 100).toFixed(0)}%` : "—",
        suffix: totalPicks > 0 ? `${totalWins}/${totalPicks}` : undefined,
      },
      { id: "wins", label: "Wins", value: String(totalWins), tone: "positive" },
    ]
  }, [events, totalPicks, totalProfit, totalWins])

  if (trackRecordQuery.isLoading) {
    return <div className="records-loading monitor-scroll-region">Loading track record…</div>
  }

  return (
    <div className="monitor-records-page monitor-scroll-region" data-testid="track-record-page">
      <HeroBand
        eyebrow="Records"
        title="Track record"
        meta="Official Dashboard betting record (+EV picks). Compare Lab on the Grading tab."
      />

      <GradingTrustStrip
        metrics={trustMetrics}
        pickSource="all"
        onPickSourceChange={() => {}}
        isFetching={gradingHistoryQuery.isFetching}
        showSourceToggle={false}
      />

      <MacroKpiStrip items={summaryKpis} testId="track-record-summary-kpis" />

      <BentoGrid columns={1} testId="track-record-bento">
        <BentoPanel title="Tournament history" span={12}>
        <div className="records-event-stack">
          {events.length > 0 ? (
            events.map((event, idx) => {
              const isExpanded = expandedIdx === idx
              const profit = Number(event.profit ?? 0)
              const picks = event.picks ?? []
              const eventTotal = (event.wins ?? 0) + (event.losses ?? 0) + (event.pushes ?? 0)
              const hr =
                eventTotal > 0 ? `${(((event.wins ?? 0) / eventTotal) * 100).toFixed(0)}%` : "—"

              return (
                <div key={`${event.name}-${idx}`} className="tr-event">
                  <div
                    className="tr-event-header"
                    onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                    onKeyDown={(keyEvent) => {
                      if (keyEvent.key === "Enter" || keyEvent.key === " ") {
                        keyEvent.preventDefault()
                        setExpandedIdx(isExpanded ? null : idx)
                      }
                    }}
                    role="button"
                    tabIndex={0}
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
                      <HeroDataGrid
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
                      <RecordsEmptyState message="No pick detail available for this tournament." />
                    </div>
                  )}
                </div>
              )
            })
          ) : (
            <RecordsEmptyState message="No track record data yet. Grade tournaments to build your history." />
          )}
        </div>
        </BentoPanel>
      </BentoGrid>
    </div>
  )
}
