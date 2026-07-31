import { useState } from "react"
import { useSearchParams } from "react-router-dom"

import { DataTable } from "@/components/operator/data-table"
import { Drawer } from "@/components/operator/drawer"
import { FeedbackState } from "@/components/operator/feedback-state"
import { MetricHelp } from "@/components/operator/metric-help"
import { PageHeader } from "@/components/operator/page-header"
import { PickRow, type PickRowData } from "@/components/operator/pick-row"
import { StatusBanner } from "@/components/operator/status-banner"
import { TrackBadge } from "@/components/operator/track-badge"
import { useOperatorBoardData, useOperatorSnapshotMetadata } from "@/features/operator-data/operator-data-provider"
import { dashboardPreviewFixture } from "@/features/dashboard/dashboard-preview-fixture"

const playerName = (row: Record<string, unknown>) => String(row.player_name ?? row.player_display ?? row.player ?? "Unknown player")

export function DashboardPreviewPage({ track }: { track: "champion" | "challenger" }) {
  const { board, viewState, error } = useOperatorBoardData()
  const { refresh } = useOperatorSnapshotMetadata()
  const [searchParams] = useSearchParams()
  const [selectedPick, setSelectedPick] = useState<PickRowData | null>(null)
  const useFixture = searchParams.get("source") !== "live"
  const picks = useFixture ? dashboardPreviewFixture.picks : (board?.picks.matchups ?? []).map((pick, index) => ({
    id: `${playerName(pick)}-${index}`,
    player: playerName(pick),
    opponent: String(pick.opponent_name ?? pick.opponent ?? "Opponent"),
    market: String(pick.market_type ?? "Matchup"),
    edge: `${Number(pick.ev ?? pick.edge ?? 0).toFixed(1)}%`,
    odds: String(pick.market_odds ?? pick.odds ?? "—"),
  }))
  const rankings = (useFixture ? dashboardPreviewFixture.rankings : (board?.rankings ?? []).slice(0, 8).map((row, index) => ({
    id: `${playerName(row)}-${index}`,
    player: playerName(row),
    rank: String(row.rank ?? index + 1),
    score: String(row.composite ?? row.score ?? "—"),
    trend: String(row.rank_delta ?? "—"),
  }))).map((row) => ({ ...row, rank: String(row.rank) }))

  if (!useFixture && viewState === "loading") return <FeedbackState state="loading" title="Loading operator dashboard" detail="Retrieving the current board." />
  if (!useFixture && (viewState === "error" || viewState === "unavailable")) return <FeedbackState state={viewState === "error" ? "error" : "unavailable"} title={viewState === "error" ? "Dashboard request failed" : "Dashboard unavailable"} detail={error?.message ?? board?.reason.message} actionLabel="Retry" onAction={refresh} />
  if (!useFixture && viewState === "empty") return <FeedbackState state="empty" title="No qualifying picks" detail={board?.reason.message ?? "The current data has no qualifying rows."} actionLabel="Refresh" onAction={refresh} />

  const stale = !useFixture && viewState === "stale"
  const refreshing = !useFixture && board?.state === "refreshing"
  const state = stale ? "stale" : refreshing ? "refreshing" : "ready"
  const message = stale ? "Showing the last retained board. Do not treat prices as current." : refreshing ? "Refreshing lines; current picks remain visible." : `Updated ${board?.source.generated_at ?? dashboardPreviewFixture.event.updated}.`

  return (
    <main className="operator-app min-h-screen px-4 py-4 lg:px-6">
      <div className="mx-auto flex w-full max-w-[1500px] gap-6">
        <aside className="hidden w-56 shrink-0 border-r border-slate-800 pr-4 lg:block" aria-label="Operator navigation">
          <p className="pt-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Operator</p>
          <p className="mt-6 border-l-2 border-emerald-400 px-3 py-2 text-sm font-semibold text-white">Dashboard</p>
          <p className="px-3 py-2 text-sm text-slate-500">Lab</p>
        </aside>
        <div className="min-w-0 flex-1 space-y-4">
          <PageHeader eyebrow="Live model board" title={board?.event.event_name ?? dashboardPreviewFixture.event.name} detail={board?.event.course_name ?? dashboardPreviewFixture.event.course} actions={<><TrackBadge track={track} /><button type="button" onClick={refresh} className="min-h-11 border border-slate-600 px-3 text-sm font-medium text-white hover:border-emerald-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300">Refresh</button></>} />
          <StatusBanner state={state} message={message} />
          <section aria-labelledby="picks-heading" className="border border-slate-800 bg-[#11151a]">
            <div className="flex items-center justify-between border-b border-slate-800 px-3 py-3">
              <div><h2 id="picks-heading" className="text-xl font-semibold text-white">Top picks</h2><p className="mt-1 text-sm text-slate-400">Qualifying matchup edges, ordered by edge.</p></div>
              <span className="operator-num text-sm text-slate-400">{picks.length} rows</span>
            </div>
            {picks.length ? picks.map((pick) => <PickRow key={pick.id} pick={pick} onSelect={setSelectedPick} />) : <FeedbackState state="empty" title="No qualifying picks" detail="Current filters exclude all matchups." />}
          </section>
          <section aria-labelledby="rankings-heading">
            <div className="mb-2 flex items-center justify-between"><h2 id="rankings-heading" className="text-xl font-semibold text-white">Rankings</h2><MetricHelp label="Composite" detail="The current model score used to rank available players." /></div>
            <DataTable caption="Operator rankings" rows={rankings} columns={[{ id: "rank", label: "Rank", render: (row) => row.rank }, { id: "player", label: "Player", render: (row) => row.player }, { id: "score", label: "Composite", align: "right", render: (row) => row.score }, { id: "trend", label: "Δ", align: "right", render: (row) => row.trend }]} />
          </section>
        </div>
      </div>
      <Drawer open={Boolean(selectedPick)} title={selectedPick ? `${selectedPick.player} matchup` : "Pick details"} onClose={() => setSelectedPick(null)}>{selectedPick ? <dl className="space-y-3"><div><dt className="text-xs uppercase tracking-wide text-slate-500">Opponent</dt><dd>{selectedPick.opponent}</dd></div><div><dt className="text-xs uppercase tracking-wide text-slate-500">Edge</dt><dd className="operator-num text-emerald-300">{selectedPick.edge}</dd></div><div><dt className="text-xs uppercase tracking-wide text-slate-500">Price</dt><dd className="operator-num">{selectedPick.odds}</dd></div></dl> : null}</Drawer>
    </main>
  )
}
