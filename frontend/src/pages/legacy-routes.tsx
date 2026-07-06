import type { CellContext, ColumnDef } from "@tanstack/react-table"
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
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import { PickRow } from "@/components/ui/pick-row"
import { ProDataGrid } from "@/components/ui/pro-data-grid"
import { StatusBanner } from "@/components/ui/status-banner"
import { buildTrackRecordPickColumns } from "@/lib/records-columns"
import { api } from "@/lib/api"
import { formatDateTime, formatUnits } from "@/lib/format"
import { buildGradingTrustMetrics } from "@/lib/grading-trust"
import { formatSeasonEventDate, laneStatusLabel, pickLatestGradedSeasonEvent, recentGradedSeasonEventsForTrend, seasonEventsToGradingHistory, seasonLaneFromPickSource } from "@/lib/grading-season"
import type { GradingSeasonEvent, MatchupBet, TrackRecordPick } from "@/lib/types"
import { mergeTrackRecordEvents, type MergedTrackRecordEvent } from "@/lib/track-record"
import { cn } from "@/lib/utils"

const trackRecordPickColumns = buildTrackRecordPickColumns()
const statusToneClass = {
  good: "good",
  warn: "warn",
  bad: "bad",
  muted: "muted",
} as const

type PickSource = "all" | "cockpit" | "lab"
type SeasonStatusTone = keyof typeof statusToneClass

const getEventRowId = (event: GradingSeasonEvent) =>
  `${event.event_id ?? event.tournament_id ?? event.name}-${event.year ?? "season"}`

const parseAmericanOdds = (value: string | null | undefined): number | null => {
  if (!value) return null
  const parsed = Number(String(value).replace(/[^\d+-]/g, ""))
  if (!Number.isFinite(parsed) || parsed === 0) return null
  if (parsed > 0) {
    return 100 / (parsed + 100)
  }
  return Math.abs(parsed) / (Math.abs(parsed) + 100)
}

const pickTierFromEdge = (edge: number | null | undefined): MatchupBet["tier"] => {
  const safeEdge = Number(edge ?? 0)
  if (safeEdge >= 0.15) return "STRONG"
  if (safeEdge >= 0.08) return "GOOD"
  return "LEAN"
}

const trackRecordPickToBet = (pick: TrackRecordPick): MatchupBet => {
  const modelWinProb = Number(pick.model_prob ?? 0)
  const impliedProb = parseAmericanOdds(pick.market_odds) ?? modelWinProb
  return {
    pick: pick.player_display,
    pick_key: pick.player_key ?? pick.player_display,
    opponent: pick.opponent_display ?? "",
    opponent_key: pick.opponent_key ?? pick.opponent_display ?? pick.player_display,
    odds: pick.market_odds ?? "—",
    book: pick.market_book ?? undefined,
    model_win_prob: modelWinProb,
    implied_prob: impliedProb,
    ev: Number(pick.ev ?? 0),
    ev_pct: "",
    composite_gap: 0,
    form_gap: 0,
    course_fit_gap: 0,
    reason: pick.reasoning ?? pick.actual_finish ?? "",
    tier: pickTierFromEdge(pick.ev),
    market_type: pick.market_type ?? pick.bet_type ?? "matchup",
  }
}

const pickRowId = (pick: TrackRecordPick, prefix: string) =>
  String(pick.id ?? `${prefix}-${pick.bet_type ?? "bet"}-${pick.player_display}-${pick.opponent_display ?? "solo"}-${pick.market_odds ?? "odds"}`)

const pickSourceLabel = (pickSource: PickSource) => {
  if (pickSource === "cockpit") return "Dashboard"
  if (pickSource === "lab") return "Lab"
  return "All"
}

const sumLaneUngraded = (event: GradingSeasonEvent, pickSource: PickSource) => {
  if (pickSource === "lab") return event.lanes?.lab.ungraded_positive_ev_count ?? 0
  if (pickSource === "all") {
    return (
      (event.lanes?.dashboard.ungraded_positive_ev_count ?? 0) +
      (event.lanes?.lab.ungraded_positive_ev_count ?? 0)
    )
  }
  return event.lanes?.dashboard.ungraded_positive_ev_count ?? 0
}

const buildSeasonStatus = (
  event: GradingSeasonEvent,
  pickSource: PickSource,
): { label: string; reason: string; tone: SeasonStatusTone } => {
  const ungradedCount = sumLaneUngraded(event, pickSource)
  const mismatch =
    event.reconciliation && event.reconciliation.reconciliation_ok === false
      ? ` Past ${event.reconciliation.past_replay_positive_matchups ?? 0} vs Results ${event.reconciliation.graded_deduped_count ?? 0}.`
      : ""

  if (event.status === "partial" || ungradedCount > 0) {
    return {
      label: "Partial",
      reason: `${ungradedCount} +EV pick${ungradedCount === 1 ? "" : "s"} still need grading.${mismatch}`,
      tone: event.reconciliation?.reconciliation_ok === false ? "bad" : "warn",
    }
  }

  if (event.status === "in_progress" || (!event.has_results && (event.inventory_count ?? 0) > 0)) {
    return {
      label: "Awaiting results",
      reason: `Waiting on final Data Golf results before grading can finish.${mismatch}`,
      tone: "warn",
    }
  }

  if (event.status === "inventory_only" || event.status === "card_recovered") {
    return {
      label: event.status === "card_recovered" ? "Card recovered" : "Inventory only",
      reason: `Pick inventory is present, but detailed graded outcomes are not ready yet.${mismatch}`,
      tone: "warn",
    }
  }

  if (event.status === "rollup_only" || event.picks_detail_missing) {
    return {
      label: "Rollup only",
      reason: `Season totals exist, but detailed pick rows are missing.${mismatch}`,
      tone: "warn",
    }
  }

  if (event.status === "no_data") {
    return {
      label: "No data",
      reason: "No recovered pick inventory or final results are available for this event yet.",
      tone: "muted",
    }
  }

  return {
    label: "Graded",
    reason: `Every visible +EV pick for this lane has a recorded outcome.${mismatch}`,
    tone: event.reconciliation?.reconciliation_ok === false ? "warn" : "good",
  }
}

function PickRowListSection({
  title,
  status,
  picks,
  emptyMessage,
  idPrefix,
}: {
  title: string
  status?: string
  picks: TrackRecordPick[]
  emptyMessage: string
  idPrefix: string
}) {
  const [expandedPickId, setExpandedPickId] = useState<string | null>(null)

  return (
    <section className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
          {status ? <span className="status-pill muted">{laneStatusLabel(status)}</span> : null}
        </div>
        <p className="text-xs text-[var(--text-secondary)]">
          Expand a pick to inspect the stored grading detail for this event.
        </p>
      </div>
      {picks.length > 0 ? (
        <div className="space-y-3">
          {picks.map((pick) => {
            const rowId = pickRowId(pick, idPrefix)
            return (
              <PickRow
                key={rowId}
                bet={trackRecordPickToBet(pick)}
                gradedResult={pick.outcome}
                expanded={expandedPickId === rowId}
                onExpand={() => setExpandedPickId(expandedPickId === rowId ? null : rowId)}
              />
            )
          })}
        </div>
      ) : (
        <EmptyState message={emptyMessage} />
      )}
    </section>
  )
}

function SeasonEventDetail({
  event,
  pickSource,
}: {
  event: GradingSeasonEvent
  pickSource: PickSource
}) {
  const gradeReport = event.grading_report
  const showMismatchBanner = event.reconciliation && event.reconciliation.reconciliation_ok === false

  return (
    <div className="space-y-4 py-2" data-testid={`grading-event-detail-${getEventRowId(event)}`}>
      {gradeReport ? (
        <StatusBanner
          tone={gradeReport.status === "partial" ? "warn" : "info"}
          title="Latest grade report"
          message={
            gradeReport.message ??
            `Scored ${gradeReport.scored_count ?? 0} · Voided ${gradeReport.voided_count ?? 0} · Skipped ${gradeReport.skipped_count ?? 0}`
          }
        />
      ) : null}
      {showMismatchBanner ? (
        <StatusBanner
          tone="warn"
          title="Past vs Results mismatch"
          message={`Past replay shows ${event.reconciliation?.past_replay_positive_matchups ?? 0} +EV matchups, but Results has ${event.reconciliation?.graded_deduped_count ?? 0} graded rows.`}
        />
      ) : null}
      <div className={cn("grid gap-4", pickSource === "all" ? "xl:grid-cols-2" : "grid-cols-1")}>
        {pickSource === "all" ? (
          <>
            <PickRowListSection
              title="Dashboard picks"
              status={event.lanes?.dashboard.status}
              picks={event.lanes?.dashboard.picks ?? []}
              emptyMessage="No graded Dashboard picks for this event."
              idPrefix={`${getEventRowId(event)}-dashboard`}
            />
            <PickRowListSection
              title="Lab picks"
              status={event.lanes?.lab.status}
              picks={event.lanes?.lab.picks ?? []}
              emptyMessage="No graded Lab picks for this event."
              idPrefix={`${getEventRowId(event)}-lab`}
            />
          </>
        ) : (
          <PickRowListSection
            title={`${pickSourceLabel(pickSource)} picks`}
            status={pickSource === "lab" ? event.lanes?.lab.status : event.lanes?.dashboard.status}
            picks={pickSource === "lab" ? event.lanes?.lab.picks ?? [] : event.lanes?.dashboard.picks ?? []}
            emptyMessage={`No graded ${pickSourceLabel(pickSource)} picks for this event.`}
            idPrefix={`${getEventRowId(event)}-${pickSource}`}
          />
        )}
      </div>
    </div>
  )
}

export function GradingPage() {
  const [pickSource, setPickSource] = useState<PickSource>("cockpit")
  const seasonQuery = useQuery({
    queryKey: ["grading-season", pickSource],
    queryFn: () =>
      api.getGradingSeason({
        year: 2026,
        lane: seasonLaneFromPickSource(pickSource),
        includePicks: true,
        includeReconciliation: true,
        limit: 100,
      }),
  })
  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    staleTime: 60_000,
  })
  const liveRefreshStatusQuery = useQuery({
    queryKey: ["live-refresh-status"],
    queryFn: api.getLiveRefreshStatus,
    staleTime: 30_000,
  })
  const gradingHistoryData = useMemo(
    () => seasonEventsToGradingHistory(seasonQuery.data, pickSource),
    [seasonQuery.data, pickSource],
  )
  const trustMetrics = useMemo(
    () =>
      buildGradingTrustMetrics(
        gradingHistoryData,
        dashboardQuery.data,
        liveRefreshStatusQuery.data?.status,
        seasonQuery.data,
        pickSource,
      ),
    [gradingHistoryData, dashboardQuery.data, liveRefreshStatusQuery.data?.status, pickSource, seasonQuery.data],
  )

  const gradingHistory = gradingHistoryData.tournaments ?? []
  const seasonEvents: GradingSeasonEvent[] = seasonQuery.data?.events ?? []
  const seasonSummary = seasonQuery.data?.summary
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const latestGradedSeasonEvent = useMemo(
    () => pickLatestGradedSeasonEvent(seasonEvents, pickSource),
    [pickSource, seasonEvents],
  )

  const trendEvents = useMemo(
    () => recentGradedSeasonEventsForTrend(seasonEvents, pickSource, 8),
    [pickSource, seasonEvents],
  )

  const labels = trendEvents
    .map((item) => item.name.replace(/open|championship|invitational/gi, "").trim().split(" ").slice(-1)[0] ?? item.name)
  const profits = trendEvents.map((item) => {
    if (pickSource === "all") {
      return Number(item.total_profit ?? 0)
    }
    const lane = pickSource === "lab" ? item.lanes?.lab : item.lanes?.dashboard
    return Number(lane?.total_profit ?? item.total_profit ?? 0)
  })

  const totalProfit = gradingHistory.reduce((s, t) => s + Number(t.total_profit ?? 0), 0)
  const totalHits = gradingHistory.reduce((s, t) => s + (t.hits ?? 0), 0)
  const totalPicks = gradingHistory.reduce((s, t) => s + (t.graded_pick_count ?? 0), 0)
  const seasonTableColumns = useMemo((): ColumnDef<GradingSeasonEvent, unknown>[] => {
    const buildLaneSummary = (event: GradingSeasonEvent, lane: "dashboard" | "lab") => {
      const laneSummary = lane === "lab" ? event.lanes?.lab : event.lanes?.dashboard
      if (!laneSummary) {
        return <span className="text-xs text-[var(--text-secondary)]">No lane data</span>
      }
      const hitRate =
        laneSummary.graded_pick_count > 0 && laneSummary.hits != null
          ? `${Math.round((laneSummary.hits / laneSummary.graded_pick_count) * 100)}%`
          : "—"
      return (
        <div className="space-y-1 text-xs">
          <div className="font-medium text-[var(--text-primary)]">
            {laneSummary.hits ?? 0}/{laneSummary.graded_pick_count} graded
          </div>
          <div className="text-[var(--text-secondary)]">
            Inventory {laneSummary.inventory_count} · Hit rate {hitRate}
          </div>
          <div className="num text-[var(--text-primary)]">{formatUnits(laneSummary.total_profit ?? 0)}</div>
        </div>
      )
    }

    return [
      {
        id: "event",
        header: "Event",
        meta: { label: "Event", sticky: true },
        cell: ({ row }) => {
          const event = row.original
          const meta = [formatSeasonEventDate(event.event_date), event.course].filter(Boolean).join(" · ")
          return (
            <div className="space-y-1 py-1">
              <div className="font-medium text-[var(--text-primary)]">{event.name}</div>
              {meta ? <div className="text-xs text-[var(--text-secondary)]">{meta}</div> : null}
            </div>
          )
        },
      },
      {
        id: "status",
        header: "Status",
        meta: { label: "Status" },
        cell: ({ row }) => {
          const status = buildSeasonStatus(row.original, pickSource)
          return (
            <div className="space-y-1 py-1">
              <span className={cn("status-pill", statusToneClass[status.tone])}>{status.label}</span>
              <div className="max-w-sm text-xs leading-5 text-[var(--text-secondary)]">{status.reason}</div>
            </div>
          )
        },
      },
      ...(pickSource === "all"
        ? [
            {
              id: "dashboard",
              header: "Dashboard",
              meta: { label: "Dashboard" },
              cell: (info: CellContext<GradingSeasonEvent, unknown>) =>
                buildLaneSummary(info.row.original, "dashboard"),
            },
            {
              id: "lab",
              header: "Lab",
              meta: { label: "Lab" },
              cell: (info: CellContext<GradingSeasonEvent, unknown>) =>
                buildLaneSummary(info.row.original, "lab"),
            },
          ]
        : [
            {
              id: "record",
              header: "Record",
              meta: { label: "Record" },
              cell: (info: CellContext<GradingSeasonEvent, unknown>) => {
                const lane =
                  pickSource === "lab" ? info.row.original.lanes?.lab : info.row.original.lanes?.dashboard
                const hitRate =
                  lane && lane.graded_pick_count > 0 && lane.hits != null
                    ? `${Math.round((lane.hits / lane.graded_pick_count) * 100)}%`
                    : "—"
                return (
                  <div className="space-y-1 text-xs py-1">
                    <div className="font-medium text-[var(--text-primary)]">
                      {lane?.hits ?? info.row.original.hits ?? 0}/
                      {lane?.graded_pick_count ?? info.row.original.graded_pick_count ?? 0} graded
                    </div>
                    <div className="text-[var(--text-secondary)]">
                      Inventory {lane?.inventory_count ?? info.row.original.picks_count ?? 0} · Hit rate {hitRate}
                    </div>
                    <div className="text-[var(--text-secondary)]">
                      Ungraded +EV{" "}
                      {lane?.ungraded_positive_ev_count ?? sumLaneUngraded(info.row.original, pickSource)}
                    </div>
                  </div>
                )
              },
            },
          ]),
      {
        id: "pnl",
        header: "P&L",
        meta: { label: "P&L", align: "right", mono: true },
        cell: ({ row }) => {
          const profit =
            pickSource === "lab"
              ? Number(row.original.lanes?.lab.total_profit ?? row.original.total_profit ?? 0)
              : pickSource === "cockpit"
                ? Number(row.original.lanes?.dashboard.total_profit ?? row.original.total_profit ?? 0)
                : Number(row.original.total_profit ?? 0)
          return (
            <span
              className={cn(
                "num font-medium",
                profit > 0
                  ? "text-[var(--green)]"
                  : profit < 0
                    ? "text-[var(--red)]"
                    : "text-[var(--text-secondary)]",
              )}
            >
              {formatUnits(profit)}
            </span>
          )
        },
      },
      {
        id: "detail",
        header: "Detail",
        meta: { label: "Detail", align: "right" },
        cell: ({ row }) => {
          const eventId = getEventRowId(row.original)
          const isExpanded = expandedId === eventId
          return (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={(event) => {
                event.stopPropagation()
                setExpandedId(isExpanded ? null : eventId)
              }}
              aria-expanded={isExpanded}
              data-testid={`grading-detail-toggle-${eventId}`}
            >
              {isExpanded ? "Hide" : "View"}
              <ChevronDown
                size={14}
                className={cn("transition-transform", isExpanded && "rotate-180")}
                aria-hidden
              />
            </Button>
          )
        },
      },
    ]
  }, [expandedId, pickSource])

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
        value: latestGradedSeasonEvent?.name ?? gradingHistory.find((e) => (e.graded_pick_count ?? 0) > 0)?.name ?? "—",
        suffix: latestGradedSeasonEvent?.last_graded_at
          ? formatDateTime(latestGradedSeasonEvent.last_graded_at)
          : undefined,
      },
    ]
  }, [gradingHistory, latestGradedSeasonEvent, pickSource, seasonSummary, totalHits, totalPicks, totalProfit])

  return (
    <div className="monitor-records-page monitor-scroll-region" data-testid="grading-page">
      <GradingTrustStrip
        metrics={trustMetrics}
        pickSource={pickSource}
        onPickSourceChange={setPickSource}
        isFetching={seasonQuery.isFetching}
      />

      <MacroKpiStrip items={summaryKpis} testId="grading-summary-kpis" />

      <BentoGrid columns={2} testId="grading-bento">
        <BentoPanel title="Season P&L trend" span={4}>
          {profits.length > 0 ? (
            <BarTrendChart labels={labels} values={profits} color="var(--accent-positive)" />
          ) : (
            <EmptyState message="Nothing graded yet this season." />
          )}
        </BentoPanel>

        <BentoPanel title="Season events" span={8} className="monitor-records-events-panel">
          <div className="space-y-4">
            {seasonQuery.isError ? (
              <StatusBanner
                tone="danger"
                title="Results season data failed to load"
                message={
                  seasonQuery.error instanceof Error
                    ? seasonQuery.error.message
                    : "The season grading table could not be loaded."
                }
              />
            ) : null}
            {seasonEvents.length === 0 && !seasonQuery.isLoading ? (
              <EmptyState
                message="Nothing graded yet this season."
                description="Grade a completed event or hydrate recovered cards to populate the season table."
              />
            ) : (
              <ProDataGrid<GradingSeasonEvent>
                data={seasonEvents}
                columns={seasonTableColumns}
                getRowId={getEventRowId}
                getRowTestId={(event) => `grading-season-row-${getEventRowId(event)}`}
                expandedRowId={expandedId}
                renderSubRow={(event) => <SeasonEventDetail event={event} pickSource={pickSource} />}
                onRowClick={(event) => {
                  const eventId = getEventRowId(event)
                  setExpandedId(expandedId === eventId ? null : eventId)
                }}
                isLoading={seasonQuery.isLoading}
                loadingMessage="Loading season events…"
                testId="grading-season-grid"
              />
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
  const seasonQuery = useQuery({
    queryKey: ["grading-season", "all"],
    queryFn: () =>
      api.getGradingSeason({
        year: 2026,
        lane: "all",
        includePicks: false,
        includeReconciliation: false,
        limit: 100,
      }),
  })
  const dashboardQuery = useQuery({
    queryKey: ["dashboard-state"],
    queryFn: api.getDashboardState,
    staleTime: 60_000,
  })
  const liveRefreshStatusQuery = useQuery({
    queryKey: ["live-refresh-status"],
    queryFn: api.getLiveRefreshStatus,
    staleTime: 30_000,
  })
  const trustMetrics = useMemo(
    () =>
      buildGradingTrustMetrics(
        gradingHistoryQuery.data,
        dashboardQuery.data,
        liveRefreshStatusQuery.data?.status,
        seasonQuery.data,
        "all",
      ),
    [gradingHistoryQuery.data, dashboardQuery.data, liveRefreshStatusQuery.data?.status, seasonQuery.data],
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
                      <EmptyState message="No pick detail available for this tournament." />
                    </div>
                  )}
                </div>
              )
            })
          ) : (
            <EmptyState message="No track record data yet. Grade tournaments to build your history." />
          )}
        </div>
        </BentoPanel>
      </BentoGrid>
    </div>
  )
}
