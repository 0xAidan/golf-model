import { useState, type ReactNode } from "react"
import { useSearchParams } from "react-router-dom"

import { Drawer } from "@/components/operator/drawer"
import { FeedbackState } from "@/components/operator/feedback-state"
import { MetricHelp } from "@/components/operator/metric-help"
import { PageHeader } from "@/components/operator/page-header"
import { PickRow, type PickRowData } from "@/components/operator/pick-row"
import { StatCard } from "@/components/operator/stat-card"
import { StatusBanner } from "@/components/operator/status-banner"
import { TrackBadge } from "@/components/operator/track-badge"
import { useOperatorBoardData, useOperatorSnapshotMetadata } from "@/features/operator-data/operator-data-provider"
import { dashboardPreviewFixture, type RankingRow } from "@/features/dashboard/dashboard-preview-fixture"

const playerName = (row: Record<string, unknown>) =>
  String(row.player_name ?? row.player_display ?? row.player ?? "Unknown player")

function TrendIndicator({ trend }: { trend: number }) {
  if (trend === 0) return <span className="op-num text-[var(--op-text-tertiary)]">—</span>
  const up = trend > 0
  return (
    <span className={`op-num inline-flex items-center gap-0.5 ${up ? "text-[var(--op-accent)]" : "text-[var(--op-negative)]"}`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} aria-hidden="true" className="h-3 w-3">
        {up ? <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" /> : <path d="M12 5v14M5 12l7 7 7-7" strokeLinecap="round" strokeLinejoin="round" />}
      </svg>
      {Math.abs(trend)}
    </span>
  )
}

function RankingLeaderboard({ rows }: { rows: RankingRow[] }) {
  return (
    <ul className="flex flex-col">
      {rows.map((row) => (
        <li
          key={row.id}
          className="flex items-center gap-3 border-b border-[var(--op-border)] px-4 py-3 last:border-b-0"
        >
          <span className={`op-medal ${row.rank <= 3 ? `op-medal-${row.rank}` : ""}`}>{row.rank}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-white">{row.player}</p>
            {row.form ? <p className="op-num truncate text-[11px] text-[var(--op-text-tertiary)]">{row.form}</p> : null}
          </div>
          <span className="op-num text-sm font-semibold text-white">{row.score}</span>
          <span className="w-10 text-right">
            <TrendIndicator trend={row.trend} />
          </span>
        </li>
      ))}
    </ul>
  )
}

function SectionCard({
  title,
  description,
  aside,
  children,
  labelledBy,
}: {
  title: string
  description?: string
  aside?: ReactNode
  children: ReactNode
  labelledBy: string
}) {
  return (
    <section aria-labelledby={labelledBy} className="op-card overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--op-border)] px-4 py-3.5">
        <div>
          <h2 id={labelledBy} className="text-[15px] font-semibold text-white">{title}</h2>
          {description ? <p className="mt-0.5 text-[13px] text-[var(--op-text-tertiary)]">{description}</p> : null}
        </div>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function DashboardPreviewPage({ track }: { track: "champion" | "challenger" }) {
  const { board, viewState, error } = useOperatorBoardData()
  const { refresh } = useOperatorSnapshotMetadata()
  const [searchParams] = useSearchParams()
  const [selectedPick, setSelectedPick] = useState<PickRowData | null>(null)
  const useFixture = searchParams.get("source") !== "live"

  const picks: PickRowData[] = useFixture
    ? [...dashboardPreviewFixture.picks]
    : (board?.picks.matchups ?? []).map((pick, index) => {
        const edgeValue = Number(pick.ev ?? pick.edge ?? 0)
        return {
          id: `${playerName(pick)}-${index}`,
          player: playerName(pick),
          opponent: String(pick.opponent_name ?? pick.opponent ?? "Opponent"),
          market: String(pick.market_type ?? "Matchup"),
          edge: `${edgeValue >= 0 ? "+" : ""}${edgeValue.toFixed(1)}%`,
          edgeValue,
          odds: String(pick.market_odds ?? pick.odds ?? "—"),
          winProb: pick.win_prob ? `${Math.round(Number(pick.win_prob) * 100)}%` : undefined,
        }
      })

  const rankings: RankingRow[] = useFixture
    ? [...dashboardPreviewFixture.rankings]
    : (board?.rankings ?? []).slice(0, 8).map((row, index) => ({
        id: `${playerName(row)}-${index}`,
        player: playerName(row),
        rank: Number(row.rank ?? index + 1),
        score: String(row.composite ?? row.score ?? "—"),
        trend: Number(row.rank_delta ?? 0) || 0,
        form: "",
      }))

  if (!useFixture && viewState === "loading")
    return (
      <div className="mx-auto w-full max-w-[1360px] px-5 py-8 lg:px-8">
        <FeedbackState state="loading" title="Loading operator dashboard" detail="Retrieving the current board." />
      </div>
    )
  if (!useFixture && (viewState === "error" || viewState === "unavailable"))
    return (
      <div className="mx-auto w-full max-w-[1360px] px-5 py-8 lg:px-8">
        <FeedbackState
          state={viewState === "error" ? "error" : "unavailable"}
          title={viewState === "error" ? "Dashboard request failed" : "Dashboard unavailable"}
          detail={error?.message ?? board?.reason.message}
          actionLabel="Retry"
          onAction={refresh}
        />
      </div>
    )
  if (!useFixture && viewState === "empty")
    return (
      <div className="mx-auto w-full max-w-[1360px] px-5 py-8 lg:px-8">
        <FeedbackState state="empty" title="No qualifying picks" detail={board?.reason.message ?? "The current data has no qualifying rows."} actionLabel="Refresh" onAction={refresh} />
      </div>
    )

  const stale = !useFixture && viewState === "stale"
  const refreshing = !useFixture && board?.state === "refreshing"
  const status = stale ? "stale" : refreshing ? "refreshing" : "ready"
  const statusMessage = stale
    ? "Showing the last retained board. Do not treat prices as current."
    : refreshing
      ? "Refreshing lines; current picks remain visible."
      : `Updated ${board?.source.generated_at ?? dashboardPreviewFixture.event.updated}.`

  const eventName = board?.event.event_name ?? dashboardPreviewFixture.event.name
  const courseName = board?.event.course_name ?? dashboardPreviewFixture.event.course
  const maxEdge = picks.reduce((max, pick) => Math.max(max, pick.edgeValue ?? 0), 0)
  const summary = dashboardPreviewFixture.summary
  const bestEdge = picks.length ? picks[0].edge : summary.bestEdge

  return (
    <div className="mx-auto w-full max-w-[1360px] px-5 py-7 lg:px-8 lg:py-8">
      <PageHeader
        eyebrow="Live model board"
        title={eventName}
        detail={courseName}
        meta={
          <>
            <span aria-hidden="true" className="text-[var(--op-text-tertiary)]">·</span>
            <span>{dashboardPreviewFixture.event.round}</span>
            <span aria-hidden="true" className="text-[var(--op-text-tertiary)]">·</span>
            <span className="op-num">{dashboardPreviewFixture.event.purse}</span>
          </>
        }
        actions={
          <>
            <TrackBadge track={track} />
            <button type="button" onClick={refresh} className="op-btn op-btn-primary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true" className="h-4 w-4">
                <path d="M21 12a9 9 0 1 1-2.64-6.36M21 4v5h-5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Refresh
            </button>
          </>
        }
      />

      <div className="mt-5">
        <StatusBanner state={status} message={statusMessage} />
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Qualifying picks" value={String(picks.length || summary.qualifyingPicks)} hint="Above edge threshold" tone="positive" />
        <StatCard label="Best edge" value={bestEdge} hint="Top matchup value" tone="positive" />
        <StatCard label="Average edge" value={summary.avgEdge} hint="Across qualifying picks" />
        <StatCard label="Players ranked" value={String(summary.playersRanked)} hint="In current field" />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <SectionCard
          labelledBy="picks-heading"
          title="Top picks"
          description="Qualifying matchup edges, ordered by model value."
          aside={<span className="op-chip">{picks.length} matchups</span>}
        >
          {picks.length ? (
            <div>
              {picks.map((pick, index) => (
                <PickRow key={pick.id} pick={pick} index={index} maxEdge={maxEdge} onSelect={setSelectedPick} />
              ))}
            </div>
          ) : (
            <div className="p-4">
              <FeedbackState state="empty" title="No qualifying picks" detail="Current filters exclude all matchups." />
            </div>
          )}
        </SectionCard>

        <SectionCard
          labelledBy="rankings-heading"
          title="Rankings"
          description="Current model composite, top of field."
          aside={<MetricHelp label="Composite" detail="The current model score used to rank available players." />}
        >
          <RankingLeaderboard rows={rankings} />
        </SectionCard>
      </div>

      <Drawer
        open={Boolean(selectedPick)}
        title={selectedPick ? `${selectedPick.player}` : "Pick details"}
        onClose={() => setSelectedPick(null)}
      >
        {selectedPick ? (
          <div className="space-y-5">
            <div className="op-card px-4 py-4">
              <p className="op-eyebrow">Matchup</p>
              <p className="mt-1 text-base font-semibold text-white">
                {selectedPick.player} <span className="text-[var(--op-text-tertiary)]">over</span> {selectedPick.opponent}
              </p>
              <p className="mt-1 text-[13px] text-[var(--op-text-secondary)]">{selectedPick.market}</p>
            </div>
            <dl className="grid grid-cols-2 gap-3">
              <div className="op-card px-4 py-3">
                <dt className="op-eyebrow">Model edge</dt>
                <dd className="op-num mt-1 text-xl font-semibold text-[var(--op-accent)]">{selectedPick.edge}</dd>
              </div>
              <div className="op-card px-4 py-3">
                <dt className="op-eyebrow">Market price</dt>
                <dd className="op-num mt-1 text-xl font-semibold text-white">{selectedPick.odds}</dd>
              </div>
              {selectedPick.winProb ? (
                <div className="op-card px-4 py-3">
                  <dt className="op-eyebrow">Win probability</dt>
                  <dd className="op-num mt-1 text-xl font-semibold text-white">{selectedPick.winProb}</dd>
                </div>
              ) : null}
            </dl>
            <p className="text-[13px] leading-relaxed text-[var(--op-text-tertiary)]">
              Full matchup breakdown, model inputs, and history will appear here in the next build stage.
            </p>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}
